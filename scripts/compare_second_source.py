"""Bounded, read-only Helius check against three frozen Solana reference blocks.

The key is prompted locally and never written to the report, raw data or Git.
Run from the repository root with Python 3.12; no third-party dependencies.
"""
import getpass
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


REFERENCE = Path('configs/second_source_reference.json')
SLOTS = (447000000, 447000001, 447000002)
MAX_REQUESTS = 4
MAX_TOTAL_BYTES = 32 * 1024 * 1024
MAX_SECONDS = 120
ENDPOINT = 'https://mainnet.helius-rpc.com/?api-key='


def digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def groups(block):
    tx = block['transactions']
    return {
        'header': {k: block[k] for k in ('blockHeight', 'blockTime', 'blockhash',
                                           'parentSlot', 'previousBlockhash')},
        'signatures_and_versions': [(t['transaction']['signatures'], t['version']) for t in tx],
        'messages': [t['transaction']['message'] for t in tx],
        'execution': [{k: t['meta'][k] for k in ('err', 'fee', 'status',
                                                 'computeUnitsConsumed', 'costUnits')} for t in tx],
        'inner_instructions': [t['meta']['innerInstructions'] for t in tx],
        'logs': [t['meta']['logMessages'] for t in tx],
        'loaded_addresses': [t['meta']['loadedAddresses'] for t in tx],
        'balances': [{k: t['meta'][k] for k in ('preBalances', 'postBalances',
                                               'preTokenBalances', 'postTokenBalances')} for t in tx],
        'all_result': block,
    }


def compare(block, expected):
    try:
        count = len(block['transactions'])
        observed = {name: digest(value) for name, value in groups(block).items()}
    except (KeyError, TypeError, ValueError):
        return {'status': 'MISSING_FIELDS', 'transactions': None, 'groups': {}}
    matches = {name: value == expected['group_sha256'][name]
               for name, value in observed.items()}
    return {'status': 'MATCH' if count == expected['transactions'] and all(matches.values())
            else 'MISMATCH', 'transactions': count, 'groups': matches}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def call(endpoint, method, params, deadline, remaining_bytes):
    if time.monotonic() >= deadline:
        raise RuntimeError('Total runtime budget reached')
    payload = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method,
                          'params': params}).encode()
    request = urllib.request.Request(endpoint, data=payload,
                                     headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.build_opener(NoRedirect).open(
                request, timeout=min(25, max(1, deadline-time.monotonic()))) as response:
            chunks = []; size = 0
            while True:
                if time.monotonic() > deadline:
                    raise RuntimeError('Total runtime budget reached')
                chunk = response.read1(min(65536, remaining_bytes - size + 1))
                if not chunk: break
                size += len(chunk)
                if size > remaining_bytes:
                    raise RuntimeError('Response byte budget reached')
                chunks.append(chunk)
            raw = b''.join(chunks)
            if response.headers.get('Content-Length') and int(response.headers['Content-Length']) != size:
                raise RuntimeError('Incomplete HTTP response')
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'HTTP {exc.code}') from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise RuntimeError('Network/timeout failure') from None
    if time.monotonic() > deadline:
        raise RuntimeError('Total runtime budget reached')
    try:
        envelope = json.loads(raw)
    except (UnicodeDecodeError, ValueError):
        raise RuntimeError('Invalid JSON response') from None
    if 'error' in envelope:
        raise RuntimeError(f"RPC error code {envelope['error'].get('code')}")
    if 'result' not in envelope:
        raise RuntimeError('RPC result missing')
    return envelope, raw


def main():
    reference = json.loads(REFERENCE.read_text(encoding='utf-8'))
    if sorted(reference['slots']) != [str(slot) for slot in SLOTS]:
        raise RuntimeError('Reference slot list changed')
    key = getpass.getpass('Helius meme-quant-lab API-key (blijft lokaal): ').strip()
    if not key or len(key) > 256 or any(c.isspace() for c in key):
        print('Ongeldige sleutel; geen verzoek verzonden.'); return 2
    endpoint = ENDPOINT + urllib.parse.quote(key, safe='')
    deadline = time.monotonic() + MAX_SECONDS
    # Fresh output path; no secrets in file names, report, or response data.
    out = Path('data/secondary') / ('helius-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True, exist_ok=False)
    report = {'provider': 'Helius', 'endpoint_host': 'mainnet.helius-rpc.com',
              'reference_manifest_sha256': reference['manifest_sha256'], 'requests': 0,
              'raw_bytes': 0, 'slots': {}, 'status': 'INCOMPLETE'}
    try:
        slots, raw = call(endpoint, 'getBlocks', [SLOTS[0], SLOTS[-1],
                          {'commitment': 'finalized'}], deadline, MAX_TOTAL_BYTES)
        report['requests'] += 1; report['raw_bytes'] += len(raw)
        if slots['result'] != list(SLOTS):
            raise RuntimeError('Slot enumeration differs from reference')
        for slot in SLOTS:
            if report['requests'] >= MAX_REQUESTS:
                raise RuntimeError('Request budget reached')
            result, raw = call(endpoint, 'getBlock', [slot, {'encoding': 'json',
                'transactionDetails': 'full', 'rewards': False, 'commitment': 'finalized',
                'maxSupportedTransactionVersion': 1}], deadline,
                MAX_TOTAL_BYTES - report['raw_bytes'])
            report['requests'] += 1; report['raw_bytes'] += len(raw)
            if result['result'] is None:
                raise RuntimeError(f'Block {slot} is null')
            # A provider should not echo the key; avoid saving it if it does.
            if key.encode() in raw:
                raise RuntimeError('Credential unexpectedly present in response')
            path = out / f'{slot}.json'
            with path.open('xb') as handle: handle.write(raw)
            report['slots'][str(slot)] = {'raw_sha256': hashlib.sha256(raw).hexdigest(),
                **compare(result['result'], reference['slots'][str(slot)])}
        report['status'] = ('MATCH' if all(v['status'] == 'MATCH'
                                    for v in report['slots'].values()) else 'MISMATCH')
    except RuntimeError as exc:
        report['status'] = 'INCOMPLETE'; report['issue'] = str(exc)
    finally:
        # Explicitly redact everything except provider, comparisons and budget counters.
        (out / 'comparison.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('Status:', report['status'], '| verzoeken:', report['requests'])
    print('Rapport:', out / 'comparison.json')
    if 'issue' in report: print('Melding:', report['issue'])
    return 0 if report['status'] == 'MATCH' else 2


if __name__ == '__main__':
    sys.exit(main())
