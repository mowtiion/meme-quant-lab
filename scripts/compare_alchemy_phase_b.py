"""Bounded 41-slot archive comparison. No retries, purchases, or trading."""
import hashlib
import json
import os
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from compare_second_source import call, compare, package_phase_b, PHASE_B_SLOTS


def main():
    key = os.environ.get('ALCHEMY_API_KEY', '').strip()
    if not key or len(key) > 256 or any(c.isspace() for c in key) or '://' in key:
        print('ALCHEMY_API_KEY must contain the API key, not an endpoint URL.')
        return 2
    endpoint = 'https://solana-mainnet.g.alchemy.com/v2/' + urllib.parse.quote(key, safe='')
    source = Path('configs/second_source_reference41.json').read_bytes()
    reference = json.loads(source)
    slots = PHASE_B_SLOTS
    if sorted(map(int, reference['slots'])) != list(slots):
        raise RuntimeError('Frozen slot range changed')
    out = Path('data/secondary') / ('alchemy41-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True, exist_ok=False)
    max_bytes, max_seconds = 192 * 1024 * 1024, 600
    report = {'provider': 'Alchemy', 'status': 'INCOMPLETE', 'requests': 0,
              'raw_bytes': 0, 'slots': {}, 'reference_sha256': hashlib.sha256(source).hexdigest(),
              'limits': {'requests': 42, 'response_bytes': max_bytes, 'network_seconds': max_seconds}}
    deadline = time.monotonic() + max_seconds

    def checkpoint():
        (out / 'comparison.json').write_text(json.dumps(report, indent=2) + '\n')

    def request(method, params):
        if report['requests'] >= 42:
            raise RuntimeError('Request budget reached')
        report['requests'] += 1
        envelope, raw = call(endpoint, method, params, deadline, max_bytes-report['raw_bytes'])
        report['raw_bytes'] += len(raw)
        if key.encode() in raw:
            raise RuntimeError('Credential unexpectedly present in response')
        return envelope['result'], raw

    try:
        found, _ = request('getBlocks', [slots[0], slots[-1], {'commitment': 'finalized'}])
        if found != list(slots):
            raise RuntimeError('Slot enumeration differs from frozen reference')
        for slot in slots:
            block, raw = request('getBlock', [slot, {'encoding': 'json', 'transactionDetails': 'full',
                                  'rewards': False, 'commitment': 'finalized',
                                  'maxSupportedTransactionVersion': 1}])
            if block is None:
                raise RuntimeError(f'Block {slot} is null')
            (out / f'{slot}.json').write_bytes(raw)
            result = compare(block, reference['slots'][str(slot)])
            result['raw_sha256'] = hashlib.sha256(raw).hexdigest()
            report['slots'][str(slot)] = result
            checkpoint()
            print(slot, result['status'], result.get('comparison_mode'), flush=True)
            if result['status'] != 'MATCH':
                report['status'] = 'MISMATCH'
                break
        else:
            report['status'] = 'MATCH_FOR_41_BLOCKS'
    except RuntimeError as exc:
        report['issue'] = str(exc)
    finally:
        checkpoint()
        package_phase_b(out, tuple(map(int, report['slots'])))
    print('Status:', report['status'], '| requests:', report['requests'])
    if 'issue' in report:
        print('Issue:', report['issue'])
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a') as handle:
            handle.write(f"## Alchemy phase B\n\nStatus: **{report['status']}**\n\n"
                         f"Blocks: {len(report['slots'])}/41; requests: {report['requests']}/42.\n"
                         'Raw evidence and the checkpoint report are in the run artifact.\n')
    return 0 if report['status'] == 'MATCH_FOR_41_BLOCKS' else 2


if __name__ == '__main__':
    sys.exit(main())
