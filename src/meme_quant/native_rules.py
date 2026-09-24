"""Historical classic-token native rules, scoped to the verified Phase B sample.

Evidence: reports/TOKEN_NATIVE_RULES.json. Feature account activation slots establish
rent=5080/byte, threshold=1 before the sample. The deployed classic binary enforces
165-byte accounts and recomputes reserve on BOTH initialization and SyncNative.
No pre/post token amount is used to select the rent rate or reserve.
"""
from .token_ledger import TOKEN

SAMPLE_START = 449382000
SAMPLE_END = 449382040
CLASSIC_DEPLOYMENT = 419472000
RENT_5080_ACTIVATION = 446256000
CLASSIC_NATIVE_SIZE = 165
ACCOUNT_OVERHEAD = 128
LAMPORTS_PER_BYTE = 5080


def native_reserve(program, slot):
    if program != TOKEN or type(slot) is not int or not SAMPLE_START <= slot <= SAMPLE_END:
        raise ValueError('HISTORICAL_NATIVE_RULES_REQUIRED')
    return (CLASSIC_NATIVE_SIZE + ACCOUNT_OVERHEAD) * LAMPORTS_PER_BYTE
