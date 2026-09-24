"""Offline independent rehash of an Actions artifact; never trusts status alone."""
import argparse
import hashlib
import io
import json
import zipfile
from pathlib import Path
from compare_second_source import compare, PHASE_B_SLOTS


def verify(path):
    reference_raw = Path('configs/second_source_reference41.json').read_bytes()
    reference = json.loads(reference_raw)
    blocks, reports = {}, []
    with zipfile.ZipFile(path) as outer:
        for entry in outer.namelist():
            if entry.endswith('comparison.json'):
                reports.append(json.loads(outer.read(entry)))
            elif entry.endswith('.zip'):
                with zipfile.ZipFile(io.BytesIO(outer.read(entry))) as part:
                    if part.testzip() is not None:
                        raise ValueError('Damaged evidence part')
                    for name in part.namelist():
                        if name == 'comparison.json':
                            reports.append(json.loads(part.read(name)))
                        elif name.endswith('.json'):
                            slot = int(Path(name).stem)
                            if slot in blocks:
                                raise ValueError('Duplicate evidence slot')
                            blocks[slot] = part.read(name)
    if not reports or any(r != reports[0] for r in reports):
        raise ValueError('Missing or inconsistent checkpoint reports')
    report = reports[0]
    if report['reference_sha256'] != hashlib.sha256(reference_raw).hexdigest():
        raise ValueError('Different reference file')
    if sorted(blocks) != list(PHASE_B_SLOTS) or sorted(map(int, report['slots'])) != list(PHASE_B_SLOTS):
        raise ValueError('Incomplete 41-block evidence')
    results = {}
    for slot, raw in sorted(blocks.items()):
        if hashlib.sha256(raw).hexdigest() != report['slots'][str(slot)]['raw_sha256']:
            raise ValueError(f'Raw evidence hash mismatch: {slot}')
        result = compare(json.loads(raw)['result'], reference['slots'][str(slot)])
        if result['status'] != 'MATCH':
            raise ValueError(f'Comparison mismatch: {slot}')
        recorded = {k:v for k,v in report['slots'][str(slot)].items() if k != 'raw_sha256'}
        if result != recorded:
            raise ValueError(f'Recomputed report differs: {slot}')
        results[str(slot)] = {'raw_sha256': hashlib.sha256(raw).hexdigest(), **result}
    return {'status': 'VERIFIED_41_BLOCKS', 'artifact_sha256': hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            'reference_sha256': report['reference_sha256'], 'network_requests_for_verification': 0,
            'slots': results}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('artifact', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    verified = verify(args.artifact)
    args.out.write_text(json.dumps(verified, indent=2)+'\n')
    print(verified['status'])
