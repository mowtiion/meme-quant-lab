"""Conservative recovery of truncated PumpSwap logs from authenticated self-CPIs.

Only positive execution evidence is promoted. Transaction success proves outer
instruction success, not success of an inner call whose error a router may catch.
Reference: https://docs.rs/anchor-lang/latest/src/anchor_lang/event.rs.html
"""
import re
from collections import defaultdict

from .decoder import AMM, unbase58
from .domain import IntegrityError

EVENT_IX_TAG = bytes.fromhex('e445a52e51cb9a1d')
# Explicitly scoped to the instruction variants validated by this implementation.
AMM_EVENTS = {
    'buy': ['BuyEvent'], 'buy_exact_quote_in': ['BuyEvent'], 'sell': ['SellEvent'],
    'close_user_volume_accumulator': ['CloseUserVolumeAccumulatorEvent'],
    'boost_buy_and_burn': ['BuyEvent', 'BoostBuyAndBurnEvent'],
}


def instruction_trace(tx):
    message, meta = tx['transaction']['message'], tx['meta']
    keys = [k['pubkey'] if isinstance(k, dict) else k for k in message['accountKeys']]
    loaded = meta.get('loadedAddresses') or {}
    keys += loaded.get('writable', []) + loaded.get('readonly', [])
    outer = message['instructions']
    groups = meta.get('innerInstructions')
    if groups is None:
        raise IntegrityError('Inner instructions unavailable')
    indices = [g['index'] for g in groups]
    if (any(type(i) is not int or not 0 <= i < len(outer) for i in indices)
            or indices != sorted(set(indices))):
        raise IntegrityError('Invalid or duplicate inner-instruction groups')
    grouped = {g['index']: g['instructions'] for g in groups}
    nodes = []

    def account(i):
        if type(i) is not int or not 0 <= i < len(keys):
            raise IntegrityError('Invalid instruction account index')
        return keys[i]

    def add(ix, depth, parent, outer_index, inner_index):
        node = {'position': len(nodes), 'program': account(ix['programIdIndex']),
                'depth': depth, 'parent': parent, 'outer_index': outer_index,
                'inner_index': inner_index, 'instruction': ix,
                'accounts': [account(i) for i in ix['accounts']], 'status': None}
        nodes.append(node)
        return node['position']

    for outer_index, ix in enumerate(outer):
        root = add(ix, 1, None, outer_index, None)
        stack = [root]
        for inner_index, child in enumerate(grouped.get(outer_index, [])):
            depth = child.get('stackHeight')
            if type(depth) is not int or depth < 2 or depth > len(stack)+1:
                raise IntegrityError('Missing or inconsistent CPI stackHeight')
            stack = stack[:depth-1]
            pos = add(child, depth, stack[-1], outer_index, inner_index)
            stack.append(pos)
    return nodes


def execution_evidence(nodes, logs):
    """Align every available invoke to the metadata preorder; never guess across gaps."""
    cursor, stack, log_parents = 0, [], {}
    for index, log in enumerate(logs):
        invoke = re.fullmatch(r'Program (\w+) invoke \[(\d+)\]', log)
        done = re.match(r'Program (\w+) (success|failed:)', log)
        if invoke:
            if cursor >= len(nodes):
                raise IntegrityError('Log invoke absent from instruction metadata')
            node = nodes[cursor]
            if (node['program'] != invoke[1] or node['depth'] != int(invoke[2])
                    or node['parent'] != (stack[-1] if stack else None)):
                raise IntegrityError('Cannot align logs to instruction execution')
            stack.append(cursor)
            cursor += 1
        elif done:
            if not stack or nodes[stack[-1]]['program'] != done[1]:
                raise IntegrityError('Cannot align log completion to instruction')
            pos = stack.pop()
            nodes[pos]['status'] = 'success' if done[2] == 'success' else 'failed'
            if nodes[pos]['depth'] == 1 and nodes[pos]['status'] == 'failed':
                raise IntegrityError('Outer failure contradicts transaction success')
        elif log.startswith('Program data: ') and stack:
            log_parents[index] = stack[-1]
    # All top-level instructions commit when meta.err is null. Inner calls may fail.
    for node in nodes:
        if node['depth'] == 1:
            node['status'] = 'success'
    return log_parents


def committed(nodes, position):
    unknown = False
    while position is not None:
        node = nodes[position]
        if node['status'] == 'failed':
            return False
        unknown |= node['status'] is None
        position = node['parent']
    return None if unknown else True


def recover_transaction(tx, rows, slot, tx_index, event_ms, raw_hash, decoders, original_issues):
    """Return one CPI-ordered stream and blocking issues, or reject the whole fallback.

    Complete log copies are matched in their originating instruction, including
    multiplicity. Unproven candidates are recorded as issues, never as trades.
    """
    if tx['meta'].get('err') is not None:
        raise IntegrityError('Cannot recover failed transaction')
    nodes = instruction_trace(tx)
    parents = execution_evidence(nodes, tx['meta']['logMessages'])
    signature = tx['transaction']['signatures'][0]
    pending = defaultdict(list)
    for row in rows:
        if row['event_index'] not in parents:
            raise IntegrityError('Log event has no instruction parent')
        pending[parents[row['event_index']]].append(row)
    recovered, issues, emitted = [], [], defaultdict(list)

    def issue(reason, node, **extra):
        issues.append({'slot': slot, 'signature': signature, 'reason': reason,
                       'instruction_path': [node['outer_index'], node['inner_index']],
                       'raw_sha256': raw_hash, **extra})

    for node in nodes:
        if node['program'] not in decoders:
            continue
        decoder = decoders[node['program']]
        raw = unbase58(node['instruction']['data'])
        if not raw.startswith(EVENT_IX_TAG):
            continue
        if node['parent'] is None or nodes[node['parent']]['program'] != node['program']:
            raise IntegrityError('Event CPI is not a self invocation')
        parent = nodes[node['parent']]
        spec = decoder.instructions.get(unbase58(parent['instruction']['data'])[:8])
        if not spec:
            raise IntegrityError('Unknown parent instruction for event CPI')
        accounts = {a['name']: parent['accounts'][i] for i, a in enumerate(spec['accounts'])}
        if node['accounts'] != [accounts.get('event_authority')]:
            raise IntegrityError('CPI event-authority account mismatch')
        name, payload = decoder.decode(raw[8:])
        if payload.get('_missing_trailing_fields'):
            raise IntegrityError('Unversioned legacy CPI event')
        expected = AMM_EVENTS.get(spec['name']) if node['program'] == AMM else None
        if expected is None or name not in expected:
            raise IntegrityError('Unvalidated instruction/event combination')
        emitted[node['parent']].append(name)
        if len(emitted[node['parent']]) > len(expected):
            raise IntegrityError('Duplicate or excess event CPIs for one instruction')
        matches = pending[node['parent']]
        log_row = None
        if matches:
            first = matches[0]
            if (first['program'], first['name'], first['payload']) != (node['program'], name, payload):
                raise IntegrityError('Log/CPI event payload or order mismatch')
            log_row = matches.pop(0)
        state = committed(nodes, node['position'])
        if state is False:
            # An event emitted by a rolled-back invocation must never be promoted.
            continue
        if state is None:
            issue('CPI_EXECUTION_UNPROVEN', node, event_name=name,
                  candidate_payload=payload, decoder_hash=decoder.hash)
            continue
        recovered.append({'slot': slot, 'tx_index': tx_index, 'event_index': node['position'],
                          'signature': signature, 'program': node['program'], 'event_ms': event_ms,
                          'name': name, 'payload': payload, 'raw_sha256': raw_hash,
                          'decoder_hash': decoder.hash, 'event_source': 'verified_self_cpi',
                          'instruction_path': [node['outer_index'], node['inner_index']],
                          'parent_instruction_path': [parent['outer_index'], parent['inner_index']],
                          'source_log_index': log_row['event_index'] if log_row else None,
                          'recovered_missing_log': log_row is None,
                          'recovery_original_issues': sorted({i['reason'] for i in original_issues})})
    if any(pending.values()):
        raise IntegrityError('Log events without matching authenticated CPI')
    for node in nodes:
        if node['program'] not in decoders or committed(nodes, node['position']) is False:
            continue
        raw = unbase58(node['instruction']['data'])
        if raw.startswith(EVENT_IX_TAG):
            continue
        spec = decoders[node['program']].instructions.get(raw[:8])
        expected = AMM_EVENTS.get(spec['name']) if spec and node['program'] == AMM else None
        if expected is None:
            issue('CPI_UNVALIDATED_INSTRUCTION', node)
        elif emitted[node['position']] != expected:
            issue('CPI_MISSING_EXPECTED_EVENT', node, expected=expected, actual=emitted[node['position']])
    return recovered, issues
