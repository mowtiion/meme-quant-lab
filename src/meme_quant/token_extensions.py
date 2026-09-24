"""Narrow, binary-checked extension support; unsupported variants stay unknown."""
TOKEN_2022 = 'TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb'


def effect_data(program, data, accounts=None):
    if program != TOKEN_2022 or not data:
        return data
    if data[0] == 26 and len(data) >= 2 and data[1] == 1:
        if len(data) != 19 or (accounts is not None and len(accounts)<4):
            raise ValueError('MALFORMED_TRANSFER_CHECKED_WITH_FEE')
        if int.from_bytes(data[11:19], 'little') != 0:
            raise ValueError('NONZERO_TRANSFER_FEE_REQUIRES_WITHHELD_LEDGER')
        return bytes([12])+data[2:11]
    if data[0] == 39 and len(data) >= 2 and data[1] == 0:
        if len(data) != 66 or (accounts is not None and len(accounts)<1):
            raise ValueError('MALFORMED_METADATA_POINTER_INITIALIZATION')
        return None
    if data[:8] == bytes.fromhex('d2e11ea258b84d8d'):
        if accounts is not None and (len(accounts)<4 or accounts[0]!=accounts[2]):
            raise ValueError('MALFORMED_TOKEN_METADATA_ACCOUNTS')
        offset=8
        for _ in range(3):
            if offset+4>len(data):raise ValueError('MALFORMED_TOKEN_METADATA')
            size=int.from_bytes(data[offset:offset+4],'little');offset+=4
            if offset+size>len(data):raise ValueError('MALFORMED_TOKEN_METADATA')
            data[offset:offset+size].decode('utf-8');offset+=size
        if offset!=len(data):raise ValueError('MALFORMED_TOKEN_METADATA')
        return None
    if data[:8] == bytes.fromhex('d7e4a6e45464567b'):
        if len(data)!=40 or (accounts is not None and len(accounts)<2):
            raise ValueError('MALFORMED_TOKEN_METADATA_AUTHORITY')
        return None
    return data
