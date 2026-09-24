"""Compare consecutive observed token boundaries across a complete block sequence.

Includes intervening non-target and failed transactions. Missing token metadata on a
funded account is unknown, never an invented zero. This checks RPC state continuity,
not every instruction's economics or the stored native reserve.
"""
from collections import Counter
from .reserve_ledger import account_keys
from .token_ledger import PROGRAMS


def token_snapshot(tx, field, keys):
    rows=tx['meta'].get(field)
    if not isinstance(rows,list):raise ValueError('MISSING_TOKEN_BALANCE_LIST')
    out={}
    for row in rows:
        i=row['accountIndex'];v=row['uiTokenAmount'];amount=v['amount']
        if type(i) is not int or not 0<=i<len(keys) or keys[i] in out:
            raise ValueError('INVALID_OR_DUPLICATE_TOKEN_INDEX')
        if not isinstance(amount,str) or not amount.isascii() or not amount.isdigit() or not 0<=int(amount)<2**64:
            raise ValueError('INVALID_TOKEN_INTEGER')
        if row.get('programId') not in PROGRAMS or not isinstance(row.get('owner'),str):
            raise ValueError('MISSING_TOKEN_IDENTITY')
        if type(v['decimals']) is not int or not 0<=v['decimals']<=255:
            raise ValueError('INVALID_TOKEN_DECIMALS')
        out[keys[i]]={'kind':'TOKEN','amount':int(amount),'mint':row['mint'],
                      'program':row['programId'],'owner':row['owner'],'decimals':v['decimals']}
    return out


class TokenContinuity:
    def __init__(self):
        self.last={};self.counts=Counter();self.issues=[];self.previous_block=None
        self.slot_counts={}

    def observe_block(self,slot,block):
        if self.previous_block is not None:
            old_slot,old_hash=self.previous_block
            if slot!=old_slot+1 or block['parentSlot']!=old_slot or block['previousBlockhash']!=old_hash:
                raise ValueError('NONCONTIGUOUS_BLOCK_CHAIN')
        self.previous_block=(slot,block['blockhash'])
        before=self.counts.copy()
        for index,tx in enumerate(block['transactions']):self.observe_transaction(slot,index,tx)
        self.slot_counts[str(slot)]=dict(self.counts-before)

    def observe_transaction(self,slot,index,tx):
        self.counts['transactions']+=1
        meta=tx['meta']
        if meta is None:raise ValueError('MISSING_TRANSACTION_METADATA')
        self.counts['failed_transactions_included']+=int(meta['err'] is not None)
        keys=account_keys(tx)
        if len(keys)!=len(set(keys)):raise ValueError('DUPLICATE_ACCOUNT_KEYS')
        for field in ('preBalances','postBalances'):
            if len(meta[field])!=len(keys) or any(type(v) is not int or not 0<=v<2**64 for v in meta[field]):
                raise ValueError('INVALID_LAMPORT_BOUNDARY')
        pre=token_snapshot(tx,'preTokenBalances',keys);post=token_snapshot(tx,'postTokenBalances',keys)
        for i,account in enumerate(keys):
            if account not in pre and account not in post and account not in self.last:continue
            a=pre.get(account,{'kind':'ABSENT' if meta['preBalances'][i]==0 else 'UNKNOWN'})
            b=post.get(account,{'kind':'ABSENT' if meta['postBalances'][i]==0 else 'UNKNOWN'})
            location={'slot':slot,'tx_index':index}
            old=self.last.get(account)
            if old is None:
                self.counts['first_observations']+=1
            elif old['state']['kind']=='UNKNOWN' or a['kind']=='UNKNOWN':
                self.counts['unprovable_links']+=1
                self.issues.append({'reason':'MISSING_TOKEN_BOUNDARY','account':account,'previous':old,'current':location,'pre':a})
            elif old['state']!=a:
                self.counts['discontinuities']+=1
                self.issues.append({'reason':'TOKEN_BOUNDARY_DISCONTINUITY','account':account,'previous':old,'current':location,'pre':a})
            else:
                self.counts['matching_links']+=1
                self.counts['matching_token_links' if a['kind']=='TOKEN' else 'matching_absent_links']+=1
                self.counts['cross_slot_matching_links']+=int(old['slot']!=slot)
            if a['kind']=='ABSENT' and b['kind']=='TOKEN':self.counts['creation_boundaries']+=1
            if a['kind']=='TOKEN' and b['kind']=='ABSENT':self.counts['closure_boundaries']+=1
            if a['kind']=='UNKNOWN' or b['kind']=='UNKNOWN':self.counts['unknown_boundaries']+=1
            if meta['err'] is not None and a!=b:
                self.counts['failed_transaction_changes']+=1
                self.issues.append({'reason':'FAILED_TRANSACTION_TOKEN_CHANGE','account':account,'current':location,'pre':a,'post':b})
            self.last[account]={**location,'state':b}

    def result(self):
        blocked=any(self.counts[k] for k in ('unprovable_links','discontinuities','unknown_boundaries','failed_transaction_changes'))
        return {'status':'TOKEN_CONTINUITY_BLOCKED' if blocked else 'TOKEN_BOUNDARY_CONTINUITY_RECONCILED',
                'counts':dict(self.counts),'unique_observed_accounts':len(self.last),'slots':self.slot_counts,
                'issues':self.issues,'stored_native_reserve_verified':False,
                'instruction_economics_verified':False}
