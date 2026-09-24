"""Bounded offline diagnosis: verify evidence, replay real checks, index residuals.

Never turns a residual pattern into a modeled movement or a passing gate.
Timings are local wall time, not RPC latency or a production throughput guarantee.
"""
import argparse
import gc
import hashlib
import io
import json
import math
import platform
import statistics
import time
import zipfile
from collections import Counter
from pathlib import Path

from compare_second_source import digest
from verify_alchemy_phase_b import verify
from meme_quant.cpi import instruction_trace
from meme_quant.decoder import AMM, PUMP, IDLDecoder, decode_block, unbase58
from meme_quant.economic import audit_transaction
from meme_quant.reserve_ledger import account_keys
from meme_quant.token_ledger import ordered_instructions

FLASH = 'FLASHX8DrLbgeR8FcfNV1F5krxYcYMUdBkrP1EPBtxB9'
OTHER = '3s1rAymURnacreXreMy718GfqW6kygQsLNka1xDyW8pC'


def distribution(seconds):
    values = sorted(seconds)
    if not values:
        raise ValueError('Empty timing population')
    def percentile(p):
        return values[max(0, math.ceil(len(values)*p)-1)]*1000
    return {'count': len(values), 'total_seconds': sum(values),
            'median_ms': statistics.median(values)*1000,
            'p95_ms': percentile(.95), 'p99_ms': percentile(.99),
            'max_ms': values[-1]*1000, 'percentile_method': 'nearest_rank'}


def replay_one(item, decoders):
    start = time.perf_counter()
    rows, issues = decode_block({'blockTime': item['blockTime'], 'transactions': [item['tx']]},
                               item['slot'], item['raw_sha256'], decoders)
    if issues:
        raise ValueError(f'Decoder issues invalidate timing: {issues}')
    # Restore the actual block position after single-transaction decoding.
    for row in rows:
        row['tx_index'] = item['tx_index']
    decoded_at = time.perf_counter()
    result = audit_transaction(item['tx'], rows, decoders)
    end = time.perf_counter()
    return rows, result, (decoded_at-start, end-decoded_at, end-start)


def diagnose_residual(item, result):
    """Record association and arithmetic only; no inferred fee rules."""
    check = result['lamport_check']
    nodes = instruction_trace(item['tx'])
    programs = {node['program'] for node in nodes}
    associated = sorted(programs & {FLASH, OTHER})
    mismatches = check['mismatches']
    accounts = {m['account'] for m in mismatches}
    payer = account_keys(item['tx'])[0]
    return {'slot': item['slot'], 'tx_index': item['tx_index'],
            'signature': item['tx']['transaction']['signatures'][0],
            'raw_sha256': item['raw_sha256'], 'status': check['status'],
            'associated_programs': associated, 'causal_mapping_verified': False,
            'residual_sum': sum(m['residual'] for m in mismatches),
            'positive_residual_lamports': sum(max(m['residual'], 0) for m in mismatches),
            'transaction_fee_lamports': item['tx']['meta']['fee'],
            'payer_residual_lamports': next((m['residual'] for m in mismatches if m['account']==payer), 0),
            'payer_post_lamports': item['tx']['meta']['postBalances'][0],
            'mismatches': mismatches,
            'program_instructions': [
                {'program': n['program'], 'path': [n['outer_index'], n['inner_index']],
                 'data_hex': unbase58(n['instruction']['data']).hex(),
                 'residual_accounts_in_instruction': sorted(accounts & set(n['accounts']))}
                for n in nodes if n['program'] in associated]}


def diagnose(path, expected):
    started = time.perf_counter()
    verified = verify(path)
    verified_at = time.perf_counter()
    if verified['artifact_sha256'] != expected['artifact_sha256']:
        raise ValueError('Different checkpoint artifact')
    decoders = {d.program: d for d in (IDLDecoder(Path('vendor/pump.json')),
                                     IDLDecoder(Path('vendor/pump_amm.json')))}
    items, block_decode_seconds, block_times = [], [], []
    total_transactions = decoded_count = 0
    with zipfile.ZipFile(path) as outer:
        for entry in outer.namelist():
            if not entry.endswith('.zip'):
                continue
            with zipfile.ZipFile(io.BytesIO(outer.read(entry))) as part:
                for name in part.namelist():
                    if name == 'comparison.json' or not name.endswith('.json'):
                        continue
                    slot = int(Path(name).stem)
                    raw = part.read(name)
                    raw_hash = hashlib.sha256(raw).hexdigest()
                    if raw_hash != verified['slots'][str(slot)]['raw_sha256']:
                        raise ValueError('Evidence changed after verification')
                    block = json.loads(raw)['result']
                    total_transactions += len(block['transactions'])
                    block_times.append(block['blockTime'])
                    t = time.perf_counter()
                    rows, issues = decode_block(block, slot, raw_hash, decoders)
                    block_decode_seconds.append(time.perf_counter()-t)
                    if issues:
                        raise ValueError('Block decoder issues')
                    decoded_count += len(rows)
                    grouped = {}
                    for row in rows:
                        grouped.setdefault(row['tx_index'], []).append(row)
                    for index, tx in enumerate(block['transactions']):
                        if tx['meta'] is None or tx['meta']['err'] is not None:
                            continue
                        keys = account_keys(tx)
                        if not any(keys[ix['programIdIndex']] in {PUMP, AMM}
                                   for _, _, ix in ordered_instructions(tx)):
                            continue
                        items.append({'slot': slot, 'tx_index': index, 'tx': tx,
                                      'blockTime': block['blockTime'], 'raw_sha256': raw_hash,
                                      'rows': grouped.get(index, [])})
    loaded_at = time.perf_counter()
    if not items:
        raise ValueError('No target transactions')
    for item in items[:20]:
        replay_one(item, decoders)
    details, timings, residuals, pauses, slowest = [], [], [], [], []
    associations = Counter()
    collection_started = None
    def collection_event(phase, info):
        nonlocal collection_started
        if phase == 'start':
            collection_started = time.perf_counter()
        elif phase == 'stop' and collection_started is not None:
            pauses.append({'seconds': time.perf_counter()-collection_started,
                           'generation': info['generation']})
            collection_started = None
    replay_start = time.perf_counter()
    gc.callbacks.append(collection_event)
    try:
        for item in items:
            before = len(pauses)
            rows, result, timing = replay_one(item, decoders)
            pause_seconds = sum(p['seconds'] for p in pauses[before:])
            if rows != item['rows']:
                raise ValueError('Single-transaction and block decoder results differ')
            timings.append(timing)
            slowest.append({'slot': item['slot'], 'tx_index': item['tx_index'],
                            'combined_ms': timing[2]*1000, 'gc_pause_ms': pause_seconds*1000})
            details.append({'slot': item['slot'], 'tx_index': item['tx_index'],
                            'signature': item['tx']['transaction']['signatures'][0], **result})
    finally:
        gc.callbacks.remove(collection_event)
    replay_end = time.perf_counter()
    result_hash = digest(details)
    if result_hash != expected['details_sha256']:
        raise ValueError('Economic results differ from pinned checkpoint')
    for item, result in zip(items, details):
        if result['lamport_check']['status'] != 'LAMPORTS_RECONCILED':
            row = diagnose_residual(item, result)
            residuals.append(row)
            associations[' + '.join(row['associated_programs']) or 'OTHER'] += 1
    decoded, ledger, combined = zip(*timings)
    return {
        'schema': 'economic-runtime-diagnosis-v1', 'pilot_ready': False,
        'network_requests': 0, 'artifact_sha256': verified['artifact_sha256'],
        'details_sha256': result_hash, 'checkpoint_results_unchanged': True,
        'counts': {'blocks': len(block_times), 'all_transactions': total_transactions,
                   'decoded_events': decoded_count, 'target_transactions': len(items),
                   'sol_reconciled': len(items)-len(residuals), 'sol_unresolved': len(residuals),
                   'fees': dict(Counter(f['status'] for r in details for f in r['fee_checks']))},
        'environment': {'python': platform.python_version(), 'machine': platform.machine(),
                        'system': platform.system(), 'parallel_workers': 1},
        'timing': {'clock': 'perf_counter wall time; GC left enabled', 'warmup_transactions': min(20,len(items)),
                   'archive_integrity_seconds': verified_at-started,
                   'load_select_and_decode_all_blocks_seconds': loaded_at-verified_at,
                   'decode_all_blocks_seconds': sum(block_decode_seconds),
                   'target_replay_loop_seconds': replay_end-replay_start,
                   'target_transactions_per_second': len(items)/(replay_end-replay_start),
                   'single_transaction_decode': distribution(decoded),
                   'single_transaction_ledger': distribution(ledger),
                   'single_transaction_combined': distribution(combined),
                   'gc_pauses_during_replay': pauses,
                   'slowest_transactions': sorted(slowest, key=lambda r: r['combined_ms'], reverse=True)[:10],
                   'entire_diagnostic_seconds': time.perf_counter()-started},
        'sample_block_time_span_seconds': max(block_times)-min(block_times),
        'limitations': ['Offline fixed sample, not a live load test or production SLA.',
                       'Per-transaction timings exclude JSON loading, artifact verification, RPC and queueing.',
                       'Combined timings include event decoding, token/SOL replay and AMM fee checks.',
                       'Archive verification is measured separately and always runs before this benchmark.',
                       'Program association and balanced residuals do not prove a movement or a fee formula.',
                       'Existing historical reserve, binary/config, census and upstream gates remain open.'],
        'residual_groups': dict(associations), 'residuals': residuals}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('artifact', type=Path)
    parser.add_argument('--checkpoint', type=Path, default=Path('reports/TOKEN_LIFECYCLE_VERIFICATION.json'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    report = diagnose(args.artifact, json.loads(args.checkpoint.read_text()))
    args.out.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'residuals'}, indent=2))
