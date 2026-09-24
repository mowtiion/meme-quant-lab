"""Published recipient snapshot plus deterministic ATA/PDA identity checks.

Documentation membership does not prove historical Global account state.
Source: pump-fun/pump-public-docs docs/FEE_RECIPIENTS.md, retrieved 2026-09-24.
"""
from solders.pubkey import Pubkey

BUYBACK_RECIPIENTS = {
    '5YxQFdt3Tr9zJLvkFccqXVUwhdTWJQc1fFg2YPbxvxeD',
    '9M4giFFMxmFGXtc3feFzRai56WbBqehoSeRE5GK7gf7',
    'GXPFM2caqTtQYC2cJ5yJRi9VDkpsYZXzYdwYpGnLmtDL',
    '3BpXnfJaUTiwXnJNe7Ej1rcbzqTTQUvLShZaWazebsVR',
    '5cjcW9wExnJJiqgLjq7DEG75Pm6JBgE1hNv4B2vHXUW6',
    'EHAAiTxcdDwQ3U4bU6YcMsQGaekdzLS3B5SmYo46kJtL',
    '5eHhjP8JaYkz83CWwvGU2uMUXefd3AazWGx4gpcuEEYD',
    'A7hAgCzFw14fejgCp387JUJRMNyz4j89JKnhtKU8piqW',
}


def associated_token(owner,mint,program):
    seeds=[bytes(Pubkey.from_string(x)) for x in (owner,program,mint)]
    return str(Pubkey.find_program_address(seeds,Pubkey.from_string('ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL'))[0])


def volume_accumulator(user,program):
    return str(Pubkey.find_program_address([b'user_volume_accumulator',bytes(Pubkey.from_string(user))],Pubkey.from_string(program))[0])
