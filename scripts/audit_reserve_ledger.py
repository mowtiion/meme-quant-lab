"""Offline reserve-ledger pilot on the already verified Alchemy 41-block artifact."""
import argparse
import hashlib
import io
import json
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from compare_second_source import digest
from verify_alchemy_phase_b import verify
from meme_quant.decoder import AMM, IDLDecoder, decode_block
from meme_quant.reserve_ledger import reconcile_pool_transaction


def audit(path):
    verified = verify(path)
    decoder = IDLDecoder(Path('vendor/pump_amm.json'))
    details, decode_issues = [], []
    with zipfile.ZipFile(path) as outer:
        for entry in outer.namelist():
            if not entry.endswith('.zip'):
                continue
            with zipfile.ZipFile(io.BytesIO(outer.read(entry))) as part:
                for name in part.namelist():
                    if not name.endswith('.json') or name == 'comparison.json':
                        continue
                    slot = int(Path(name).stem); raw = part.read(name)
                    block = json.loads(raw)['result']
                    rows, issues = decode_block(block, slot, hashlib.sha256(raw).hexdigest(), {AMM: decoder})
                    decode_issues.extend(issues)
                    by_tx = defaultdict(list)
                    for row in rows:
                        by_tx[row['tx_index']].append(row)
                    for index, events in by_tx.items():
                        for result in reconcile_pool_transaction(block['transactions'][index], events, decoder):
                            details.append({'slot': slot, 'tx_index': index, **result})
    counts = Counter(row['status'] for row in details)
    reasons = Counter(row['reason'] for row in details if row['status'] != 'RECONCILED')
    return {'status': 'SCOPED_RESERVE_AUDIT', 'artifact_sha256': verified['artifact_sha256'],
            'decoder_sha256': decoder.hash, 'network_requests': 0,
            'counts': dict(counts), 'unresolved_reasons': dict(reasons),
            'reconciled_events': sum(r['event_count'] for r in details if r['status'] == 'RECONCILED'),
            'decode_issues': decode_issues, 'details_sha256': digest(details), 'details': details,
            'full_historical_ledger': False,
            'scope': 'Transaction-bounded ordinary PumpSwap vault flows. Does not validate pricing, all fee recipients, mint/burn/transfer supply ledger, or continuity between transactions.'}


def summary(result):
    details = result['details']
    compact = {k:v for k,v in result.items() if k != 'details'}
    compact['ordinary_vault_flow_gate'] = ('PASS' if result['reconciled_events'] > 0
        and not result['decode_issues'] and set(result['unresolved_reasons']) <= {'PROTOCOL_BURN_SEPARATE_LEDGER'} else 'BLOCKED')
    compact['unique_reconciled_pools'] = len({r['pool'] for r in details if r['status'] == 'RECONCILED'})
    compact['multi_action_groups'] = sum(r['status'] == 'RECONCILED' and r['event_count'] > 1 for r in details)
    compact['slots'] = {}
    for slot in sorted({r['slot'] for r in details}):
        rows = [r for r in details if r['slot'] == slot]
        compact['slots'][str(slot)] = {'counts': dict(Counter(r['status'] for r in rows)),
                                      'ledger_sha256': digest(rows)}
    compact['unresolved'] = [r for r in details if r['status'] != 'RECONCILED']
    compact['examples'] = []
    for kind in ('BuyEvent', 'SellEvent', 'multi_action'):
        for row in details:
            if row['status'] == 'RECONCILED' and ((kind == 'multi_action' and row['event_count'] > 1)
                 or (kind != 'multi_action' and row['event_count'] == 1 and row['steps'][0]['kind'] == kind)):
                compact['examples'].append(row)
                break
    return compact


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('artifact', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--summary-only', action='store_true')
    args = parser.parse_args()
    result = audit(args.artifact)
    if args.summary_only:
        result = summary(result)
    args.out.write_text(json.dumps(result, indent=2)+'\n')
    print(result['counts'], result['unresolved_reasons'], result['reconciled_events'])
