"""Narrow AMM instruction-scoped protocol/creator fee audit; no pricing claims."""
from collections import Counter
from .decoder import AMM, ZERO, unbase58, boost_identity
from .reserve_ledger import account_keys
from .token_ledger import ordered_instructions, token_flows


def audit_amm_fees(tx, rows, decoder):
    events = [r for r in rows if r['program'] == AMM and r['name'] in ('BuyEvent','SellEvent')]
    if not events:
        return []
    if len(events) != 1:
        return [{'status':'UNRESOLVED','reason':'MULTI_EVENT_FEE_ATTRIBUTION','event_count':len(events)}]
    event = events[0]; p = event['payload']
    result = {'status':'UNRESOLVED','pool':p['pool'],'event_count':1}
    try:
        parsed = token_flows(tx)
        if parsed['unknown']:
            raise ValueError('UNSUPPORTED_TOKEN_EXTENSION')
        if p['user_base_token_account'] == ZERO:
            mint, quote_mint, companion = boost_identity({'transactions':[tx]},
                {**event,'tx_index':0}, [{**r,'tx_index':0} for r in rows], decoder)
            result.update(status='PROTOCOL_BURN_RECONCILED',base_mint=mint,quote_mint=quote_mint,
                          burned=p['base_amount_out'],quote_used=p['quote_amount_in'],companion_event_index=companion)
            return [result]
        if p.get('_missing_trailing_fields') or p['cashback'] or p['holder_rewards']:
            raise ValueError('FEE_VARIANT_REQUIRES_SEPARATE_MAPPING')
        keys = account_keys(tx)
        ordered = list(ordered_instructions(tx))
        candidates=[]
        for pos,(top,inner,ix) in enumerate(ordered):
            if keys[ix['programIdIndex']] != AMM:
                continue
            spec=decoder.instructions.get(unbase58(ix['data'])[:8])
            wanted=('buy','buy_exact_quote_in') if event['name']=='BuyEvent' else ('sell',)
            if not spec or spec['name'] not in wanted:
                continue
            a={v['name']:keys[ix['accounts'][i]] for i,v in enumerate(spec['accounts']) if i<len(ix['accounts'])}
            if all(a.get(k)==p[k] for k in ('pool','user','user_base_token_account','user_quote_token_account')):
                candidates.append((pos,top,inner,ix,a))
        if len(candidates)!=1:
            raise ValueError('AMBIGUOUS_INSTRUCTION')
        pos,top,inner,ix,a=candidates[0]
        depth=1 if inner is None else ix.get('stackHeight')
        if type(depth) is not int:
            raise ValueError('MISSING_CPI_DEPTH')
        descendants=set()
        for ct,ci,cix in ordered[pos+1:]:
            cd=1 if ci is None else cix.get('stackHeight')
            if type(cd) is not int:
                raise ValueError('MISSING_CPI_DEPTH')
            if ct!=top or cd<=depth:
                break
            descendants.add((ct,ci))
        flows=[f for f in parsed['flows'] if (f['top_index'],f['inner_index']) in descendants]
        if any(f['kind']!='transfer' for f in flows):
            raise ValueError('UNEXPECTED_MINT_OR_BURN')
        if a['protocol_fee_recipient_token_account'] != p['protocol_fee_recipient_token_account']:
            raise ValueError('PROTOCOL_RECIPIENT_DIFFERS')
        buy=event['name']=='BuyEvent'
        source=a['user_quote_token_account'] if buy else a['pool_quote_token_account']
        main_dest=a['pool_quote_token_account'] if buy else a['user_quote_token_account']
        main_amount=p['quote_amount_in_with_lp_fee'] if buy else p['user_quote_amount_out']
        base_source=a['pool_base_token_account'] if buy else a['user_base_token_account']
        base_dest=a['user_base_token_account'] if buy else a['pool_base_token_account']
        base_amount=p['base_amount_out'] if buy else p['base_amount_in']
        core=[(a['base_mint'],base_source,base_dest,base_amount),
              (a['quote_mint'],source,main_dest,main_amount),
              (a['quote_mint'],source,a['protocol_fee_recipient_token_account'],p['protocol_fee']-p['buyback_fee']),
              (a['quote_mint'],source,a['coin_creator_vault_ata'],p['coin_creator_fee'])]
        observed=Counter((f['mint'],f['source'],f['destination'],f['amount']) for f in flows if f['amount'])
        for mint,src,dest,amount in core:
            if type(amount) is not int or amount<0:
                raise ValueError('INVALID_FEE_AMOUNT')
            if amount:
                key=(mint,src,dest,amount)
                if observed[key]!=1:
                    raise ValueError('CORE_TRANSFER_DIFFERS')
                del observed[key]
        remaining=[{'mint':m,'source':s,'destination':d,'amount':n} for (m,s,d,n),count in observed.items() for _ in range(count)]
        if any(f['mint']!=a['quote_mint'] or f['source']!=source for f in remaining):
            raise ValueError('UNEXPECTED_RESIDUAL_TRANSFER')
        if sum(f['amount'] for f in remaining)!=p['buyback_fee']:
            raise ValueError('BUYBACK_AMOUNT_DIFFERS')
        result.update(status='CORE_FEES_RECONCILED',protocol_recipient=a['protocol_fee_recipient_token_account'],
                      protocol_net=p['protocol_fee']-p['buyback_fee'],creator_recipient=a['coin_creator_vault_ata'],
                      creator_fee=p['coin_creator_fee'],buyback_amount=p['buyback_fee'],
                      buyback_recipient_identity_verified=False,residual_transfers=remaining)
    except (ValueError,KeyError,IndexError,TypeError) as exc:
        result['reason']=str(exc) if isinstance(exc,ValueError) else 'MISSING_OR_MALFORMED_FIELDS'
    return [result]
