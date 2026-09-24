"""Bounded, read-only Helius check against frozen Solana reference blocks.

The key is prompted locally and never written to the report, raw data or Git.
Run from the repository root with Python 3.12; no third-party dependencies.
"""
import argparse
import getpass
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path


REFERENCE = Path('configs/second_source_reference.json')
SLOTS = (447000000, 447000001, 447000002)
MAX_REQUESTS = 4
MAX_TOTAL_BYTES = 32 * 1024 * 1024
MAX_SECONDS = 120
ENDPOINT = 'https://mainnet.helius-rpc.com/?api-key='
PHASE_B_REFERENCE = Path('configs/second_source_reference41.json')
PHASE_B_SLOTS = tuple(range(449382000, 449382041))
PHASE_B_MAX_BYTES = 192 * 1024 * 1024
PHASE_B_MAX_SECONDS = 600


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


def normalize_preexecution_empty(block):
    """Align empty arrays with the reference's null only for pre-execution failures.

    Both original provider responses remain unchanged in the evidence archives.
    A missing log on an executed transaction is never normalized away.
    """
    changes = []
    transactions = list(block['transactions'])
    for index, tx in enumerate(transactions):
        meta = tx['meta']
        if (meta['err'] != 'MaxLoadedAccountsDataSizeExceeded' or
                meta['computeUnitsConsumed'] != 0):
            continue
        fields = [field for field in ('innerInstructions', 'logMessages')
                  if meta[field] == []]
        if fields:
            changed = dict(tx)
            changed['meta'] = dict(meta)
            for field in fields:
                changed['meta'][field] = None
            transactions[index] = changed
            changes.append({'index': index, 'signature': tx['transaction']['signatures'][0],
                            'fields': fields})
    normalized = dict(block)
    normalized['transactions'] = transactions
    return normalized, changes


def compare(block, expected):
    try:
        count = len(block['transactions'])
        observed = {name: digest(value) for name, value in groups(block).items()}
        matches = {name: value == expected['group_sha256'][name]
                   for name, value in observed.items()}
        changes = []
        if not all(matches.values()):
            normalized, candidates = normalize_preexecution_empty(block)
            if candidates:
                normalized_hashes = {name: digest(value) for name, value in groups(normalized).items()}
                normalized_matches = {name: value == expected['group_sha256'][name]
                                      for name, value in normalized_hashes.items()}
                if all(normalized_matches.values()):
                    matches, changes = normalized_matches, candidates
    except (KeyError, TypeError, ValueError):
        return {'status': 'MISSING_FIELDS', 'transactions': None, 'groups': {}}
    return {'status': 'MATCH' if count == expected['transactions'] and all(matches.values())
            else 'MISMATCH', 'transactions': count, 'groups': matches,
            'normalized_preexecution_fields': changes}


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


def package_phase_b(out, slot_numbers):
    """Small, verified parts can be uploaded without sharing credentials."""
    for start in range(0, len(slot_numbers), 8):
        part = out / f'evidence-{start//8+1:02d}.zip'
        partial = out / f'evidence-{start//8+1:02d}.zip.partial'
        with zipfile.ZipFile(partial, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            z.write(out / 'comparison.json', 'comparison.json')
            for slot in slot_numbers[start:start+8]:
                z.write(out / f'{slot}.json', f'{slot}.json')
        with zipfile.ZipFile(partial) as z:
            if z.testzip() is not None: raise RuntimeError('Damaged evidence ZIP')
        if partial.stat().st_size > 32*1024*1024:
            raise RuntimeError('Evidence ZIP exceeds upload limit')
        os.replace(partial, part)


def main():
    parser=argparse.ArgumentParser(description='Read-only Helius block comparison')
    parser.add_argument('--phase-b',action='store_true',help='Compare 41 more slots, strictly bounded')
    args=parser.parse_args()
    phase_b=args.phase_b
    reference_path=PHASE_B_REFERENCE if phase_b else REFERENCE
    slot_numbers=PHASE_B_SLOTS if phase_b else SLOTS
    max_requests=len(slot_numbers)+1
    max_bytes=PHASE_B_MAX_BYTES if phase_b else MAX_TOTAL_BYTES
    max_seconds=PHASE_B_MAX_SECONDS if phase_b else MAX_SECONDS
    reference = json.loads(reference_path.read_text(encoding='utf-8'))
    if sorted(reference['slots']) != [str(slot) for slot in slot_numbers]:
        raise RuntimeError('Reference slot list changed')
    # GitHub Actions supplies this as a repository secret; interactive runs still prompt.
    key = (os.environ.get('HELIUS_API_KEY') or
           getpass.getpass('Helius meme-quant-lab API-key (blijft lokaal): ')).strip()
    if not key or len(key) > 256 or any(c.isspace() for c in key):
        print('Ongeldige sleutel; geen verzoek verzonden.'); return 2
    endpoint = ENDPOINT + urllib.parse.quote(key, safe='')
    deadline = time.monotonic() + max_seconds
    # Fresh output path; no secrets in file names, report, or response data.
    label='helius41-' if phase_b else 'helius-'
    out = Path('data/secondary') / (label + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True, exist_ok=False)
    report = {'provider': 'Helius', 'endpoint_host': 'mainnet.helius-rpc.com',
              'reference_manifest_sha256': reference['manifest_sha256'], 'requests': 0,
              'raw_bytes': 0, 'slots': {}, 'status': 'INCOMPLETE'}
    if phase_b:report['limits']={'requests':max_requests,'response_bytes':max_bytes,
                                  'network_seconds':max_seconds}
    try:
        slots, raw = call(endpoint, 'getBlocks', [slot_numbers[0], slot_numbers[-1],
                          {'commitment': 'finalized'}], deadline, max_bytes)
        report['requests'] += 1; report['raw_bytes'] += len(raw)
        if slots['result'] != list(slot_numbers):
            raise RuntimeError('Slot enumeration differs from reference')
        for slot in slot_numbers:
            if report['requests'] >= max_requests:
                raise RuntimeError('Request budget reached')
            if phase_b:time.sleep(min(.35,max(0,deadline-time.monotonic())))
            result, raw = call(endpoint, 'getBlock', [slot, {'encoding': 'json',
                'transactionDetails': 'full', 'rewards': False, 'commitment': 'finalized',
                'maxSupportedTransactionVersion': 1}], deadline,
                max_bytes - report['raw_bytes'])
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
            if report['slots'][str(slot)]['status'] != 'MATCH' and phase_b:
                report['status']='MISMATCH'
                break
        else:
            report['status'] = ('MATCH' if all(v['status'] == 'MATCH'
                                        for v in report['slots'].values()) else 'MISMATCH')
    except RuntimeError as exc:
        report['status'] = 'INCOMPLETE'; report['issue'] = str(exc)
    finally:
        # Explicitly redact everything except provider, comparisons and budget counters.
        (out / 'comparison.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    if phase_b and report['slots']:
        try:package_phase_b(out, tuple(map(int,report['slots'])))
        except RuntimeError as exc:print('Archiefmelding:', str(exc))
    print('Status:', report['status'], '| verzoeken:', report['requests'])
    print('Rapport:', out / 'comparison.json')
    if phase_b:print('Bewijsdelen:',out / 'evidence-*.zip')
    if 'issue' in report: print('Melding:', report['issue'])
    return 0 if report['status'] == 'MATCH' else 2


if __name__ == '__main__':
    sys.exit(main())
