"""Transaction-bounded PumpSwap vault replay using integer balances only.

This certifies event-reported vault flows, not fee pricing or historical state between
transactions. External vault flows or ambiguous attribution fail closed.
"""
from collections import Counter, defaultdict
from .decoder import AMM, ZERO, unbase58


def account_keys(tx):
    message, meta = tx['transaction']['message'], tx['meta']
    keys = [x['pubkey'] if isinstance(x, dict) else x for x in message['accountKeys']]
    loaded = meta.get('loadedAddresses') or {}
    return keys + loaded.get('writable', []) + loaded.get('readonly', [])


def _uint(value):
    if type(value) is not int or not 0 <= value < 2**64:
        raise ValueError('INVALID_INTEGER_AMOUNT')
    return value


def _balance(tx, keys, field, account, mint):
    found = [b for b in tx['meta'][field] if keys[b['accountIndex']] == account]
    if len(found) != 1 or found[0]['mint'] != mint:
        raise ValueError('MISSING_OR_CONFLICTING_VAULT_BALANCE')
    token = found[0]['uiTokenAmount']
    amount = token['amount']
    if not isinstance(amount, str) or not amount.isascii() or not amount.isdigit():
        raise ValueError('INVALID_INTEGER_AMOUNT')
    return _uint(int(amount)), _uint(token['decimals'])


def reconcile_pool_transaction(tx, rows, decoder):
    """Return one auditable result per pool; never infer missing balances as zero."""
    grouped = defaultdict(list)
    for row in rows:
        if row['program'] == AMM and row['name'] in ('BuyEvent', 'SellEvent'):
            grouped[row['payload']['pool']].append(row)
    if not grouped:
        return []
    keys = account_keys(tx)
    instructions = list(tx['transaction']['message']['instructions'])
    instructions += [ix for group in tx['meta'].get('innerInstructions') or [] for ix in group['instructions']]
    mappings = []
    for ix in instructions:
        if keys[ix['programIdIndex']] != AMM:
            continue
        spec = decoder.instructions.get(unbase58(ix['data'])[:8])
        if spec and spec['name'] in ('buy', 'sell', 'buy_exact_quote_in'):
            mappings.append({'_kind': 'SellEvent' if spec['name'] == 'sell' else 'BuyEvent',
                             **{a['name']: keys[ix['accounts'][i]] for i, a in enumerate(spec['accounts'])
                                if i < len(ix['accounts'])}})
    results = []
    for pool, events in grouped.items():
        result = {'pool': pool, 'signature': tx['transaction']['signatures'][0],
                  'event_count': len(events), 'status': 'UNRESOLVED'}
        try:
            if tx['meta']['err'] is not None:
                raise ValueError('FAILED_TRANSACTION')
            logs = tx['meta'].get('logMessages')
            if not isinstance(logs, list) or any('Log truncated' in s or ' failed:' in s for s in logs):
                raise ValueError('INCOMPLETE_OR_FAILED_INNER_EXECUTION')
            if any(e['payload']['user_base_token_account'] == ZERO for e in events):
                raise ValueError('PROTOCOL_BURN_SEPARATE_LEDGER')
            identities = set()
            identity_fields = ('pool', 'user', 'user_base_token_account', 'user_quote_token_account')
            event_counts = Counter((e['name'], *(e['payload'][k] for k in identity_fields)) for e in events)
            for event in events:
                p = event['payload']
                matching = [a for a in mappings if a['_kind'] == event['name']
                            and all(a.get(k) == p[k] for k in identity_fields)]
                if len(matching) != event_counts[(event['name'], *(p[k] for k in identity_fields))]:
                    raise ValueError('INSTRUCTION_EVENT_COUNT_DIFFERS')
                candidates = {tuple(a[k] for k in ('pool_base_token_account', 'pool_quote_token_account',
                                                   'base_mint', 'quote_mint')) for a in matching}
                if len(candidates) != 1:
                    raise ValueError('AMBIGUOUS_INSTRUCTION_ATTRIBUTION')
                identities.update(candidates)
            if len(identities) != 1:
                raise ValueError('POOL_IDENTITY_CHANGED')
            base_vault, quote_vault, base_mint, quote_mint = next(iter(identities))
            pre_base, bd = _balance(tx, keys, 'preTokenBalances', base_vault, base_mint)
            pre_quote, qd = _balance(tx, keys, 'preTokenBalances', quote_vault, quote_mint)
            post_base, bpostd = _balance(tx, keys, 'postTokenBalances', base_vault, base_mint)
            post_quote, qpostd = _balance(tx, keys, 'postTokenBalances', quote_vault, quote_mint)
            if (bd, qd) != (bpostd, qpostd):
                raise ValueError('DECIMALS_CHANGED')
            current_base, current_quote = pre_base, pre_quote
            steps = []
            seen_indices = set()
            for event in sorted(events, key=lambda e: e['event_index']):
                p = event['payload']
                if event['event_index'] in seen_indices:
                    raise ValueError('DUPLICATE_EVENT')
                seen_indices.add(event['event_index'])
                if (_uint(p['pool_base_token_reserves']), _uint(p['pool_quote_token_reserves'])) != (current_base, current_quote):
                    raise ValueError('EVENT_PRE_RESERVES_DIFFER')
                if event['name'] == 'BuyEvent':
                    db = -_uint(p['base_amount_out'])
                    dq = _uint(p['quote_amount_in_with_lp_fee'])
                else:
                    db = _uint(p['base_amount_in'])
                    dq = -_uint(p['quote_amount_out_without_lp_fee'])
                if db == 0 or dq == 0:
                    raise ValueError('ZERO_FLOW')
                current_base, current_quote = _uint(current_base + db), _uint(current_quote + dq)
                steps.append({'event_index': event['event_index'], 'kind': event['name'],
                              'base_delta': db, 'quote_delta': dq,
                              'base_after': current_base, 'quote_after': current_quote})
            result.update(base_vault=base_vault, quote_vault=quote_vault,
                          base_mint=base_mint, quote_mint=quote_mint,
                          base_decimals=bd, quote_decimals=qd,
                          pre_base=pre_base, pre_quote=pre_quote, post_base=post_base, post_quote=post_quote,
                          predicted_post_base=current_base, predicted_post_quote=current_quote, steps=steps)
            if (current_base, current_quote) != (post_base, post_quote):
                raise ValueError('POST_RESERVES_DIFFER')
            result['status'] = 'RECONCILED'
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            result['reason'] = str(exc) if isinstance(exc, ValueError) else 'MISSING_OR_MALFORMED_FIELDS'
        results.append(result)
    return results
