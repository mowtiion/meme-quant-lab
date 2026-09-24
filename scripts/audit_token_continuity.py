"""Audit token boundary continuity in all transactions of the verified 41-block artifact."""
import argparse
import io
import json
import zipfile
from pathlib import Path
from compare_second_source import digest
from verify_alchemy_phase_b import verify
from meme_quant.token_continuity import TokenContinuity


def audit(path):
    verified=verify(path);check=TokenContinuity();seen=[]
    with zipfile.ZipFile(path) as outer:
        # Parts and their members are sorted by slot, not ZIP insertion order.
        parts=[]
        for entry in outer.namelist():
            if not entry.endswith('.zip'):continue
            with zipfile.ZipFile(io.BytesIO(outer.read(entry))) as part:
                names=[n for n in part.namelist() if n.endswith('.json') and n!='comparison.json']
                parts.append((min(int(Path(n).stem) for n in names),entry))
        for _,entry in sorted(parts):
            with zipfile.ZipFile(io.BytesIO(outer.read(entry))) as part:
                names=[n for n in part.namelist() if n.endswith('.json') and n!='comparison.json']
                for name in sorted(names,key=lambda n:int(Path(n).stem)):
                    slot=int(Path(name).stem);seen.append(slot)
                    check.observe_block(slot,json.loads(part.read(name))['result'])
    if seen!=sorted(map(int,verified['slots'])):raise ValueError('CONTINUITY_SLOT_COVERAGE_DIFFERS')
    result=check.result();result.update(artifact_sha256=verified['artifact_sha256'],network_requests=0)
    result['end_states_sha256']=digest(check.last)
    result['issues_sha256']=digest(result['issues'])
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('artifact',type=Path);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();result=audit(args.artifact)
    args.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('slots','issues')},indent=2))
