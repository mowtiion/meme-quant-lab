"""Slot-scoped executable/IDL evidence, without backdating observed config state.

The registry certifies a limited interface validation scope, not all semantics,
reproducible source builds, historical inputs or readiness for trading/research.
Upgrade slots are excluded because slot alone cannot order an upgrade and trade.
"""
import base64
import hashlib
import json
from pathlib import Path
from solders.pubkey import Pubkey
from .decoder import PUMP, AMM, Reader
from .domain import IntegrityError

FEE_PROGRAM = 'pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ'


class ProgramRegistry:
    def __init__(self, path: Path):
        raw = path.read_bytes()
        self.sha256 = hashlib.sha256(raw).hexdigest()
        payload = json.loads(raw)
        if payload.get('schema_version') != 1 or payload.get('upgrade_slots_excluded') is not True:
            raise IntegrityError('Unsupported program registry')
        self.regimes = payload['regimes']
        for r in self.regimes:
            if (type(r['first_slot']) is not int or type(r['last_slot']) is not int
                    or not r['deployment_slot'] < r['first_slot'] <= r['last_slot']):
                raise IntegrityError('Invalid historical program interval')
            for key in ('binary_sha256', 'idl_sha256'):
                h = r[key]
                if len(h) != 64 or any(c not in '0123456789abcdef' for c in h):
                    raise IntegrityError('Invalid program evidence hash')
        for i, left in enumerate(self.regimes):
            for right in self.regimes[i+1:]:
                if left['program'] == right['program'] and max(left['first_slot'],right['first_slot']) <= min(left['last_slot'],right['last_slot']):
                    raise IntegrityError('Overlapping program intervals')

    def bind(self, decoder, slot):
        if type(slot) is not int:
            raise IntegrityError('Program binding requires an integer slot')
        matches = [r for r in self.regimes if r['program'] == decoder.program and r['first_slot'] <= slot <= r['last_slot']]
        if len(matches) != 1:
            raise IntegrityError('Historical executable interval is unproven at this slot')
        r = matches[0]
        if decoder.hash != r['idl_sha256']:
            raise IntegrityError('IDL hash differs from executable interface evidence')
        return {k:r[k] for k in ('id','program','deployment_slot','binary_sha256','idl_sha256','validated_scope','full_historical_config_verified','verified_source_build')}


def verify_history_window(envelope, start, stop, expected_upgrades):
    """Check a newest-first, unpaginated finalized receipt crossing the lower bound.

Callers must retain the request (no `before`, sufficient limit) and separately
verify every expected successful loader upgrade. This is RPC evidence, not a
cryptographic chain proof or an independent upstream assertion.
"""
    rows = envelope['result']
    if not rows or min(r['slot'] for r in rows) >= start:
        raise IntegrityError('ProgramData history does not cross interval start')
    if [r['slot'] for r in rows] != sorted((r['slot'] for r in rows),reverse=True):
        raise IntegrityError('ProgramData history is unordered')
    if len({r['signature'] for r in rows}) != len(rows) or any(r['confirmationStatus'] != 'finalized' for r in rows):
        raise IntegrityError('ProgramData history is duplicated or unfinalized')
    relevant = {(r['slot'],r['signature']) for r in rows if start <= r['slot'] <= stop and r['err'] is None}
    if relevant != set(expected_upgrades):
        raise IntegrityError('Unexplained ProgramData history change')
    return len(rows)


def decode_config_observation(observation, decoder, *, target_slot=None):
    """Decode a checked current snapshot; never substitute it for an earlier slot."""
    slot = observation['observed_slot']
    if type(slot) is not int or slot < 0:
        raise IntegrityError('Invalid config observation slot')
    if target_slot is not None and (type(target_slot) is not int or target_slot != slot):
        raise IntegrityError('Config snapshot is not proven at the requested historical slot')
    typ = observation['type']; pid = Pubkey.from_string(decoder.program)
    if typ == 'Global' and decoder.program == PUMP:
        owner, seeds = pid, [b'global']
    elif typ == 'GlobalConfig' and decoder.program == AMM:
        owner, seeds = pid, [b'global_config']
    elif typ == 'FeeConfig' and decoder.program in (PUMP, AMM):
        owner, seeds = Pubkey.from_string(FEE_PROGRAM), [b'fee_config',bytes(pid)]
    else:
        raise IntegrityError('Unsupported config type/program')
    expected = str(Pubkey.find_program_address(seeds,owner)[0])
    account = observation['account']
    if observation['address'] != expected or account['owner'] != str(owner) or account['executable'] is not False:
        raise IntegrityError('Config address, owner or executable flag mismatch')
    if account['data'][1] != 'base64':
        raise IntegrityError('Unexpected config encoding')
    raw = base64.b64decode(account['data'][0],validate=True)
    if account.get('space',len(raw)) != len(raw) or raw[:8] != decoder.accounts.get(typ):
        raise IntegrityError('Config size or discriminator mismatch')
    reader = Reader(raw[8:],decoder.types)
    value = reader.read({'defined':{'name':typ}})
    if any(reader.data[reader.pos:]):
        raise IntegrityError('Unknown nonzero config extension')
    return {'address':expected,'owner':str(owner),'type':typ,'observed_slot':slot,
            'account_sha256':hashlib.sha256(raw).hexdigest(),'idl_sha256':decoder.hash,
            'decoded_bytes':8+reader.pos,'padding_bytes':len(raw)-8-reader.pos,'value':value}
