"""Offline token-flow audit for every successful Pump/PumpSwap invocation in the sample."""
import argparse
import hashlib
import io
import json
import zipfile
from collections import Counter
from pathlib import Path
from compare_second_source import digest
from verify_alchemy_phase_b import verify
from meme_quant.decoder import PUMP, AMM, IDLDecoder, decode_block
from meme_quant.reserve_ledger import account_keys
from meme_quant.fee_audit import audit_amm_fees
from meme_quant.token_ledger import ordered_instructions, reconcile_token_accounts


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
                    for index, tx in enumerate(block['transactions']):
                        if tx['meta'] is None:
                            continue
                        keys = account_keys(tx)
                        if not any(keys[ix['programIdIndex']] in {PUMP, AMM} for _, _, ix in ordered_instructions(tx)):
                            continue
                        if tx['meta']['err'] is not None:
                            failed += 1
                            continue
                        result = reconcile_token_accounts(tx)
                        result['fee_checks'] = audit_amm_fees(tx,[r for r in decoded if r['tx_index']==index],decoders[AMM])
                        details.append({'slot': slot, 'tx_index': index,
                                        'signature': tx['transaction']['signatures'][0], **result})
    return {'artifact_sha256': verified['artifact_sha256'], 'status': 'SCOPED_TOKEN_FLOW_AUDIT',
            'network_requests': 0, 'failed_target_transactions_excluded': failed, 'details': details,
            'counts': dict(Counter(r['status'] for r in details)), 'details_sha256': digest(details),
            'transaction_reasons': dict(Counter(r['reason'] for r in details if 'reason' in r)),
            'account_counts': dict(Counter(a['status'] for r in details for a in r['accounts'])),
            'account_reasons': dict(Counter(a['reason'] for r in details for a in r['accounts'] if 'reason' in a)),
            'flow_counts': dict(Counter(f['kind'] for r in details for f in r['flows'])),
            'unknown_instructions': dict(Counter(str(u['tag']) for r in details for u in r['unknown'])),
            'fee_counts': dict(Counter(f['status'] for r in details for f in r['fee_checks'])),
            'fee_reasons': dict(Counter(f['reason'] for r in details for f in r['fee_checks'] if 'reason' in f)),
            'full_supply_or_lamport_ledger': False}


def summary(result):
    out = {k:v for k,v in result.items() if k != 'details'}
    out['slots'] = {}
    for slot in sorted({r['slot'] for r in result['details']}):
        rows = [r for r in result['details'] if r['slot']==slot]
        out['slots'][str(slot)] = {'transactions':len(rows), 'sha256':digest(rows)}
    out['unresolved_examples'] = []
    out['protocol_burns'] = [{'slot':r['slot'], 'signature':r['signature'], **f}
        for r in result['details'] for f in r['fee_checks'] if f['status']=='PROTOCOL_BURN_RECONCILED']
    out['core_fee_examples'] = [{'slot':r['slot'], 'signature':r['signature'], **f}
        for r in result['details'] for f in r['fee_checks'] if f['status']=='CORE_FEES_RECONCILED'][:2]
    seen = set()
    for r in result['details']:
        for a in r['accounts']:
            if a.get('reason') and a['reason'] not in seen:
                seen.add(a['reason'])
                out['unresolved_examples'].append({'slot':r['slot'],'signature':r['signature'],**a})
    return out


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('artifact',type=Path); p.add_argument('--out',type=Path,required=True)
    p.add_argument('--summary-only', action='store_true'); args=p.parse_args()
    result=audit(args.artifact)
    args.out.write_text(json.dumps(summary(result) if args.summary_only else result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary(result).items() if k not in ('slots','unresolved_examples')},indent=2))
