"""Bounded historical account-state reads; credential stays in Actions secrets."""
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def main():
    key = os.environ['ALCHEMY_API_KEY'].strip()
    if not key or len(key) > 256 or any(c.isspace() for c in key):
        raise ValueError('Invalid credential')
    endpoint = 'https://solana-mainnet.g.alchemy.com/v2/' + urllib.parse.quote(key, safe='')
    requests = json.loads(Path('configs/token_state_requests.json').read_text())
    if not 1 <= len(requests) <= 16:
        raise ValueError('Request cap exceeded')
    out = Path('data/secondary/token-state'); out.mkdir(parents=True, exist_ok=True)
    report = {'requests': [], 'max_requests': 16, 'max_bytes': 16*1024*1024}
    deadline = time.monotonic()+120; remaining = report['max_bytes']
    for number, spec in enumerate(requests):
        if time.monotonic() >= deadline:
            break
        payload = {'jsonrpc':'2.0','id':number,'method':'getAccountInfo',
                   'params':[spec['account'],{'encoding':'base64','commitment':'finalized','slot':spec['slot']}]}
        req = urllib.request.Request(endpoint, data=json.dumps(payload).encode(), headers={'Content-Type':'application/json'})
        row = dict(spec)
        try:
            with urllib.request.urlopen(req, timeout=min(25,deadline-time.monotonic())) as response:
                raw = response.read(remaining+1)
            if len(raw)>remaining: raise ValueError('Response byte cap exceeded')
            if key.encode() in raw: raise ValueError('Credential in response')
            remaining -= len(raw)
            name = f'{number:02d}.json'; (out/name).write_bytes(raw)
            body = json.loads(raw)
            row.update(file=name, sha256=hashlib.sha256(raw).hexdigest(),
                       context=body.get('result',{}).get('context'), error=body.get('error'))
        except urllib.error.HTTPError as exc:
            row['http_status'] = exc.code
        except Exception as exc:
            row['exception_type'] = type(exc).__name__
        report['requests'].append(row)
    (out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
