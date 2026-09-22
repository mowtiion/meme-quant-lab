"""One bounded, resumable read-only collection of the identified historical buffer.

Discovery receipts must already exist. This is not a launch population download.
"""
import json
import time
from pathlib import Path

from meme_quant.rpc import RPC
from meme_quant.storage import store_raw, json_bytes, immutable_write

ROOT=Path('data/raw')
OUT=Path('data/processed/pump-old-buffer-blocks-v1.json')
LIMIT_SLOTS=64
LIMIT_BYTES=256*1024*1024
LIMIT_SECONDS=600

def main():
    receipts=json.loads(Path('data/processed/pump-old-buffer-probe.json').read_text())
    rows=[]
    for r in receipts:
        if r['method']!='getSignaturesForAddress':continue
        h=r['raw_sha256'];rows+=json.loads((ROOT/'objects'/h[:2]/f'{h}.json').read_text())['result']
    slots=sorted({r['slot'] for r in rows})
    if len(slots)>LIMIT_SLOTS:raise ValueError('Slot budget exceeded')
    report={'source':'https://api.mainnet-beta.solana.com','commitment':'finalized',
            'purpose':'historical_program_buffer_reconstruction','buffer':'J7raNSKXB14MeCc6RwXQrKbPJXH4CWh9V4NCnw4Kibtk',
            'selected_slots':slots,'history_receipts':receipts,
            'limits':{'max_slots':LIMIT_SLOTS,'max_bytes':LIMIT_BYTES,'max_seconds':LIMIT_SECONDS},
            'blocks':[],'issues':[],'complete':False}
    if OUT.exists():
        report=json.loads(OUT.read_text())
        if report['selected_slots']!=slots:raise ValueError('Resume discovery changed')
        if report['complete']:print('Already complete');return
        report['issues']=[]
    rpc=RPC(report['source'],attempts=2)
    used=sum(b['bytes'] for b in report['blocks']);done={b['slot'] for b in report['blocks']};started=time.monotonic()
    for slot in slots:
        if slot in done:continue
        if time.monotonic()-started>LIMIT_SECONDS or used>=LIMIT_BYTES:
            report['issues'].append({'slot':slot,'reason':'BUDGET_EXHAUSTED'});break
        try:
            e,raw=rpc.call('getBlock',[slot,{'encoding':'json','transactionDetails':'full','rewards':False,
                                          'commitment':'finalized','maxSupportedTransactionVersion':1}])
            h,_=store_raw(ROOT,raw)
            if e['result'] is None:raise ValueError('NULL_BLOCK')
            used+=len(raw)
            if used>LIMIT_BYTES:raise ValueError('Byte budget exceeded')
            report['blocks'].append({'slot':slot,'raw_sha256':h,'bytes':len(raw)})
        except Exception as exc:
            report['issues'].append({'slot':slot,'reason':str(exc)})
            OUT.write_bytes(json_bytes(report));print(json.dumps(report['issues']),flush=True);break
        OUT.write_bytes(json_bytes(report))
        if len(report['blocks'])%5==0:print(json.dumps({'blocks':len(report['blocks']),'target':len(slots),'bytes':used}),flush=True)
    report['complete']=len(report['blocks'])==len(slots) and not report['issues']
    OUT.write_bytes(json_bytes(report))
    if report['complete']:
        h,_=store_raw(ROOT,json_bytes(report));immutable_write(ROOT/'manifests'/f'{h}.json',json_bytes(report))
        print(json.dumps({'complete':True,'blocks':len(slots),'bytes':used,'manifest_sha256':h}),flush=True)

if __name__=='__main__':main()
