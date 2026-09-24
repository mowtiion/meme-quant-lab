"""Rebuild canonical hashes only from SHA-verified original frozen blocks."""
import hashlib
import json
from pathlib import Path
from compare_second_source import canonical_token_ui, normalize_preexecution_empty, groups, digest


def main():
    path = Path('configs/second_source_reference41.json')
    reference = json.loads(path.read_text())
    for slot, item in reference['slots'].items():
        sha = item['raw_sha256']
        raw = Path(f'data/raw/objects/{sha[:2]}/{sha}.json').read_bytes()
        if hashlib.sha256(raw).hexdigest() != sha:
            raise RuntimeError(f'Primary raw hash mismatch: {slot}')
        block = json.loads(raw)['result']
        if {k:digest(v) for k,v in groups(block).items()} != item['group_sha256']:
            raise RuntimeError(f'Primary field hash mismatch: {slot}')
        canonical, _ = canonical_token_ui(normalize_preexecution_empty(block)[0])
        item['canonical_group_sha256'] = {k:digest(v) for k,v in groups(canonical).items()}
    reference['canonical_policy'] = ('CANONICAL_TOKEN_UI_V1: validate numeric uiAmount within one ULP of '
        'amount/10**decimals, retain exact amount, decimals, uiAmountString and null; '
        'normalize preexecution empty arrays only under existing rule')
    path.write_text(json.dumps(reference, indent=2)+'\n')
    print('Verified and rebuilt', len(reference['slots']), 'references')


if __name__ == '__main__':
    main()
