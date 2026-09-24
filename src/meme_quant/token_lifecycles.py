"""Chronological token amounts with distinct account generations and native rules.

The independently reconciled SOL replay supplies instruction-time lamports, never
post-state-derived adjustments. Token instructions then predict every token amount,
including transient accounts; final token metadata is comparison-only.
"""
import re
from collections import defaultdict
from .decoder import unbase58
from .reserve_ledger import account_keys
from .token_ledger import PROGRAMS, NATIVE, NO_AMOUNT_CHANGE, ordered_instructions
from .token_extensions import effect_data
from .native_rules import native_reserve


def integer(value):
    if type(value) is not int or not 0 <= value < 2**64:
        raise ValueError('TOKEN_AMOUNT_OUT_OF_RANGE')
    return value


def replay_token_lifecycles(tx, lamport_check, slot):
    result = {'status':'UNRESOLVED', 'accounts':[], 'flows':[], 'unknown':[],
              'lifetimes':[], 'native_reserve_verified':False}
    try:
        meta = tx['meta']
        if meta['err'] is not None:
            raise ValueError('FAILED_TRANSACTION')
        logs = meta.get('logMessages')
        if not isinstance(logs,list) or any('Log truncated' in s or re.match(r'Program \w+ failed:',s) for s in logs):
            raise ValueError('INCOMPLETE_OR_FAILED_INNER_EXECUTION')
        if lamport_check.get('status') != 'LAMPORTS_RECONCILED':
            raise ValueError('RECONCILED_LAMPORT_REPLAY_REQUIRED')
        keys = account_keys(tx)
        if len(keys) != len(set(keys)):
            raise ValueError('DUPLICATE_ACCOUNT_KEYS')
        decimals = {}
        def checked_decimals(mint, value):
            if type(value) is not int or not 0 <= value <= 255:
                raise ValueError('INVALID_DECIMALS')
            if mint in decimals and decimals[mint] != value:
                raise ValueError('MINT_DECIMALS_CONFLICT')
            decimals[mint] = value
        def snapshot(field):
            out = {}
            for row in meta[field]:
                i = row['accountIndex']
                if type(i) is not int or not 0 <= i < len(keys):
                    raise ValueError('INVALID_ACCOUNT_INDEX')
                account = keys[i]
                if account in out: raise ValueError('DUPLICATE_BALANCE')
                if row.get('programId') not in PROGRAMS: raise ValueError('MISSING_TOKEN_PROGRAM')
                amount = row['uiTokenAmount']['amount']
                if not isinstance(amount,str) or not amount.isascii() or not amount.isdigit():
                    raise ValueError('INVALID_INTEGER_AMOUNT')
                checked_decimals(row['mint'],row['uiTokenAmount']['decimals'])
                out[account] = (row['mint'],row['programId'],integer(int(amount)))
            return out
        pre, post = snapshot('preTokenBalances'), snapshot('postTokenBalances')
        active, generations, identities = {}, defaultdict(int), {}
        instruction_delta, lifecycle_delta = defaultdict(int), defaultdict(int)
        cash_lifecycles = {}
        for row in lamport_check['lifecycles']:
            key = (tuple(row['position']),row['kind'],row['account'])
            if key in cash_lifecycles: raise ValueError('DUPLICATE_LAMPORT_LIFECYCLE')
            cash_lifecycles[key] = row
        def cash_at(position, kind, account):
            row = cash_lifecycles.get((tuple(position),kind,account))
            if row is None: raise ValueError('LAMPORT_LIFECYCLE_MISSING')
            return integer(row['lamports'])
        def begin(account,mint,program,amount,position):
            if account in active: raise ValueError('INITIALIZE_ACTIVE_ACCOUNT')
            if position is not None: generations[account] += 1
            state = {'account':account,'generation':generations[account], 'mint':mint,
                     'program':program,'start':position,'initial_amount':amount,
                     'amount':amount,'operations':[]}
            active[account] = state; identities[account] = (mint,program)
            result['lifetimes'].append(state)
            return state
        for account,(mint,program,amount) in pre.items():
            begin(account,mint,program,amount,None)
        def require(account,program,mint=None):
            state = active.get(account)
            if state is None or state['program'] != program or (mint is not None and state['mint'] != mint):
                raise ValueError('INACTIVE_OR_CONFLICTING_TOKEN_ACCOUNT')
            return state
        def change(state,delta,kind,position,lifecycle=False):
            state['amount'] = integer(state['amount']+delta)
            (lifecycle_delta if lifecycle else instruction_delta)[state['account']] += delta
            state['operations'].append({'kind':kind,'delta':delta,'amount':state['amount'],'position':position})
        native_operations = 0
        def key_at(index):
            if type(index) is not int or not 0 <= index < len(keys):
                raise ValueError('INVALID_ACCOUNT_INDEX')
            return keys[index]
        for top,inner,ix in ordered_instructions(tx):
            program = key_at(ix['programIdIndex'])
            if program not in PROGRAMS: continue
            a = [key_at(i) for i in ix['accounts']]; pos = [top,inner]
            data = effect_data(program,unbase58(ix['data']),a)
            if data is None: continue
            if not data: raise ValueError('EMPTY_TOKEN_INSTRUCTION')
            tag = data[0]
            if tag in (1,16,18):
                if len(data) != (1 if tag==1 else 33) or len(a)<2:
                    raise ValueError('MALFORMED_INITIALIZATION')
                amount = 0; reserve = None
                if a[1] == NATIVE:
                    reserve = native_reserve(program,slot)
                    amount = integer(cash_at(pos,'initialize',a[0])-reserve)
                    native_operations += 1
                state = begin(a[0],a[1],program,amount,pos)
                lifecycle_delta[a[0]] += amount
                if reserve is not None: state['initial_reserve'] = reserve
            elif tag in (3,7,8,12,14,15):
                checked = tag in (12,14,15)
                if len(data) != (10 if checked else 9) or len(a)<(4 if tag==12 else 3):
                    raise ValueError('MALFORMED_TOKEN_FLOW')
                amount = int.from_bytes(data[1:9],'little')
                kind = 'transfer' if tag in (3,12) else 'mint' if tag in (7,14) else 'burn'
                source = a[0] if kind!='mint' else None
                dest = (a[2] if tag==12 else a[1]) if kind=='transfer' else a[1] if kind=='mint' else None
                mint = a[1] if tag in (8,12,15) else a[0] if kind=='mint' else require(source,program)['mint']
                if checked: checked_decimals(mint,data[9])
                src = require(source,program,mint) if source is not None else None
                dst = require(dest,program,mint) if dest is not None else None
                if kind != 'transfer' and mint == NATIVE: raise ValueError('NATIVE_MINT_BURN_INVALID')
                if src is not None and src['amount'] < amount: raise ValueError('TOKEN_INTERMEDIATE_FUNDS_DEFICIT')
                if source != dest:
                    if src is not None: change(src,-amount,kind,pos)
                    if dst is not None: change(dst,amount,kind,pos)
                result['flows'].append({'kind':kind,'program':program,'mint':mint,'amount':amount,
                    'source':source,'destination':dest,'authority':a[3] if tag==12 else a[2],
                    'top_index':top,'inner_index':inner})
            elif tag == 17:
                if len(data)!=1 or not a: raise ValueError('MALFORMED_SYNC')
                state = require(a[0],program,NATIVE)
                reserve = native_reserve(program,slot)
                amount = integer(cash_at(pos,'sync_native',a[0])-reserve)
                change(state,amount-state['amount'],'sync_native',pos,True)
                state['operations'][-1]['reserve'] = reserve
                native_operations += 1
            elif tag == 45:
                if len(a)<3 or len(data) not in (2,10) or data[1] not in (0,1) or len(data)!=(2 if data[1]==0 else 10):
                    raise ValueError('MALFORMED_UNWRAP_LAMPORTS')
                state = require(a[0],program,NATIVE)
                if a[0]==a[1]: raise ValueError('INVALID_UNWRAP_SOURCE')
                # Bytecode applicability of this new classic-token opcode is sample scoped.
                native_reserve(program,slot)
                amount = state['amount'] if data[1]==0 else int.from_bytes(data[2:10],'little')
                change(state,-amount,'unwrap',pos)
                result['flows'].append({'kind':'unwrap','program':program,'mint':NATIVE,'amount':amount,
                    'source':a[0],'destination':None,'lamport_destination':a[1],
                    'authority':a[2],'top_index':top,'inner_index':inner})
            elif tag == 9:
                if len(data)!=1 or len(a)<3 or a[0]==a[1]: raise ValueError('MALFORMED_CLOSE')
                state = require(a[0],program)
                if state['mint'] != NATIVE and state['amount'] != 0:
                    raise ValueError('CLOSE_NONZERO_NONNATIVE_ACCOUNT')
                state['amount_at_close'] = state['amount']
                change(state,-state['amount'],'close',pos,True)
                state['end'] = pos; del active[a[0]]
            elif tag not in NO_AMOUNT_CHANGE:
                result['unknown'].append({'program':program,'tag':tag,'top_index':top,'inner_index':inner,'accounts':a})
                raise ValueError('UNSUPPORTED_TOKEN_EXTENSION')
        for account in sorted(set(identities)|set(post)):
            state = active.get(account)
            predicted = state['amount'] if state else 0
            observed = post[account][2] if account in post else 0
            reason = None
            if (state is None) != (account not in post): reason = 'MISSING_ACCOUNT_BOUNDARY'
            elif state and (state['mint'],state['program']) != post[account][:2]: reason = 'ACCOUNT_IDENTITY_CHANGED'
            elif predicted != observed: reason = 'TOKEN_DELTA_DIFFERS'
            mint,program = identities.get(account,post.get(account,(None,None))[:2])
            before = pre.get(account,(None,None,0))[2]
            if before+instruction_delta[account]+lifecycle_delta[account] != predicted:
                raise ValueError('TOKEN_LIFECYCLE_CONSERVATION_FAILED')
            row = {'account':account,'mint':mint,'program':program,'before':before,'after':observed,
                   'predicted':predicted,'instruction_delta':instruction_delta[account],
                   'lifecycle_delta':lifecycle_delta[account], 'status':'UNRESOLVED' if reason else 'RECONCILED'}
            if reason: row['reason'] = reason
            result['accounts'].append(row)
        result['native_operations_verified'] = native_operations
        result['native_reserve_verified'] = bool(native_operations)
        result['status'] = ('NO_TOKEN_ACCOUNT_ACTIVITY' if not result['accounts'] else
                            'RECONCILED' if all(a['status']=='RECONCILED' for a in result['accounts']) else 'PARTIAL')
    except (ValueError,TypeError,IndexError,KeyError) as exc:
        result['reason'] = str(exc) if isinstance(exc,ValueError) else 'MALFORMED_METADATA'
    return result
