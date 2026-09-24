"""One transaction's economic checks, shared by batch audits and latency probes."""
import hashlib
import json
from .decoder import AMM
from .fee_audit import audit_amm_fees
from .lamport_ledger import reconcile_lamports
from .token_ledger import reconcile_token_accounts


def audit_transaction(tx, rows, decoders):
    result = reconcile_token_accounts(tx)
    result['lamport_check'] = reconcile_lamports(tx, rows, decoders)
    result['fee_checks'] = audit_amm_fees(tx, rows, decoders[AMM])
    return result


class DetailsDigest:
    """Hash the canonical JSON array without retaining every result in memory."""
    def __init__(self):
        self._hash = hashlib.sha256(b'[')
        self.count = 0

    def add(self, detail):
        encoded = json.dumps(detail, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
        if self.count:
            self._hash.update(b',')
        self._hash.update(encoded)
        self.count += 1

    def hexdigest(self):
        final = self._hash.copy()
        final.update(b']')
        return final.hexdigest()
