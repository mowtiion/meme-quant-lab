"""Conservative SPL token account-flow reconciliation from successful raw transactions.

Supports ordinary transfer/mint/burn variants. WSOL wrapping/closing and unknown
extensions stay explicit gaps; no missing account state is silently made zero.
"""
import re
from collections import defaultdict
from .decoder import unbase58
from .reserve_ledger import account_keys
from .token_extensions import effect_data

TOKEN = 'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA'
TOKEN_2022 = 'TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb'
NATIVE = 'So11111111111111111111111111111111111111112'
PROGRAMS = {TOKEN, TOKEN_2022}
NO_AMOUNT_CHANGE = {0, 2, 4, 5, 6, 10, 11, 13, 19, 20, 21, 22, 23, 24}


def ordered_instructions(tx):
    groups = {}
    for group in tx['meta'].get('innerInstructions') or []:
        if group['index'] in groups:
            raise ValueError('DUPLICATE_INNER_GROUP')
        groups[group['index']] = group['instructions']
    top = tx['transaction']['message']['instructions']
    if any(type(i) is not int or not 0 <= i < len(top) for i in groups):
        raise ValueError('INVALID_INNER_GROUP')
    for index, ix in enumerate(top):
        yield index, None, ix
        for inner_index, inner in enumerate(groups.get(index, [])):
            yield index, inner_index, inner


def token_flows(tx, allow_reinitialization=False):
    """Decode all token calls once. Return gross instructions even with coverage gaps."""
    meta = tx['meta']
    if meta['err'] is not None:
        raise ValueError('FAILED_TRANSACTION')
    logs = meta.get('logMessages')
    if not isinstance(logs, list) or any('Log truncated' in s or re.match(r'Program \w+ failed:', s) for s in logs):
        raise ValueError('INCOMPLETE_OR_FAILED_INNER_EXECUTION')
    keys = account_keys(tx)
    identities, snapshots, mint_decimals = {}, {}, {}

    def identify(account, mint, program, decimals=None):
        old = identities.get(account)
        value = (mint, program)
        if old is not None and old != value:
            raise ValueError('ACCOUNT_IDENTITY_CHANGED')
        identities[account] = value
        if decimals is not None:
            if type(decimals) is not int or not 0 <= decimals <= 255:
                raise ValueError('INVALID_DECIMALS')
            if mint in mint_decimals and mint_decimals[mint] != decimals:
                raise ValueError('MINT_DECIMALS_CONFLICT')
            mint_decimals[mint] = decimals

    for field in ('preTokenBalances', 'postTokenBalances'):
        snapshot = {}
        for row in meta[field]:
            account = keys[row['accountIndex']]
            if account in snapshot:
                raise ValueError('DUPLICATE_BALANCE')
            program = row.get('programId')
            if program not in PROGRAMS:
                raise ValueError('MISSING_TOKEN_PROGRAM')
            identify(account, row['mint'], program, row['uiTokenAmount']['decimals'])
            amount = row['uiTokenAmount']['amount']
            if not isinstance(amount, str) or not amount.isascii() or not amount.isdigit() or not 0 <= int(amount) < 2**64:
                raise ValueError('INVALID_INTEGER_AMOUNT')
            snapshot[account] = int(amount)
        snapshots[field] = snapshot
    initialized, closed, synced, unknown, flows = {}, set(), set(), [], []
    calls = []
    for top_index, inner_index, ix in ordered_instructions(tx):
        program = keys[ix['programIdIndex']]
        if program not in PROGRAMS:
            continue
        data = unbase58(ix['data'])
        accounts = [keys[i] for i in ix['accounts']]
        data = effect_data(program, data, accounts)
        if data is None:
            continue
        if not data:
            raise ValueError('EMPTY_TOKEN_INSTRUCTION')
        tag = data[0]
        calls.append((program, tag, accounts, data, top_index, inner_index))
        if tag in (1, 16, 18):
            if len(data) != (1 if tag == 1 else 33) or len(accounts) < 2:
                raise ValueError('MALFORMED_INITIALIZATION')
            if accounts[0] in initialized and not allow_reinitialization:
                raise ValueError('ACCOUNT_REINITIALIZATION')
            identify(accounts[0], accounts[1], program)
            initialized[accounts[0]] = accounts[1]
        elif tag == 9:
            if len(data) != 1 or len(accounts) < 3:
                raise ValueError('MALFORMED_CLOSE')
            closed.add(accounts[0])
        elif tag == 17:
            if len(data) != 1 or not accounts:
                raise ValueError('MALFORMED_SYNC')
            synced.add(accounts[0])
    for program, tag, a, data, top_index, inner_index in calls:
        if tag in (3, 7, 8, 12, 14, 15):
            checked = tag in (12, 14, 15)
            if len(data) != (10 if checked else 9) or len(a) < (4 if tag == 12 else 3):
                raise ValueError('MALFORMED_TOKEN_FLOW')
            amount = int.from_bytes(data[1:9], 'little')
            kind = 'transfer' if tag in (3, 12) else 'mint' if tag in (7, 14) else 'burn'
            source = a[0] if kind != 'mint' else None
            destination = (a[2] if tag == 12 else a[1]) if kind == 'transfer' else a[1] if kind == 'mint' else None
            mint = a[1] if tag in (8, 12, 15) else a[0] if kind == 'mint' else None
            inferred = {identities[x][0] for x in (source, destination) if x in identities}
            if mint is not None:
                inferred.add(mint)
            if len(inferred) != 1:
                raise ValueError('MISSING_OR_CONFLICTING_FLOW_MINT')
            mint = next(iter(inferred))
            for account in (source, destination):
                if account is not None:
                    identify(account, mint, program, data[9] if checked else None)
            if kind in ('mint','burn') and mint == NATIVE:
                raise ValueError('NATIVE_MINT_BURN_INVALID')
            flows.append({'kind': kind, 'program': program, 'mint': mint, 'amount': amount,
                          'source': source, 'destination': destination,
                          'authority': a[3] if tag == 12 else a[2],
                          'top_index': top_index, 'inner_index': inner_index})
        elif tag not in NO_AMOUNT_CHANGE | {1, 9, 16, 17, 18}:
            unknown.append({'program': program, 'tag': tag, 'top_index': top_index,
                            'inner_index': inner_index, 'accounts': a})
    return {'flows': flows, 'unknown': unknown, 'identities': identities,
            'pre': snapshots['preTokenBalances'], 'post': snapshots['postTokenBalances'],
            'initialized': initialized, 'closed': closed, 'synced': synced}


def reconcile_token_accounts(tx):
    try:
        parsed = token_flows(tx)
    except (ValueError, TypeError, IndexError, KeyError) as exc:
        return {'status': 'UNRESOLVED', 'reason': str(exc) if isinstance(exc, ValueError) else 'MALFORMED_METADATA',
                'accounts': [], 'flows': [], 'unknown': []}
    deltas = defaultdict(int)
    for flow in parsed['flows']:
        if flow['source'] is not None:
            deltas[flow['source']] -= flow['amount']
        if flow['destination'] is not None:
            deltas[flow['destination']] += flow['amount']
    accounts = []
    for account in sorted(set(parsed['pre']) | set(parsed['post']) | set(deltas)):
        mint, program = parsed['identities'][account]
        row = {'account': account, 'mint': mint, 'program': program, 'instruction_delta': deltas[account],
               'status': 'UNRESOLVED'}
        before, after = parsed['pre'].get(account), parsed['post'].get(account)
        reason = None
        if parsed['unknown']:
            reason = 'UNSUPPORTED_TOKEN_EXTENSION'
        elif account in parsed['synced'] or (mint == NATIVE and
                (account in parsed['initialized'] or account in parsed['closed'])):
            reason = 'WSOL_LIFECYCLE_REQUIRES_LAMPORT_LEDGER'
        else:
            if before is None and account in parsed['initialized'] and mint != NATIVE:
                before = 0
            if after is None and account in parsed['closed'] and mint != NATIVE:
                after = 0
            if before is None or after is None:
                reason = 'MISSING_ACCOUNT_BOUNDARY'
            elif after-before != deltas[account]:
                reason = 'TOKEN_DELTA_DIFFERS'
        row.update(before=before, after=after)
        if reason:
            row['reason'] = reason
        else:
            row['status'] = 'RECONCILED'
        accounts.append(row)
    full = bool(accounts) and all(a['status'] == 'RECONCILED' for a in accounts) and not parsed['unknown']
    return {'status': 'RECONCILED' if full else 'PARTIAL', 'accounts': accounts,
            'flows': parsed['flows'], 'unknown': parsed['unknown']}
