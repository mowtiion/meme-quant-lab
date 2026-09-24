"""Offline verification of the six bounded Phase B Helius evidence archives."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path

from compare_second_source import compare


SLOTS = tuple(range(449382000, 449382041))
MAX_BYTES = 192 * 1024 * 1024
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024


def verify(archives: list[Path], reference_path: Path):
    reference=json.loads(reference_path.read_bytes())
    assert set(reference['slots']) == {str(s) for s in SLOTS}
    if len(archives)!=6 or len({p.name for p in archives})!=6:
        raise ValueError('Exactly six distinct archive parts required')
    archive_hashes={}; blocks={}; report_raw=None; total=0
    for part_index in range(6):
        name=f'evidence-{part_index+1:02d}.zip'
        matching=[p for p in archives if p.name==name]
        if len(matching)!=1:raise ValueError(f'Missing archive part {name}')
        path=matching[0];blob=path.read_bytes();archive_hashes[name]=hashlib.sha256(blob).hexdigest()
        if len(blob)>32*1024*1024 or sum(p.stat().st_size for p in archives)>MAX_ARCHIVE_BYTES:
            raise ValueError('Archive byte budget exceeded')
        part_slots=SLOTS[part_index*8:(part_index+1)*8]
        with zipfile.ZipFile(path) as z:
            infos=z.infolist()
            if (len(infos)!=len(part_slots)+1 or
                    {i.filename for i in infos}!={'comparison.json'}|{f'{s}.json' for s in part_slots} or
                    any(i.file_size>10*1024*1024 for i in infos) or
                    sum(i.file_size for i in infos)>MAX_BYTES):
                raise ValueError(f'Invalid archive entries in {name}')
            if z.testzip() is not None:raise ValueError(f'Damaged archive part {name}')
            candidate=z.read('comparison.json')
            if report_raw is None:report_raw=candidate
            elif report_raw!=candidate:raise ValueError('Comparison report differs across parts')
            report=json.loads(report_raw)
            if (report['status']!='MATCH' or report['provider']!='Helius' or
                    report['endpoint_host']!='mainnet.helius-rpc.com' or
                    report['reference_manifest_sha256']!=reference['manifest_sha256'] or
                    report['requests']!=42 or set(report['slots'])!={str(s) for s in SLOTS} or
                    report.get('limits')!={'requests':42,'response_bytes':MAX_BYTES,'network_seconds':600}):
                raise ValueError('Comparison report metadata mismatch')
            for slot in part_slots:
                raw=z.read(f'{slot}.json');total+=len(raw)
                if total>MAX_BYTES:raise ValueError('Raw byte budget exceeded')
                raw_hash=hashlib.sha256(raw).hexdigest()
                entry=report['slots'][str(slot)]
                if raw_hash!=entry['raw_sha256']:raise ValueError(f'Raw hash mismatch in {slot}')
                outcome=compare(json.loads(raw)['result'],reference['slots'][str(slot)])
                if (outcome['status']!='MATCH' or outcome['transactions']!=entry['transactions']
                        or outcome['groups']!=entry['groups'] or not all(outcome['groups'].values())):
                    raise ValueError(f'Semantic mismatch in {slot}')
                blocks[str(slot)]={'raw_sha256':raw_hash,'transactions':outcome['transactions'],
                                   'verified_groups':len(outcome['groups'])}
    if not total<report['raw_bytes']<=MAX_BYTES:
        raise ValueError('Incorrect response byte accounting')
    return {'status':'MATCH','reference_manifest_sha256':reference['manifest_sha256'],
            'archive_sha256':archive_hashes,'original_report_sha256':hashlib.sha256(report_raw).hexdigest(),
            'requests':report['requests'],'raw_block_bytes':total,'reported_response_bytes':report['raw_bytes'],
            'blocks':blocks,'upstream_independence':'UNPROVEN','full_census':'UNPROVEN',
            'continue_to_exp001':False}


def main():
    parser=argparse.ArgumentParser(description='Verify six Helius evidence ZIPs offline')
    parser.add_argument('archives',type=Path,nargs=6)
    parser.add_argument('--reference',type=Path,default=Path('configs/second_source_reference41.json'))
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if args.out.exists():parser.error('Output already exists')
    report=verify(args.archives,args.reference)
    args.out.write_text(json.dumps(report,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'blocks':len(report['blocks'])}))


if __name__=='__main__':main()
