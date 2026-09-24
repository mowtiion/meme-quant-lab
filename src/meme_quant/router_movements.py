"""Native movements recovered from pinned deployed FLASH and 3s1rA binaries.

Amounts depend on instruction bytes, successful System CPIs, or modeled live
balances. Post balances are never inputs. Unsupported layouts/epochs fail closed.
"""
from .decoder import ZERO, SOL, unbase58

FLASH = 'FLASHX8DrLbgeR8FcfNV1F5krxYcYMUdBkrP1EPBtxB9'
REPLENISH = '3s1rAymURnacreXreMy718GfqW6kygQsLNka1xDyW8pC'
TARGET_LAMPORTS = 100_000_000
# Upper bounds are the finalized program-data observation slot, pinned below.
DEPLOYMENTS = {FLASH: (449187226, 450107290), REPLENISH: (447884446, 450107290)}
FLASH_LAYOUTS = {
    (0, bytes.fromhex('2c')):32, (1, bytes.fromhex('2b')):30,
    (0, bytes.fromhex('2a00')):45, (1, bytes.fromhex('2a00')):43,
    (0, bytes.fromhex('0d0e2e00')):80,
    (1, bytes.fromhex('2d0e0d00')):79, (1, bytes.fromhex('2a0e0d00')):74,
}


def fee_allocations(amount, discount, referral_share, recipients):
    if type(amount) is not int or not 0 <= amount < 2**64:
        raise ValueError('INVALID_ROUTER_FEE')
    if not 0 <= discount <= 200 or not 0 <= referral_share <= 120:
        raise ValueError('UNSUPPORTED_ROUTER_RATE')
    if len(recipients) != 4 or recipients[-1] != FLASH:
        raise ValueError('UNSUPPORTED_ROUTER_FOURTH_REFERRAL')
    weighted = amount*(200-discount)
    net = weighted//200
    if weighted >= 2**64 or net*max(referral_share,3) >= 2**64:
        raise ValueError('ROUTER_FEE_MULTIPLICATION_OVERFLOW')
    # The deployed code divides before multiplying by the first referral rate.
    amounts = (net*referral_share//200, net*3//100, weighted//10000)
    payments = [(recipient, value) for recipient, value in zip(recipients[:3], amounts)
                if recipient != FLASH and value]
    remaining = amount-sum(v for _,v in payments)
    if remaining < 0:
        raise ValueError('ROUTER_DISTRIBUTION_EXCEEDS_FEE')
    return payments, remaining


def program_movements(scope, rows):
    from .lamport_ledger import system_movement
    schedule = {}
    def add(position, kind, source, destination, amount=None, **extra):
        if source == destination:
            raise ValueError('ALIASED_ROUTER_MOVEMENT')
        schedule.setdefault(position, []).append({'kind':kind, 'source':source,
            'destination':destination, 'amount':amount, 'event_index':None, **extra})
    for node in scope.nodes:
        program = node['program']
        if program not in DEPLOYMENTS:
            continue
        slots = {r.get('slot') for r in rows}
        lo, hi = DEPLOYMENTS[program]
        # The deployment slot itself may contain pre-upgrade transactions.
        if len(slots)!=1 or not all(type(s) is int and lo<s<=hi for s in slots):
            raise ValueError('UNVERIFIED_ROUTER_DEPLOYMENT_SLOT')
        raw = unbase58(node['instruction']['data']); a = node['accounts']
        if not raw:
            raise ValueError('EMPTY_ROUTER_INSTRUCTION')
        if program == FLASH:
            if raw[0] != 0:
                if ((raw[0]==1 and len(raw)==10 and len(a)==5)
                        or (raw==b'\x05' and len(a)==7)
                        or (raw[0]==7 and not a)):
                    continue  # Preparation has modeled CPIs; self-event has no accounts.
                raise ValueError('UNSUPPORTED_FLASH_INSTRUCTION')
            if len(raw)<22 or len(raw)!=21+raw[18] or FLASH_LAYOUTS.get((raw[17],raw[19:-2]))!=len(a):
                raise ValueError('UNSUPPORTED_FLASH_ROUTE_LAYOUT')
            if a[3]!=ZERO or a[4]!=FLASH or a[-6]!=FLASH:
                raise ValueError('FLASH_ACCOUNT_LAYOUT_DIFFERS')
            vault=a[-5]
            children=scope.nodes[node['position']+1:scope.end(node)]
            funding=[]
            for child in children:
                if child['program']!=ZERO:
                    continue
                movement=system_movement(unbase58(child['instruction']['data']),child['accounts'])
                if movement and movement[2]==vault:
                    funding.append((child,movement))
            if len(funding)!=1:
                raise ValueError('FLASH_FEE_FUNDING_AMBIGUOUS')
            child,movement=funding[0]
            if (movement[:3]!=('transfer',a[1],vault) or child['parent']!=node['position']
                    or child['position']+1!=scope.end(node)):
                raise ValueError('FLASH_FEE_FUNDING_SCOPE_DIFFERS')
            payments,remainder=fee_allocations(movement[3],raw[-2],raw[-1],a[-4:])
            for destination,amount in payments:
                add(scope.end(node),'flash_referral',vault,destination,amount)
            if remainder:
                add(scope.end(node),'flash_fee_remainder',vault,a[2],remainder)
        else:
            if (len(raw)!=6 or raw[0] not in (0,1) or len(a)!=(38 if raw[0]==0 else 42)
                    or node['depth']!=1 or a[1]!=SOL or a[5]!=ZERO
                    or a[7]!='Sysvar1nstructions1111111111111111111111111'):
                raise ValueError('UNSUPPORTED_REPLENISH_LAYOUT')
            add(scope.end(node),'router_balance_replenishment',a[0],a[8],
                target_lamports=TARGET_LAMPORTS, insufficient_source='skip')
    return schedule
