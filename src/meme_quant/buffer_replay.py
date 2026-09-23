"""Reconstruct a loader-v3 upload buffer from complete, ordered raw transactions.

The recovered ELF is data only. A binary hash is not a verified source/IDL binding.
"""
import hashlib
import json
from pathlib import Path

from .cpi import instruction_trace, execution_evidence, committed
from .decoder import ZERO, unbase58
from .domain import IntegrityError
from .regimes import LOADER

MAX_PROGRAM_BYTES=8*1024*1024


class BufferReplay:
    def __init__(self, buffer, program, programdata):
        self.buffer,self.program,self.programdata=buffer,program,programdata
        self.data=None;self.covered=None;self.authority=None
        self.initialized=False;self.upgraded=False;self.writes=0;self.overwritten_bytes=0
        self.incoming_transfers=0;self.incoming_lamports=0

    def apply(self, program, accounts, raw):
        if self.buffer not in accounts:return
        if self.upgraded:raise IntegrityError('Buffer reused after target upgrade')
        tag=int.from_bytes(raw[:4],'little') if len(raw)>=4 else -1
        if program==ZERO:
            # System Transfer credits lamports only; it cannot change buffer data.
            # Accept the observed, allocated-buffer recipient case, not withdrawals.
            if tag==2:
                if (len(raw)!=12 or len(accounts)!=2 or accounts[1]!=self.buffer
                        or accounts[0]==self.buffer or self.data is None or not self.initialized):
                    raise IntegrityError('Invalid incoming buffer transfer')
                self.incoming_transfers+=1
                self.incoming_lamports+=int.from_bytes(raw[4:12],'little')
                return
            if tag!=0 or len(raw)!=52 or len(accounts)!=2 or accounts[1]!=self.buffer:
                raise IntegrityError('Unsupported system operation on buffer')
            if raw[20:52]!=unbase58(LOADER) or self.data is not None:
                raise IntegrityError('Invalid buffer allocation or account reuse')
            size=int.from_bytes(raw[12:20],'little')-37
            if not 0<size<=MAX_PROGRAM_BYTES:raise IntegrityError('Invalid buffer allocation size')
            self.data=bytearray(size);self.covered=bytearray(size)
            return
        if program!=LOADER:raise IntegrityError('Unvalidated program operation on buffer')
        if self.data is None:raise IntegrityError('Buffer allocation history missing')
        if tag==0:
            if raw!=bytes(4) or len(accounts)!=2 or accounts[0]!=self.buffer or self.initialized:
                raise IntegrityError('Invalid buffer initialization')
            self.initialized=True;self.authority=accounts[1]
        elif tag==1:
            if not self.initialized or len(accounts)!=2 or accounts!=[self.buffer,self.authority] or len(raw)<16:
                raise IntegrityError('Invalid buffer write authority or encoding')
            offset=int.from_bytes(raw[4:8],'little');size=int.from_bytes(raw[8:16],'little')
            if size!=len(raw)-16 or size==0 or offset+size>len(self.data):
                raise IntegrityError('Invalid buffer write extent')
            self.overwritten_bytes+=sum(self.covered[offset:offset+size])
            self.data[offset:offset+size]=raw[16:]
            self.covered[offset:offset+size]=b'\x01'*size;self.writes+=1
        elif tag==4:
            if raw!=(4).to_bytes(4,'little') or len(accounts)!=3 or accounts[:2]!=[self.buffer,self.authority]:
                raise IntegrityError('Invalid buffer authority change')
            self.authority=accounts[2]
        elif tag==3:
            if raw!=(3).to_bytes(4,'little') or accounts[:3]!=[self.programdata,self.program,self.buffer]:
                raise IntegrityError('Upgrade target mismatch')
            if len(accounts)!=7 or accounts[-1]!=self.authority:
                raise IntegrityError('Upgrade authority mismatch')
            self.finish();self.upgraded=True
        else:raise IntegrityError('Unsupported loader operation on buffer')

    def finish(self):
        if self.data is None or not self.initialized:raise IntegrityError('Missing allocation/initialization')
        if not all(self.covered):raise IntegrityError('Incomplete byte coverage')
        if not self.data.startswith(b'\x7fELF'):raise IntegrityError('Reconstructed bytes lack ELF magic')
        return bytes(self.data)


def read_hashed(root, digest):
    if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
        raise IntegrityError('Invalid raw SHA256')
    raw=(root/'objects'/digest[:2]/f'{digest}.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=digest:raise IntegrityError('Raw SHA256 mismatch')
    return json.loads(raw)


def history_rows(receipts, root, buffer):
    rows=[];previous=None;terminal=False
    for receipt in receipts:
        if receipt['method']!='getSignaturesForAddress':continue
        params=receipt['params']
        if (terminal or params[0]!=buffer or params[1].get('commitment')!='finalized'
                or params[1].get('before')!=previous):
            raise IntegrityError('Non-contiguous buffer history pagination')
        limit=params[1]['limit']
        if type(limit) is not int or not 1<=limit<=1000:raise IntegrityError('Invalid history limit')
        page=read_hashed(root,receipt['raw_sha256'])['result']
        if len(page)>limit:raise IntegrityError('History page exceeds limit')
        if any(r.get('confirmationStatus')!='finalized' for r in page):
            raise IntegrityError('Unfinalized buffer history')
        rows+=page;terminal=len(page)<limit
        if page:previous=page[-1]['signature']
    if not terminal or not rows:raise IntegrityError('Buffer history not exhausted')
    if len({r['signature'] for r in rows})!=len(rows):raise IntegrityError('Duplicate history signature')
    if [r['slot'] for r in rows]!=sorted([r['slot'] for r in rows],reverse=True):
        raise IntegrityError('History is not ordered by descending slot')
    return rows


def reconstruct(manifest, raw_root, program, programdata, target_signature):
    if not manifest.get('complete') or manifest.get('issues') or manifest.get('commitment')!='finalized':
        raise IntegrityError('Incomplete/unfinalized buffer block collection')
    history=history_rows(manifest['history_receipts'],raw_root,manifest['buffer'])
    expected={r['signature']:r for r in history}
    if target_signature not in expected:raise IntegrityError('Target upgrade missing from history')
    slots=sorted({r['slot'] for r in history})
    if [b['slot'] for b in manifest['blocks']]!=slots or manifest['selected_slots']!=slots:
        raise IntegrityError('Block collection does not match buffer history')
    replay=BufferReplay(manifest['buffer'],program,programdata)
    observed=set();operations=[];upgrade=None
    for b in manifest['blocks']:
        block=read_hashed(raw_root,b['raw_sha256'])['result']
        for tx_index,tx in enumerate(block['transactions']):
            message=tx['transaction']['message'];meta=tx.get('meta')
            if meta is None:raise IntegrityError('Missing transaction metadata')
            keys=[k['pubkey'] if isinstance(k,dict) else k for k in message['accountKeys']]
            loaded=meta.get('loadedAddresses') or {};keys+=loaded.get('writable',[])+loaded.get('readonly',[])
            if manifest['buffer'] not in keys:continue
            sig=tx['transaction']['signatures'][0]
            if sig not in expected or sig in observed:raise IntegrityError('Block/history signature mismatch')
            observed.add(sig);entry=expected[sig]
            if entry['slot']!=b['slot'] or entry['err']!=meta['err']:
                raise IntegrityError('Block/history execution mismatch')
            if meta['err'] is not None:continue
            nodes=instruction_trace(tx);execution_evidence(nodes,meta.get('logMessages') or [])
            # Router instructions can carry the buffer but only validated system/
            # loader calls may change it. Unknown leaf calls fail closed.
            for node in nodes:
                if manifest['buffer'] not in node['accounts']:continue
                state=committed(nodes,node['position'])
                if state is False:continue
                if state is None:raise IntegrityError('Buffer operation execution unproven')
                if node['program'] not in {ZERO,LOADER}:
                    if any(n['parent']==node['position'] for n in nodes):continue
                    raise IntegrityError('Unknown leaf program involving buffer')
                data=unbase58(node['instruction']['data'])
                if node['program']==LOADER and data==(3).to_bytes(4,'little') and sig!=target_signature:
                    raise IntegrityError('Unexpected upgrade in buffer history')
                replay.apply(node['program'],node['accounts'],data)
                op={'slot':b['slot'],'tx_index':tx_index,'signature':sig,
                    'instruction_path':[node['outer_index'],node['inner_index']],
                    'program':node['program'],'tag':int.from_bytes(data[:4],'little'),'raw_sha256':b['raw_sha256']}
                operations.append(op)
                if replay.upgraded:upgrade=op
    if observed!=set(expected):raise IntegrityError('Missing history transactions in blocks')
    if not replay.upgraded:raise IntegrityError('Target upgrade not executed')
    binary=replay.finish()
    return binary,{'status':'RECONSTRUCTED_FROM_RPC_HISTORY','program':program,'buffer':manifest['buffer'],
                   'binary_sha256':hashlib.sha256(binary).hexdigest(),'binary_bytes':len(binary),
                   'write_operations':replay.writes,'overwritten_bytes':replay.overwritten_bytes,
                   'incoming_transfers':replay.incoming_transfers,'incoming_lamports':replay.incoming_lamports,
                   'history_transactions':len(history),'blocks':len(slots),'upgrade':upgrade,
                   'operations':operations,'historical_source_idl_binding':'UNPROVEN',
                   'independent_binary_verification':'UNPROVEN'}
