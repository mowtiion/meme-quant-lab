"""Combined offline economic checkpoint on hash-verified historical evidence."""
import argparse
import hashlib
import io
import json
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from compare_second_source import digest
from verify_alchemy_phase_b import verify
from meme_quant.decoder import PUMP, AMM, IDLDecoder, decode_block
from meme_quant.reserve_ledger import account_keys
from meme_quant.economic import audit_transaction
from meme_quant.token_ledger import ordered_instructions


def audit(path):
    verified = verify(path)
    details = []; failed = 0
    decoders = {d.program:d for d in (IDLDecoder(Path('vendor/pump.json')), IDLDecoder(Path('vendor/pump_amm.json')))}
    with zipfile.ZipFile(path) as outer:
        for entry in outer.namelist():
            if not entry.endswith('.zip'):
                continue
            with zipfile.ZipFile(io.BytesIO(outer.read(entry))) as part:
                for name in part.namelist():
                    if name == 'comparison.json' or not name.endswith('.json'):
                        continue
                    slot = int(Path(name).stem); raw = part.read(name); block = json.loads(raw)['result']
                    decoded, decode_issues = decode_block(block,slot,hashlib.sha256(raw).hexdigest(),decoders)
                    if decode_issues:
                        raise ValueError('Decoder issues block fee attribution')
                    by_transaction = defaultdict(list)
                    for row in decoded:
                        by_transaction[row['tx_index']].append(row)
                    for index, tx in enumerate(block['transactions']):
                        if tx['meta'] is None:
                            continue
                        keys = account_keys(tx)
                        if not any(keys[ix['programIdIndex']] in {PUMP, AMM} for _, _, ix in ordered_instructions(tx)):
                            continue
                        if tx['meta']['err'] is not None:
                            failed += 1
                            continue
                        result = audit_transaction(tx, by_transaction[index], decoders)
                        details.append({'slot': slot, 'tx_index': index,
                                        'signature': tx['transaction']['signatures'][0], **result})
    return {'artifact_sha256': verified['artifact_sha256'], 'status': 'ECONOMIC_CHECKPOINT_BLOCKED',
            'network_requests': 0, 'failed_target_transactions_excluded': failed, 'details': details,
            'counts': dict(Counter(r['status'] for r in details)), 'details_sha256': digest(details),
            'transaction_reasons': dict(Counter(r['reason'] for r in details if 'reason' in r)),
            'account_counts': dict(Counter(a['status'] for r in details for a in r['accounts'])),
            'account_reasons': dict(Counter(a['reason'] for r in details for a in r['accounts'] if 'reason' in a)),
            'flow_counts': dict(Counter(f['kind'] for r in details for f in r['flows'])),
            'unknown_instructions': dict(Counter(str(u['tag']) for r in details for u in r['unknown'])),
            'fee_counts': dict(Counter(f['status'] for r in details for f in r['fee_checks'])),
            'fee_reasons': dict(Counter(f['reason'] for r in details for f in r['fee_checks'] if 'reason' in f)),
            'lamport_counts':dict(Counter(r['lamport_check']['status'] for r in details)),
            'lamport_reasons':dict(Counter(r['lamport_check']['reason'] for r in details if 'reason' in r['lamport_check'])),
            'native_boundary_counts_in_sol_passes':dict(Counter(a['status'] for r in details
                if r['lamport_check']['status']=='LAMPORTS_RECONCILED'
                for a in r['lamport_check'].get('native_token_boundaries',[]))),
            'direct_movement_counts_in_sol_passes':dict(Counter(m['kind'] for r in details
                if r['lamport_check']['status']=='LAMPORTS_RECONCILED' for m in r['lamport_check']['movements']
                if m['kind'].startswith(('pump_','migration_','flash_','router_')) or m['kind'] in ('close_volume_account','claim_cashback','unwrap_lamports'))),
            'fee_variant_counts':{'cashback':sum(bool(f.get('cashback')) for r in details for f in r['fee_checks'] if f['status']=='CORE_FEES_RECONCILED'),
                'holder_rewards':sum(bool(f.get('holder_rewards')) for r in details for f in r['fee_checks'] if f['status']=='CORE_FEES_RECONCILED'),
                'multi_event_transactions':sum(len(r['fee_checks'])>1 and all(f['status']=='CORE_FEES_RECONCILED' for f in r['fee_checks']) for r in details)},
            'pilot_ready':False,'full_supply_or_lamport_ledger':False,
            'sync_native_stored_reserve_verified':False,'historical_global_config_verified':False}


def summary(result):
    out={k:v for k,v in result.items() if k!='details'}
    out['slots']={}
    for slot in sorted({r['slot'] for r in result['details']}):
        rows=[r for r in result['details'] if r['slot']==slot]
        out['slots'][str(slot)]={'transactions':len(rows),'sha256':digest(rows),
            'lamport_counts':dict(Counter(r['lamport_check']['status'] for r in rows)),
            'fee_counts':dict(Counter(f['status'] for r in rows for f in r['fee_checks']))}
    out['lamport_unresolved']=[]
    for r in result['details']:
        l=r['lamport_check']
        if l['status']!='LAMPORTS_RECONCILED':
            out['lamport_unresolved'].append({'slot':r['slot'],'tx_index':r['tx_index'],'signature':r['signature'],
                'status':l['status'],'reason':l.get('reason'),'mismatches':l['mismatches'],
                'blocked_movement':l.get('blocked_movement')})
    out['fee_unresolved']=[{'slot':r['slot'],'tx_index':r['tx_index'],**f} for r in result['details']
        for f in r['fee_checks'] if f['status']=='UNRESOLVED']
    return out


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('artifact',type=Path); p.add_argument('--out',type=Path,required=True)
    p.add_argument('--summary-only', action='store_true'); args=p.parse_args()
    result=audit(args.artifact)
    args.out.write_text(json.dumps(summary(result) if args.summary_only else result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary(result).items() if k not in ('slots','lamport_unresolved','fee_unresolved')},indent=2))
