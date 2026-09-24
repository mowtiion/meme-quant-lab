"""Replay the verified sample one block at a time, retaining no transaction history.

Offline replay only. Same decoder and economic checks as the cached benchmark;
unknown movements remain in the report. No altered GC thresholds or disabled GC.
"""
import argparse
import gc
import hashlib
import io
import json
import platform
import time
import zipfile
from collections import Counter
from pathlib import Path
from diagnose_economic_runtime import diagnose_residual, distribution, replay_one
from compare_second_source import digest
from verify_alchemy_phase_b import verify
from meme_quant.decoder import AMM, PUMP, IDLDecoder, decode_block
from meme_quant.economic import DetailsDigest
from meme_quant.reserve_ledger import account_keys
from meme_quant.token_ledger import ordered_instructions


def replay(path, expected):
    started = time.perf_counter()
    verified = verify(path)
    verified_at = time.perf_counter()
    if verified['artifact_sha256'] != expected['artifact_sha256']:
        raise ValueError('Different checkpoint artifact')
    decoders = {d.program: d for d in (IDLDecoder(Path('vendor/pump.json')), IDLDecoder(Path('vendor/pump_amm.json')))}
    details_hash = DetailsDigest()
    counts = Counter(); fees = Counter(); residuals = []; times = []; slowest = []
    gc_pauses = []; collection_started = None
    def collection_event(phase, info):
        nonlocal collection_started
        if phase == 'start':
            collection_started = time.perf_counter()
        elif phase == 'stop' and collection_started is not None:
            gc_pauses.append({'seconds': time.perf_counter()-collection_started, 'generation': info['generation']})
            collection_started = None
    replay_started = time.perf_counter()
    gc.callbacks.append(collection_event)
    try:
        with zipfile.ZipFile(path) as outer:
            for entry in outer.namelist():
                if not entry.endswith('.zip'):
                    continue
                with zipfile.ZipFile(io.BytesIO(outer.read(entry))) as part:
                    for name in part.namelist():
                        if name == 'comparison.json' or not name.endswith('.json'):
                            continue
                        slot = int(Path(name).stem); raw = part.read(name)
                        raw_hash = hashlib.sha256(raw).hexdigest()
                        if raw_hash != verified['slots'][str(slot)]['raw_sha256']:
                            raise ValueError('Evidence changed after verification')
                        block = json.loads(raw)['result']
                        rows, issues = decode_block(block, slot, raw_hash, decoders)
                        if issues:
                            raise ValueError('Block decoder issues')
                        counts['blocks'] += 1
                        counts['all_transactions'] += len(block['transactions'])
                        counts['decoded_events'] += len(rows)
                        grouped = {}
                        for row in rows:
                            grouped.setdefault(row['tx_index'], []).append(row)
                        item = result = decoded = tx = None
                        for index, tx in enumerate(block['transactions']):
                            if tx['meta'] is None or tx['meta']['err'] is not None:
                                continue
                            keys = account_keys(tx)
                            if not any(keys[ix['programIdIndex']] in {PUMP,AMM} for _,_,ix in ordered_instructions(tx)):
                                continue
                            item = {'slot': slot, 'tx_index': index, 'tx': tx, 'blockTime': block['blockTime'], 'raw_sha256': raw_hash}
                            if details_hash.count < 20:
                                replay_one(item, decoders)
                            before = len(gc_pauses)
                            decoded, result, timing = replay_one(item, decoders)
                            pause = sum(p['seconds'] for p in gc_pauses[before:])
                            if decoded != grouped.get(index, []):
                                raise ValueError('Single-transaction and block decoding differ')
                            times.append(timing[2])
                            slowest.append({'slot':slot, 'tx_index':index, 'combined_ms':timing[2]*1000, 'gc_pause_ms':pause*1000})
                            details_hash.add({'slot':slot, 'tx_index':index, 'signature':tx['transaction']['signatures'][0], **result})
                            counts['target_transactions'] += 1
                            fees.update(f['status'] for f in result['fee_checks'])
                            if result['lamport_check']['status']=='LAMPORTS_RECONCILED':
                                counts['sol_reconciled'] += 1
                            else:
                                counts['sol_unresolved'] += 1
                                residuals.append(diagnose_residual(item, result))
                        # Neither the next block nor an accumulated result list keeps these graphs alive.
                        del block, rows, grouped, tx, item, result, decoded, raw
    finally:
        gc.callbacks.remove(collection_event)
    finished = time.perf_counter()
    if details_hash.hexdigest() != expected['details_sha256']:
        raise ValueError('Streaming results differ from pinned checkpoint')
    return {'schema':'economic-stream-replay-v1', 'pilot_ready':False, 'network_requests':0,
            'artifact_sha256':verified['artifact_sha256'], 'details_sha256':details_hash.hexdigest(),
            'checkpoint_results_unchanged':True, 'counts':{**counts, 'fees':dict(fees)},
            'environment':{'python':platform.python_version(), 'machine':platform.machine(), 'system':platform.system(), 'parallel_workers':1},
            'timing':{'archive_integrity_seconds':verified_at-started,
                      'replay_including_block_loading_and_result_hashing_seconds':finished-replay_started,
                      'entire_diagnostic_seconds':finished-started,
                      'single_transaction_combined':distribution(times),
                      'gc_pauses_during_replay':gc_pauses,
                      'slowest_transactions':sorted(slowest,key=lambda r:r['combined_ms'],reverse=True)[:10]},
            'retention':'One decoded block and one transaction result; compressed evidence part, timing scalars and unresolved summaries also retained.',
            'limitations':['Offline sample; live RPC, queueing and finality not measured.',
                           'GC remains enabled with unchanged thresholds; per-transaction measurement excludes JSON loading and result hashing.',
                           'Same 20 target transactions warmed once before their measured call.',
                           'Archive verifier still loads the full sample; bounded retention applies to replay.',
                           'Block and single-transaction decoders both run to prove event equality.',
                           'No throughput SLA, statistical latency bound or gate promotion.'],
            'residual_groups':dict(Counter(' + '.join(r['associated_programs']) or 'OTHER' for r in residuals)),
            'residuals_sha256':digest(residuals),
            'residual_index_report':'reports/ECONOMIC_RUNTIME_DIAGNOSIS.json'}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('artifact',type=Path)
    parser.add_argument('--checkpoint',type=Path,default=Path('reports/ECONOMIC_CONTINUITY_VERIFICATION.json'))
    parser.add_argument('--out',type=Path,required=True); args=parser.parse_args()
    report=replay(args.artifact,json.loads(args.checkpoint.read_text()))
    args.out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('residuals','timing')},indent=2))
