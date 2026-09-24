"""Event-attributed Pump payouts and volume-account closures, without fitted residuals."""
from .decoder import PUMP, AMM, ZERO, SOL, unbase58
from .event_scope import EventScope


def program_movements(tx, rows, decoders):
    scope = EventScope(tx)
    schedule = {}; seen = set()
    def add(end, kind, source, destination, amount, event):
        if amount is not None and (type(amount) is not int or not 0 <= amount < 2**64):
            raise ValueError('INVALID_DIRECT_AMOUNT')
        if source == destination:
            raise ValueError('ALIASED_DIRECT_ACCOUNTS')
        schedule.setdefault(end, []).append({'kind':kind,'source':source,'destination':destination,
            'amount':amount,'event_index':event['event_index']})
    for event in rows:
        program = event['program']; name = event['name']; p = event['payload']
        if program not in (PUMP,AMM):continue
        if program == PUMP and name == 'ClaimCashbackEvent':
            node,a,spec=scope.bind(event,decoders[program],{'claim_cashback','claim_cashback_v2'})
            if spec['name']=='claim_cashback_v2' and a['quote_mint']!=SOL:
                continue
            if p['user']!=a['user']:raise ValueError('CASHBACK_CLAIM_IDENTITY_DIFFERS')
            if node['position'] in seen:raise ValueError('DUPLICATE_DIRECT_EVENT')
            seen.add(node['position'])
            add(scope.end(node),'claim_cashback',a['user_volume_accumulator'],a['user'],p['amount'],event)
        elif name == 'CloseUserVolumeAccumulatorEvent':
            node,a,spec = scope.bind(event,decoders[program],{'close_user_volume_accumulator'})
            if p['user'] != a['user'] or len(unbase58(node['instruction']['data'])) != 8:
                raise ValueError('VOLUME_CLOSE_IDENTITY_DIFFERS')
            if node['position'] in seen:raise ValueError('DUPLICATE_DIRECT_EVENT')
            seen.add(node['position'])
            add(scope.end(node),'close_volume_account',a['user_volume_accumulator'],a['user'],None,event)
        elif program == PUMP and name == 'TradeEvent' and not p['is_buy']:
            if p['quote_mint'] != ZERO:
                continue  # Non-native quote flows are represented by token instructions.
            node,a,spec = scope.bind(event,decoders[PUMP],{'sell','sell_v2'})
            if spec['name']=='sell_v2':
                a['mint']=a['base_mint']
                if a['quote_mint']!=SOL:raise ValueError('DIRECT_NATIVE_QUOTE_ACCOUNT_DIFFERS')
            if node['position'] in seen:raise ValueError('DUPLICATE_DIRECT_EVENT')
            seen.add(node['position'])
            if p.get('_missing_trailing_fields') or p['quote_mint'] != ZERO or p['ix_name'] != 'sell':
                raise ValueError('UNSUPPORTED_DIRECT_SELL_VARIANT')
            if any(a[k] != p[k] for k in ('mint','user','fee_recipient')):
                raise ValueError('DIRECT_SELL_IDENTITY_DIFFERS')
            raw=unbase58(node['instruction']['data'])
            if len(raw)!=24 or int.from_bytes(raw[8:16],'little')!=p['token_amount']:
                raise ValueError('DIRECT_SELL_AMOUNT_DIFFERS')
            extra=node['accounts'][len(spec['accounts']):]
            # Published legacy layout: optional cashback accumulator, curve-v2, buyback.
            if spec['name']=='sell' and len(extra)!=(3 if p['cashback'] else 2):
                raise ValueError('UNSUPPORTED_DIRECT_SELL_ACCOUNTS')
            if spec['name']=='sell_v2':
                if extra:raise ValueError('UNSUPPORTED_DIRECT_SELL_ACCOUNTS')
                extra=[a['user_volume_accumulator'],a['buyback_fee_recipient']]
            if p['sol_amount']!=p['quote_amount'] or p['holder_rewards'] not in (0,p['creator_fee']):
                raise ValueError('DIRECT_FEE_ALIAS_DIFFERS')
            if p['cashback'] and (p['creator_fee'] or p['holder_rewards']):
                raise ValueError('DIRECT_FEE_VARIANT_DIFFERS')
            q=p['sol_amount']; fee=p['fee']; creator=p['creator_fee']+p['cashback']; buyback=p['buyback_fee']
            net=q-fee-creator
            if net<int.from_bytes(raw[16:24],'little'):
                raise ValueError('DIRECT_SELL_MINIMUM_NOT_MET')
            end=scope.end(node); source=a['bonding_curve']
            add(end,'pump_sell_user',source,a['user'],net,event)
            add(end,'pump_sell_protocol',source,a['fee_recipient'],fee-buyback,event)
            add(end,'pump_sell_creator_or_reward',source,extra[0] if p['cashback'] else a['creator_vault'],creator,event)
            add(end,'pump_sell_buyback',source,extra[-1],buyback,event)
    return schedule
