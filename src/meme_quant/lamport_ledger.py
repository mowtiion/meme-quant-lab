"""Rent-independent lamport replay, including native-token account lifecycles.

Proves modeled instruction cash movements against every account's post-lamports.
Does not invent stored rent reserves or claim a separate SyncNative token-amount proof.
"""
import re
from .decoder import unbase58
from .reserve_ledger import account_keys
from .token_ledger import PROGRAMS, NATIVE, ordered_instructions, NO_AMOUNT_CHANGE

SYSTEM = '11111111111111111111111111111111'


def u64(value):
    if type(value) is not int or not 0 <= value < 2**64:
        raise ValueError('INVALID_U64')
    return value


def system_movement(data, accounts):
    """Decode stable bincode SystemInstruction layouts; fail on unknown variants."""
    if len(data) < 4:
        raise ValueError('MALFORMED_SYSTEM_INSTRUCTION')
    tag = int.from_bytes(data[:4], 'little')
    def read(offset):
        if offset+8 > len(data):
            raise ValueError('MALFORMED_SYSTEM_INSTRUCTION')
        return int.from_bytes(data[offset:offset+8], 'little')
    def require(size, count):
        if len(data) != size or len(accounts) < count:
            raise ValueError('MALFORMED_SYSTEM_INSTRUCTION')
    if tag == 0:
        require(52,2)
        return 'create', accounts[0], accounts[1], read(4)
    if tag in (2,5):
        require(12,2 if tag==2 else 5)
        return 'transfer' if tag==2 else 'withdraw_nonce', accounts[0], accounts[1], read(4)
    if tag == 3:
        length = read(36)
        if length > 32:
            raise ValueError('INVALID_SYSTEM_SEED')
        require(92+length,2)
        data[44:44+length].decode('utf-8')
        return 'create_with_seed', accounts[0], accounts[1], read(44+length)
    if tag == 11:
        length = read(12)
        if length > 32:
            raise ValueError('INVALID_SYSTEM_SEED')
        require(52+length,3)
        data[20:20+length].decode('utf-8')
        return 'transfer_with_seed', accounts[0], accounts[2], read(4)
    # Known state-only operations do not move lamports; binary structure still checked.
    fixed = {1:36, 4:4, 6:36, 7:36, 8:12, 12:4}
    if tag in fixed:
        require(fixed[tag],1)
        return None
    if tag in (9,10):
        length = read(36)
        if length>32:
            raise ValueError('INVALID_SYSTEM_SEED')
        require((84 if tag==9 else 76)+length,1)
        data[44:44+length].decode('utf-8')
        return None
    raise ValueError('UNSUPPORTED_SYSTEM_INSTRUCTION_'+str(tag))


def reconcile_lamports(tx):
    result = {'status':'UNRESOLVED','movements':[], 'lifecycles':[], 'mismatches':[],
              'native_accounts':[], 'rent_assumed':False, 'sync_token_amounts_independently_verified':False}
    try:
        meta=tx['meta']
        if meta['err'] is not None:
            raise ValueError('FAILED_TRANSACTION')
        logs=meta.get('logMessages')
        if not isinstance(logs,list) or any('Log truncated' in s or re.match(r'Program \w+ failed:',s) for s in logs):
            raise ValueError('INCOMPLETE_OR_FAILED_INNER_EXECUTION')
        keys=account_keys(tx)
        if len(set(keys))!=len(keys):
            raise ValueError('DUPLICATE_ACCOUNT_KEYS')
        if len(meta['preBalances'])!=len(keys) or len(meta['postBalances'])!=len(keys):
            raise ValueError('MISSING_LAMPORT_BOUNDARY')
        pre=[u64(v) for v in meta['preBalances']]; post=[u64(v) for v in meta['postBalances']]
        live=list(pre); fee=u64(meta['fee'])
        live[0]=u64(live[0]-fee)
        result['fee']=fee
        identities={}; active=set(); generations={}; native=set()
        def index(i):
            if type(i) is not int or not 0<=i<len(keys):
                raise ValueError('INVALID_ACCOUNT_INDEX')
            return i
        for row in meta['preTokenBalances']:
            i=index(row['accountIndex'])
            if i in identities or row.get('programId') not in PROGRAMS:
                raise ValueError('INVALID_TOKEN_IDENTITY')
            identities[i]=(row['mint'],row['programId']); active.add(i)
            if row['mint']==NATIVE:
                native.add(i)
        def move(kind,source,destination,amount,position):
            amount=u64(amount)
            if source!=destination:
                if live[source]<amount:
                    result['blocked_movement']={'kind':kind,'source':keys[source],
                        'destination':keys[destination],'lamports':amount,
                        'modeled_source_balance':live[source],'position':position}
                    raise ValueError('MODELED_INTERMEDIATE_FUNDS_DEFICIT')
                live[source]=u64(live[source]-amount)
                live[destination]=u64(live[destination]+amount)
            result['movements'].append({'kind':kind,'source':keys[source],'destination':keys[destination],
                                        'lamports':amount,'position':position})
        for top,inner,ix in ordered_instructions(tx):
            program=keys[index(ix['programIdIndex'])]
            accounts=[index(i) for i in ix['accounts']]
            pos=[top,inner]
            if program not in PROGRAMS | {SYSTEM}:
                continue  # Unmodeled direct program changes must survive as post-state residuals.
            data=unbase58(ix['data'])
            if program==SYSTEM:
                movement=system_movement(data,accounts)
                if movement:
                    kind,source,destination,amount=movement
                    if kind in ('create','create_with_seed') and live[destination]!=0:
                        raise ValueError('CREATE_NONZERO_ACCOUNT')
                    move(kind,source,destination,amount,pos)
                continue
            if not data:
                raise ValueError('EMPTY_TOKEN_INSTRUCTION')
            tag=data[0]
            if tag in (1,16,18):
                if len(data)!=(1 if tag==1 else 33) or len(accounts)<2:
                    raise ValueError('MALFORMED_INITIALIZATION')
                account=accounts[0]; mint=keys[accounts[1]]
                if account in active:
                    raise ValueError('INITIALIZE_ACTIVE_ACCOUNT')
                identities[account]=(mint,program); active.add(account)
                generations[account]=generations.get(account,0)+1
                if mint==NATIVE:
                    native.add(account)
                result['lifecycles'].append({'kind':'initialize','account':keys[account], 'mint':mint,
                    'generation':generations[account],'lamports':live[account],'position':pos})
            elif tag in (3,12):
                if len(data)!=(10 if tag==12 else 9) or len(accounts)<(4 if tag==12 else 3):
                    raise ValueError('MALFORMED_TOKEN_TRANSFER')
                source=accounts[0]; destination=accounts[2] if tag==12 else accounts[1]
                known={identities[a][0] for a in (source,destination) if a in identities}
                if tag==12:known.add(keys[accounts[1]])
                if len(known)!=1:
                    raise ValueError('MISSING_OR_CONFLICTING_TRANSFER_MINT')
                mint=next(iter(known))
                for a in (source,destination):
                    if a not in active or identities[a]!=(mint,program):
                        raise ValueError('INACTIVE_OR_CONFLICTING_TOKEN_ACCOUNT')
                if mint==NATIVE:
                    native.update((source,destination))
                    move('native_token_transfer',source,destination,int.from_bytes(data[1:9],'little'),pos)
            elif tag==9:
                if len(data)!=1 or len(accounts)<3 or accounts[0]==accounts[1]:
                    raise ValueError('MALFORMED_CLOSE')
                account=accounts[0]
                if account not in active or identities[account][1]!=program:
                    raise ValueError('CLOSE_WITHOUT_ACCOUNT_IDENTITY')
                amount=live[account]
                move('close_token_account',account,accounts[1],amount,pos)
                result['lifecycles'].append({'kind':'close','account':keys[account],
                    'mint':identities[account][0],'generation':generations.get(account,0),
                    'lamports_returned':amount,'position':pos})
                active.remove(account); del identities[account]
            elif tag==17:
                if len(data)!=1 or len(accounts)<1 or identities.get(accounts[0])!=(NATIVE,program) or accounts[0] not in active:
                    raise ValueError('INVALID_SYNC_NATIVE')
                native.add(accounts[0])
                result['lifecycles'].append({'kind':'sync_native','account':keys[accounts[0]],
                    'generation':generations.get(accounts[0],0),'lamports':live[accounts[0]],'position':pos})
            elif tag in (7,8,14,15):
                if len(data)!=(10 if tag in (14,15) else 9) or len(accounts)<3:
                    raise ValueError('MALFORMED_MINT_BURN')
                mint=keys[accounts[0] if tag in (7,14) else accounts[1]]
                if mint==NATIVE:
                    raise ValueError('NATIVE_MINT_BURN_INVALID')
            elif tag not in NO_AMOUNT_CHANGE:
                raise ValueError('UNSUPPORTED_TOKEN_INSTRUCTION_'+str(tag))
        result['native_accounts']=[keys[i] for i in sorted(native)]
        result['reused_accounts']=[keys[i] for i,count in generations.items() if count>1]
        result['mismatches']=[{'account':keys[i],'predicted':live[i],'observed':post[i],
                               'residual':post[i]-live[i]} for i in range(len(keys)) if live[i]!=post[i]]
        if result['mismatches']:
            result['status']='UNEXPLAINED_LAMPORT_CHANGES'
        elif sum(pre)-sum(post)!=fee:
            raise ValueError('TOTAL_LAMPORT_CONSERVATION_FAILED')
        else:
            result['status']='LAMPORTS_RECONCILED'
    except (ValueError,KeyError,IndexError,TypeError) as exc:
        result['reason']=str(exc) if isinstance(exc,ValueError) else 'MALFORMED_METADATA'
        # Partial replay is diagnostic only; never treat it as reconciled cash flow.
    return result
