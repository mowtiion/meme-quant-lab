"""Two-block, read-only eligibility check for Alchemy's Solana archive.

The API key comes from an Actions repository secret or a hidden local prompt.
An archival marketing claim is not evidence of complete transaction logs.
"""
import getpass
import hashlib
import json
import os
import sys
import time
import urllib.parse
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from compare_second_source import call, compare


SLOTS = (449382002, 449382004)
REFERENCE = Path('configs/second_source_reference41.json')
LIMIT_BYTES = 24 * 1024 * 1024
LIMIT_SECONDS = 90
LONG_LOG_SIGNATURES = {
    449382002: '4g5kQkyRPv8GW1gEzChsbsZE2VAVrLjeTYvPuE2JR9nFGkB4AvJ6XDjDEMF4puUNJYEf9914hnxEFjuGuNv89tDL',
    449382004: '2J7w6SASpjH3bHuP64HJY3GqkTU8wqgdtsu3uTPM1a5p8A6JwxC3PTBS8orQVaHQwuo63c8ua4qQhF2XiMeNZEKw',
}


def main():
    key = (os.environ.get('ALCHEMY_API_KEY') or
           getpass.getpass('Alchemy API-key (blijft lokaal): ')).strip()
    if not key or len(key) > 256 or any(c.isspace() for c in key):
        print('Ongeldige sleutel; geen verzoek verzonden.')
        return 2
    endpoint = 'https://solana-mainnet.g.alchemy.com/v2/' + urllib.parse.quote(key, safe='')
    expected = json.loads(REFERENCE.read_text())
    out = Path('data/secondary') / ('alchemy-probe-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True, exist_ok=False)
    report = {'provider': 'Alchemy', 'endpoint_host': 'solana-mainnet.g.alchemy.com',
              'requests': 0, 'response_bytes': 0, 'limits': {'requests': 2,
              'response_bytes': LIMIT_BYTES, 'network_seconds': LIMIT_SECONDS},
              'slots': {}, 'status': 'INCOMPLETE'}
    deadline = time.monotonic() + LIMIT_SECONDS
    try:
        for slot in SLOTS:
            report['requests'] += 1
            envelope, raw = call(endpoint, 'getBlock', [slot, {
                'encoding': 'json', 'transactionDetails': 'full', 'rewards': False,
                'commitment': 'finalized', 'maxSupportedTransactionVersion': 1}],
                deadline, LIMIT_BYTES - report['response_bytes'])
            report['response_bytes'] += len(raw)
            if key.encode() in raw:
                raise RuntimeError('Credential unexpectedly present in response')
            block = envelope['result']
            if block is None:
                raise RuntimeError(f'Block {slot} is null')
            (out / f'{slot}.json').write_bytes(raw)
            result = compare(block, expected['slots'][str(slot)])
            by_sig = {tx['transaction']['signatures'][0]: tx for tx in block['transactions']}
            tx = by_sig.get(LONG_LOG_SIGNATURES[slot])
            logs = tx['meta'].get('logMessages') if tx and tx.get('meta') else None
            result.update({'raw_sha256': hashlib.sha256(raw).hexdigest(),
                           'long_log_lines': len(logs) if isinstance(logs, list) else None,
                           'long_log_truncated': (not isinstance(logs, list) or
                                                  any('Log truncated' in line for line in logs))})
            report['slots'][str(slot)] = result
            if result['status'] != 'MATCH' or result['long_log_truncated']:
                report['status'] = 'MISMATCH'
                break
        else:
            report['status'] = 'MATCH_FOR_TWO_BLOCKS'
    except RuntimeError as exc:
        report['issue'] = str(exc)
    finally:
        (out / 'comparison.json').write_text(json.dumps(report, indent=2) + '\n')
    archive = out / 'evidence.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.write(out / 'comparison.json', 'comparison.json')
        for slot in report['slots']:
            z.write(out / f'{slot}.json', f'{slot}.json')
    print('Status:', report['status'], '| verzoeken:', report['requests'])
    if 'issue' in report:
        print('Fout:', report['issue'])
    print('Rapport:', out / 'comparison.json')
    print('Bewijs:', archive)
    return 0 if report['status'] == 'MATCH_FOR_TWO_BLOCKS' else 2


if __name__ == '__main__':
    sys.exit(main())
