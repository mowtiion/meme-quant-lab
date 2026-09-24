"""Offline audit of a stopped Helius Phase B artifact against pinned primary blocks.

Run with PYTHONPATH=src; the primary raw-object directory is deliberately not in Git.
This does not turn a scoped event match into full block equivalence.
"""
import argparse
import hashlib
import io
import json
import zipfile
from collections import Counter
from pathlib import Path

from meme_quant.decoder import AMM, PUMP, IDLDecoder, decode_block


MANIFEST = Path('data/raw/manifests/e6f27b744a0dcd838d24de1b916109ac8cd744cdf2103871bc2592d0f90413b5.json')
SCOPED = {PUMP, AMM}


def target_programs(tx):
    message, meta = tx['transaction']['message'], tx['meta']
    keys = [k['pubkey'] if isinstance(k, dict) else k for k in message['accountKeys']]
    loaded = meta.get('loadedAddresses') or {}
    keys += loaded.get('writable', []) + loaded.get('readonly', [])
    ix = list(message['instructions'])
    ix += [item for group in meta.get('innerInstructions') or [] for item in group['instructions']]
    return {keys[item['programIdIndex']] for item in ix}


def event_identities(rows):
    return [(r['tx_index'], r['event_index'], r['program'], r['name'], r['payload']) for r in rows]


def audit(artifact, root):
    pinned = json.loads((root / MANIFEST).read_text())
    raw_sha = {x['slot']: x['raw_sha256'] for x in pinned['blocks']}
    decoders = {d.program: d for d in
                (IDLDecoder(root / 'vendor/pump.json'), IDLDecoder(root / 'vendor/pump_amm.json'))}
    result = {'artifact_sha256': hashlib.sha256(artifact.read_bytes()).hexdigest(),
              'run': 36018149420, 'full_block_equivalence': False,
              'full_41_block_check': False, 'slots': {}}
    with zipfile.ZipFile(artifact) as outer:
        archive = [p for p in outer.namelist() if p.endswith('/evidence-01.zip')]
        report = [p for p in outer.namelist() if p.endswith('/comparison.json')]
        if len(archive) != 1 or len(report) != 1:
            raise ValueError('Unexpected artifact files')
        comparison = json.loads(outer.read(report[0]))
        if comparison['status'] != 'MISMATCH' or comparison['requests'] != 4:
            raise ValueError('Unexpected run status')
        with zipfile.ZipFile(io.BytesIO(outer.read(archive[0]))) as z:
            for slot in (449382000, 449382001, 449382002):
                original = z.read(f'{slot}.json')
                if hashlib.sha256(original).hexdigest() != comparison['slots'][str(slot)]['raw_sha256']:
                    raise ValueError(f'Helius raw hash mismatch: {slot}')
                source_sha = raw_sha[slot]
                source = root / f'data/raw/objects/{source_sha[:2]}/{source_sha}.json'
                primary_bytes = source.read_bytes()
                if hashlib.sha256(primary_bytes).hexdigest() != source_sha:
                    raise ValueError(f'Primary raw hash mismatch: {slot}')
                secondary_block = json.loads(original)['result']
                primary_block = json.loads(primary_bytes)['result']
                if len(secondary_block['transactions']) != len(primary_block['transactions']):
                    raise ValueError('Transaction count differs')
                secondary, si = decode_block(secondary_block, slot, hashlib.sha256(original).hexdigest(), decoders)
                primary, pi = decode_block(primary_block, slot, source_sha, decoders)
                if event_identities(secondary) != event_identities(primary) or si != pi:
                    raise ValueError(f'Target events/issues differ: {slot}')
                truncated = []; null_empty = Counter(); unexpected = []
                for index, (a, b) in enumerate(zip(secondary_block['transactions'], primary_block['transactions'])):
                    if a['transaction'] != b['transaction'] or a['version'] != b['version']:
                        raise ValueError(f'Transaction contents differ: {slot}/{index}')
                    for field in a['meta'].keys() | b['meta'].keys():
                        aa, bb = a['meta'].get(field), b['meta'].get(field)
                        if aa == bb:
                            continue
                        if (field in ('innerInstructions', 'logMessages') and aa == [] and bb is None
                                and a['meta']['err'] == 'MaxLoadedAccountsDataSizeExceeded'
                                and a['meta']['computeUnitsConsumed'] == 0):
                            null_empty[field] += 1
                        elif (field == 'logMessages' and isinstance(aa, list) and
                              aa[-1:] == ['Log truncated'] and isinstance(bb, list) and
                              aa[:-1] == bb[:len(aa)-1]):
                            programs = target_programs(a)
                            truncated.append({'tx_index': index, 'signature': a['transaction']['signatures'][0],
                                              'primary_lines': len(bb), 'secondary_lines': len(aa),
                                              'missing_primary_lines': len(bb) - len(aa) + 1,
                                              'target_program': bool(programs & SCOPED),
                                              'programs': sorted(programs)})
                        else:
                            unexpected.append({'tx_index': index, 'field': field})
                if unexpected or any(x['target_program'] for x in truncated):
                    raise ValueError(f'Unclassified or target-program difference: {slot}')
                result['slots'][str(slot)] = {
                    'transactions': len(secondary_block['transactions']),
                    'matching_target_events': len(primary),
                    'preexecution_null_empty_fields': dict(null_empty),
                    'truncated_unrelated_transactions': truncated,
                    'other_metadata_differences': unexpected}
    result['matching_target_events'] = sum(x['matching_target_events'] for x in result['slots'].values())
    result['scoped_observation'] = 'MATCH_FOR_THREE_INSPECTED_BLOCKS_ONLY'
    risk = Counter({'target_over_10000_bytes': 0, 'unrelated_over_10000_bytes': 0,
                    'primary_target_truncated': 0, 'primary_unrelated_truncated': 0})
    for slot in range(449382000, 449382041):
        source_sha = raw_sha[slot]
        original = (root / f'data/raw/objects/{source_sha[:2]}/{source_sha}.json').read_bytes()
        if hashlib.sha256(original).hexdigest() != source_sha:
            raise ValueError(f'Primary 41-block risk input hash mismatch: {slot}')
        for tx in json.loads(original)['result']['transactions']:
            if tx['meta'] is None:
                continue
            logs = tx['meta'].get('logMessages') or []
            target = bool(target_programs(tx) & SCOPED)
            if any('Log truncated' in line for line in logs):
                risk['primary_target_truncated' if target else 'primary_unrelated_truncated'] += 1
            if len('\n'.join(logs).encode()) > 10000:
                risk['target_over_10000_bytes' if target else 'unrelated_over_10000_bytes'] += 1
    result['primary_41_block_log_risk'] = dict(risk)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('artifact', type=Path)
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error('Output already exists')
    args.out.write_text(json.dumps(audit(args.artifact, args.root), indent=2) + '\n')
