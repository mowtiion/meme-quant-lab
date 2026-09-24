"""Resume a bounded historical buffer collection using already verified discovery.

At most 64 selected slots, 256 MiB stored blocks and 600 seconds per invocation.
Up to two simultaneous public RPC reads; each completed block is checkpointed.
"""
import argparse
import concurrent.futures
import json
import time
from pathlib import Path
from meme_quant.buffer_replay import history_rows
from meme_quant.rpc import RPC
from meme_quant.storage import store_raw, json_bytes


def collect(receipts_path, buffer, out, root=Path('data/raw')):
    receipts=json.loads(receipts_path.read_text())
    rows=history_rows(receipts,root,buffer);slots=sorted({r['slot'] for r in rows})
    if len(slots)>64:raise ValueError('Slot cap exceeded')
    report={'source':'https://api.mainnet-beta.solana.com','commitment':'finalized',
            'purpose':'historical_program_buffer_reconstruction','buffer':buffer,
            'selected_slots':slots,'history_receipts':receipts,'blocks':[], 'issues':[],
            'complete':False,'requests':0,'limits':{'slots':64,'stored_bytes':256*1024*1024,'seconds_per_invocation':600}}
    if out.exists():
        report=json.loads(out.read_text())
        if report['history_receipts']!=receipts or report['buffer']!=buffer or report['selected_slots']!=slots:
            raise ValueError('Resume inputs changed')
        if report['complete']:return report
        report['issues']=[]
    out.parent.mkdir(parents=True,exist_ok=True)
    used=sum(b['bytes'] for b in report['blocks']);done={b['slot'] for b in report['blocks']}
    # Reuse a previously fetched exact block, if its known manifest supplies it.
    for path in root.joinpath('manifests').glob('*.json'):
        manifest=json.loads(path.read_text())
        for b in manifest.get('blocks',[]):
            if b['slot'] in slots and b['slot'] not in done:
                h=b['raw_sha256'];raw=root/'objects'/h[:2]/f'{h}.json'
                if raw.exists():
                    from meme_quant.buffer_replay import read_hashed
                    read_hashed(root,h)
                    report['blocks'].append({'slot':b['slot'],'raw_sha256':h,'bytes':raw.stat().st_size})
                    used+=raw.stat().st_size;done.add(b['slot'])
    pending=[s for s in slots if s not in done];deadline=time.monotonic()+600
    def fetch(slot):
        envelope,raw=RPC(report['source'],attempts=1).call('getBlock',[slot,{
            'encoding':'json','transactionDetails':'full','rewards':False,
            'commitment':'finalized','maxSupportedTransactionVersion':1}])
        if envelope['result'] is None:raise ValueError('NULL_BLOCK')
        return raw
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for start in range(0,len(pending),2):
            if time.monotonic()>=deadline or used>=report['limits']['stored_bytes']:
                report['issues'].append({'reason':'BUDGET_EXHAUSTED'});break
            batch=[(slot,pool.submit(fetch,slot)) for slot in pending[start:start+2]]
            report['requests']+=len(batch)
            for slot,future in batch:
                try:
                    raw=future.result()
                    if used+len(raw)>report['limits']['stored_bytes']:raise ValueError('Stored byte cap exceeded')
                    h,_=store_raw(root,raw);used+=len(raw)
                    report['blocks'].append({'slot':slot,'raw_sha256':h,'bytes':len(raw)})
                except Exception as exc:
                    report['issues'].append({'slot':slot,'reason':str(exc)})
                report['blocks'].sort(key=lambda b:b['slot']);out.write_bytes(json_bytes(report))
            print(json.dumps({'blocks':len(report['blocks']),'target':len(slots),'bytes':used,'issues':report['issues']}),flush=True)
            if report['issues']:break
    report['complete']=len(report['blocks'])==len(slots) and not report['issues']
    out.write_bytes(json_bytes(report));return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--receipts',type=Path,required=True)
    p.add_argument('--buffer',required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();r=collect(a.receipts,a.buffer,a.out)
    print('COMPLETE' if r['complete'] else 'CHECKPOINTED_INCOMPLETE')
