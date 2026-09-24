"""Reconcile Pump/PumpSwap decoded events in verified Alchemy evidence offline."""
import argparse
import hashlib
import io
import json
import zipfile
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from verify_alchemy_phase_b import verify
from compare_second_source import digest
from meme_quant.decoder import AMM, IDLDecoder, decode_block, normalize_block


def audit(path):
    verified = verify(path)
    reference = json.loads(Path('configs/second_source_reference41.json').read_text())
    decoders = {d.program:d for d in (IDLDecoder(Path('vendor/pump.json')), IDLDecoder(Path('vendor/pump_amm.json')))}
    result = {'status': 'MATCH_FOR_41_BLOCKS', 'artifact_sha256': verified['artifact_sha256'],
              'decoder_hashes': {p:d.hash for p,d in decoders.items()}, 'slots': {},
              'network_requests': 0, 'independent_decoder': False,
              'scope': 'Same pinned decoder on two separately retrieved block datasets; not a full historical census'}
    totals, normalized_totals = Counter(), Counter()
    with zipfile.ZipFile(path) as outer:
        for entry in outer.namelist():
            if not entry.endswith('.zip'):
                continue
            with zipfile.ZipFile(io.BytesIO(outer.read(entry))) as part:
                for name in part.namelist():
                    if name == 'comparison.json' or not name.endswith('.json'):
                        continue
                    slot = int(Path(name).stem)
                    raw = part.read(name)
                    sha = reference['slots'][str(slot)]['raw_sha256']
                    original = Path(f'data/raw/objects/{sha[:2]}/{sha}.json').read_bytes()
                    if hashlib.sha256(original).hexdigest() != sha:
                        raise ValueError('Primary raw hash changed')
                    primary, pi = decode_block(json.loads(original)['result'], slot, sha, decoders)
                    secondary, si = decode_block(json.loads(raw)['result'], slot, hashlib.sha256(raw).hexdigest(), decoders)
                    a = [{k:v for k,v in row.items() if k != 'raw_sha256'} for row in primary]
                    b = [{k:v for k,v in row.items() if k != 'raw_sha256'} for row in secondary]
                    if a != b or pi != si:
                        raise ValueError(f'Decoded event or issue mismatch at {slot}')
                    pn, pni = normalize_block(json.loads(original)['result'], primary, decoders[AMM])
                    sn, sni = normalize_block(json.loads(raw)['result'], secondary, decoders[AMM])
                    pa = [{k:v for k,v in asdict(row).items() if k != 'raw_sha256'} for row in pn]
                    sa = [{k:v for k,v in asdict(row).items() if k != 'raw_sha256'} for row in sn]
                    if pa != sa or pni != sni:
                        raise ValueError(f'Normalized event mismatch at {slot}')
                    normalized_totals.update(row.kind for row in sn)
                    names = Counter(row['name'] for row in secondary)
                    totals.update(names)
                    result['slots'][str(slot)] = {'events': len(secondary), 'event_names': dict(names),
                        'event_sha256': digest(b), 'issues': si,
                        'normalized_events': len(sn), 'normalized_sha256': digest(sa),
                        'normalization_issues': sni}
    result['events'] = sum(totals.values())
    result['event_names'] = dict(totals)
    result['issues'] = sum(len(r['issues']) for r in result['slots'].values())
    result['normalized_events'] = sum(normalized_totals.values())
    result['normalized_kinds'] = dict(normalized_totals)
    result['normalization_issues'] = sum(len(r['normalization_issues']) for r in result['slots'].values())
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('artifact', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.artifact)
    args.out.write_text(json.dumps(result, indent=2)+'\n')
    print(result['status'], '| events:', result['events'], '| issues:', result['issues'])
    print(result['event_names'])
