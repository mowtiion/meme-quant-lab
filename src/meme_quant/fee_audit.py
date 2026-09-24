"""Narrow AMM instruction-scoped protocol/creator fee audit; no pricing claims."""
from collections import Counter
from .decoder import AMM, ZERO, boost_identity
from .token_ledger import token_flows
from .event_scope import EventScope
from .fee_recipients import associated_token, volume_accumulator, BUYBACK_RECIPIENTS


def audit_amm_fees(tx, rows, decoder):
    events = [r for r in rows if r['program'] == AMM and r['name'] in ('BuyEvent','SellEvent')]
    if not events:
        return []
    if len({e['event_index'] for e in events}) != len(events):
        return [{'status':'UNRESOLVED','reason':'MULTI_EVENT_FEE_ATTRIBUTION','event_count':len(events)}]
    try:
        scope=EventScope(tx)
        parsed=token_flows(tx,allow_reinitialization=True)
    except (ValueError,KeyError,IndexError,TypeError) as exc:
        return [{'status':'UNRESOLVED','reason':str(exc),'event_count':len(events)}]
    return [_audit_event(tx,e,rows,decoder,scope,parsed) for e in events]


def _audit_event(tx,event,rows,decoder,scope,parsed):
    p = event['payload']
    result = {'status':'UNRESOLVED','pool':p['pool'],'event_count':1,'event_index':event['event_index']}
    try:
        if p['user_base_token_account'] == ZERO:
            if parsed['unknown']:raise ValueError('UNSUPPORTED_TOKEN_EXTENSION')
            mint, quote_mint, companion = boost_identity({'transactions':[tx]},
                {**event,'tx_index':0}, [{**r,'tx_index':0} for r in rows], decoder)
            result.update(status='PROTOCOL_BURN_RECONCILED',base_mint=mint,quote_mint=quote_mint,
                          burned=p['base_amount_out'],quote_used=p['quote_amount_in'],companion_event_index=companion)
            return result
        if p.get('_missing_trailing_fields'):
            raise ValueError('FEE_VARIANT_REQUIRES_SEPARATE_MAPPING')
        node,a,spec=scope.bind(event,decoder,{'buy','buy_exact_quote_in'} if event['name']=='BuyEvent' else {'sell'})
        if any(a[k]!=p[k] for k in ('pool','user','user_base_token_account','user_quote_token_account')):
            raise ValueError('EVENT_ACCOUNT_DIFFERS')
        if p['holder_rewards'] not in (0,p['coin_creator_fee']) or (p['cashback'] and (p['coin_creator_fee'] or p['holder_rewards'])):
            raise ValueError('FEE_VARIANT_REQUIRES_SEPARATE_MAPPING')
        descendants=scope.descendants(node)
        if any((u['top_index'],u['inner_index']) in descendants for u in parsed['unknown']):
            raise ValueError('UNSUPPORTED_TOKEN_EXTENSION')
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
        extra=node['accounts'][len(spec['accounts']):]
        if len(extra)<2:
            raise ValueError('MISSING_BUYBACK_RECIPIENT')
        pairs=[(owner,ata) for owner,ata in zip(extra,extra[1:]) if owner in BUYBACK_RECIPIENTS
               and associated_token(owner,a['quote_mint'],a['quote_token_program'])==ata]
        if len(pairs)!=1:
            raise ValueError('BUYBACK_ATA_DIFFERS')
        buyback_owner,buyback_ata=pairs[0]
        if p['cashback']:
            owner=volume_accumulator(a['user'],AMM)
            if not extra or extra[0]!=associated_token(owner,a['quote_mint'],a['quote_token_program']):
                raise ValueError('CASHBACK_ATA_DIFFERS')
            core.append((a['quote_mint'],source,extra[0],p['cashback']))
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
        if any(f['destination']!=buyback_ata for f in remaining):
            raise ValueError('BUYBACK_DESTINATION_DIFFERS')
        result.update(status='CORE_FEES_RECONCILED',protocol_recipient=a['protocol_fee_recipient_token_account'],
                      protocol_net=p['protocol_fee']-p['buyback_fee'],creator_recipient=a['coin_creator_vault_ata'],
                      creator_fee=p['coin_creator_fee'],buyback_amount=p['buyback_fee'],
                      buyback_recipient_identity_verified=True,buyback_owner=buyback_owner,
                      buyback_recipient_documented=buyback_owner in BUYBACK_RECIPIENTS,
                      historical_global_config_verified=False,buyback_mapping='unique_documented_recipient_ata_pair',
                      cashback=p['cashback'],holder_rewards=p['holder_rewards'],
                      instruction_path=[node['outer_index'],node['inner_index']],residual_transfers=remaining)
    except (ValueError,KeyError,IndexError,TypeError) as exc:
        result['reason']=str(exc) if isinstance(exc,ValueError) else 'MISSING_OR_MALFORMED_FIELDS'
    return result
