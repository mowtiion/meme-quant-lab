"""Audit native-currency cash flow in the already verified 41-block sample."""
import argparse
import io
import json
import zipfile
from collections import Counter
from pathlib import Path
from compare_second_source import digest
from verify_alchemy_phase_b import verify
from meme_quant.decoder import PUMP, AMM
from meme_quant.reserve_ledger import account_keys
from meme_quant.token_ledger import ordered_instructions, NATIVE
from meme_quant.lamport_ledger import reconcile_lamports


def audit(path):
    verified=verify(path)
    details=[];failed=0
    with zipfile.ZipFile(path) as outer:
        for entry in outer.namelist():
            if not entry.endswith('.zip'):continue
            with zipfile.ZipFile(io.BytesIO(outer.read(entry))) as part:
                for name in part.namelist():
                    if not name.endswith('.json') or name=='comparison.json':continue
                    slot=int(Path(name).stem);block=json.loads(part.read(name))['result']
                    for index,tx in enumerate(block['transactions']):
                        if tx['meta'] is None:continue
                        keys=account_keys(tx)
                        if not any(keys[ix['programIdIndex']] in {PUMP,AMM} for _,_,ix in ordered_instructions(tx)):continue
                        if tx['meta']['err'] is not None:
                            failed+=1;continue
                        result=reconcile_lamports(tx)
                        details.append({'slot':slot,'tx_index':index,'signature':tx['transaction']['signatures'][0],**result})
    passed=[r for r in details if r['status']=='LAMPORTS_RECONCILED']
    return {'status':'SCOPED_LAMPORT_AUDIT','artifact_sha256':verified['artifact_sha256'],
            'network_requests':0,'failed_target_transactions_excluded':failed,'details':details,
            'details_sha256':digest(details),'counts':dict(Counter(r['status'] for r in details)),
            'reasons':dict(Counter(r['reason'] for r in details if 'reason' in r)),
            'reconciled_native_account_observations':sum(len(r['native_accounts']) for r in passed),
            'reconciled_reused_account_observations':sum(len(r.get('reused_accounts',[])) for r in passed),
            'reconciled_lifecycle_counts':dict(Counter(e['kind'] for r in passed for e in r['lifecycles'] if e['kind']=='sync_native' or e['mint']==NATIVE)),
            'rent_assumed':False,'full_economic_ledger':False,
            'sync_token_amounts_independently_verified':False}


def summary(result):
    out={k:v for k,v in result.items() if k!='details'}
    out['slots']={}
    for slot in sorted({r['slot'] for r in result['details']}):
        rows=[r for r in result['details'] if r['slot']==slot]
        out['slots'][str(slot)]={'counts':dict(Counter(r['status'] for r in rows)),'sha256':digest(rows)}
    out['examples']=[];seen=set()
    for row in result['details']:
        tag=row.get('reason',row['status'])
        if row.get('reused_accounts') and row['status']=='LAMPORTS_RECONCILED':tag='RECONCILED_REUSE'
        if tag not in seen:
            seen.add(tag);out['examples'].append(row)
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('artifact',type=Path);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--summary-only',action='store_true');args=p.parse_args()
    result=audit(args.artifact)
    args.out.write_text(json.dumps(summary(result) if args.summary_only else result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='details'},indent=2))
