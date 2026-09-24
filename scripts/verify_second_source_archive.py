"""Offline verification of a bounded, user-provided three-block evidence ZIP."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path

from compare_second_source import compare

MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
SLOTS = ('447000000', '447000001', '447000002')


def verify(archive: Path, reference: Path) -> dict:
    expected = json.loads(reference.read_bytes())
    if set(expected['slots']) != set(SLOTS): raise ValueError('Reference slot mismatch')
    archive_bytes = archive.read_bytes()
    if len(archive_bytes) > MAX_ARCHIVE_BYTES:
        raise ValueError('Archive size budget exceeded')
    with zipfile.ZipFile(archive) as z:
        infos = z.infolist()
        if (len(infos) != 4 or {i.filename for i in infos} !=
                {s + '.json' for s in SLOTS} | {'comparison.json'}
                or any(i.file_size > 10*1024*1024 for i in infos)
                or sum(i.file_size for i in infos) > MAX_ARCHIVE_BYTES):
            raise ValueError('Unexpected archive entries or sizes')
        if z.testzip() is not None: raise ValueError('Damaged ZIP entry')
        report_bytes = z.read('comparison.json')
        report = json.loads(report_bytes)
        if (report['status'] != 'MATCH' or report['provider'] != 'Helius'
                or report['endpoint_host'] != 'mainnet.helius-rpc.com'
                or report['reference_manifest_sha256'] != expected['manifest_sha256']
                or report['requests'] != 4 or set(report['slots']) != set(SLOTS)):
            raise ValueError('Unmatched report metadata')
        rows={}; raw_total=0
        for slot in SLOTS:
            raw = z.read(slot + '.json')
            raw_total += len(raw)
            raw_hash = hashlib.sha256(raw).hexdigest()
            if raw_hash != report['slots'][slot]['raw_sha256']:
                raise ValueError(f'Raw hash mismatch at slot {slot}')
            result = json.loads(raw)['result']
            checked = compare(result, expected['slots'][slot])
            if (checked['status'] != 'MATCH' or checked['transactions'] !=
                    report['slots'][slot]['transactions'] or not all(checked['groups'].values())
                    or checked['groups'] != report['slots'][slot]['groups']):
                raise ValueError(f'Semantic mismatch at slot {slot}')
            rows[slot]={'raw_sha256': raw_hash, 'transactions': checked['transactions'],
                        'verified_groups': len(checked['groups'])}
        if raw_total >= report['raw_bytes'] or report['raw_bytes'] > MAX_ARCHIVE_BYTES:
            raise ValueError('Incorrect response byte accounting')
    return {'status':'MATCH','archive_sha256':hashlib.sha256(archive_bytes).hexdigest(),
            'archive_bytes':len(archive_bytes),'original_report_sha256':hashlib.sha256(report_bytes).hexdigest(),
            'reference_manifest_sha256':expected['manifest_sha256'],'primary_and_helius_same_contents':True,
            'upstream_independence':'UNPROVEN','full_census':'UNPROVEN','continue_to_exp001':False,
            'reported_requests':report['requests'],'reported_response_bytes':report['raw_bytes'],
            'raw_block_bytes':raw_total,'slots':rows}


def main():
    p=argparse.ArgumentParser(description='Offline three-block Helius raw archive comparison')
    p.add_argument('--archive',type=Path,required=True)
    p.add_argument('--reference',type=Path,default=Path('configs/second_source_reference.json'))
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    if args.out.exists():p.error('Output already exists')
    result=verify(args.archive,args.reference)
    args.out.write_text(json.dumps(result,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':result['status'],'blocks':len(result['slots']),
                      'archive_sha256':result['archive_sha256']}))


if __name__=='__main__': main()
