"""Local VM checks against frozen deployed programs; no RPC or wallet signatures."""
import base64
import re
from solders.account import Account
from solders.clock import Clock
from solders.instruction import AccountMeta, Instruction
from solders.litesvm import LiteSVM
from solders.message import Message
from solders.pubkey import Pubkey
from solders.transaction import Transaction
from meme_quant.decoder import Reader


def encode(value, typ, types):
    if isinstance(typ,str):
        if typ=='pubkey':return bytes(Pubkey.from_string(value))
        if typ=='bool':return bytes([int(value)])
        if typ=='string':
            raw=value.encode();return len(raw).to_bytes(4,'little')+raw
        if re.fullmatch('[ui](8|16|32|64|128)',typ):return value.to_bytes(int(typ[1:])//8,'little',signed=typ[0]=='i')
    if 'defined' in typ:
        fields=types[typ['defined']['name']]['fields']
        if all(isinstance(f,dict) and 'name' in f for f in fields):
            return b''.join(encode(value[f['name']],f['type'],types) for f in fields)
        if len(value)!=len(fields):raise ValueError('Tuple field count differs')
        return b''.join(encode(v,f,types) for f,v in zip(fields,value))
    if 'option' in typ:return b'\0' if value is None else b'\1'+encode(value,typ['option'],types)
    if 'vec' in typ:return len(value).to_bytes(4,'little')+b''.join(encode(v,typ['vec'],types) for v in value)
    if 'array' in typ:
        if len(value)!=typ['array'][1]:raise ValueError('Array length differs')
        return b''.join(encode(v,typ['array'][0],types) for v in value)
    raise ValueError(typ)


def default_value(typ,types):
    if isinstance(typ,str):return str(Pubkey.default()) if typ=='pubkey' else '' if typ=='string' else False if typ=='bool' else 0
    if 'defined' in typ:
        fields=types[typ['defined']['name']]['fields']
        return {f['name']:default_value(f['type'],types) for f in fields} if all(isinstance(f,dict) and 'name' in f for f in fields) else [default_value(f,types) for f in fields]
    if 'option' in typ:return None
    if 'vec' in typ:return []
    if 'array' in typ:return [default_value(typ['array'][0],types) for _ in range(typ['array'][1])]
    raise ValueError(typ)


def virtual_machine(program,binary):
    svm=LiteSVM().with_sigverify(False).with_blockhash_check(False)
    svm.add_program(Pubkey.from_string(program),binary)
    svm.set_clock(Clock(449382000,0,0,0,1790080924))
    return svm


def metadata(result):return result.meta() if hasattr(result,'meta') else result


def dispatch_checks(decoder,binary):
    svm=virtual_machine(decoder.program,binary);payer=Pubkey.from_bytes(bytes([19])*32)
    svm.set_account(payer,Account(100000000,b'',Pubkey.default()));pid=Pubkey.from_string(decoder.program)
    out=[]
    for spec in decoder.instructions.values():
        args=b''.join(encode(default_value(a['type'],decoder.types),a['type'],decoder.types) for a in spec['args'])
        data=bytes(spec['discriminator'])+args
        r=svm.send_transaction(Transaction.new_unsigned(Message([Instruction(pid,data,[])],payer)))
        logs=metadata(r).logs();ixlogs=[s.split('Instruction: ',1)[1] for s in logs if s.startswith('Program log: Instruction: ')]
        if len(ixlogs)!=1 or ixlogs[0].replace('_','').lower()!=spec['name'].replace('_','').lower():raise ValueError('Instruction selector routed incorrectly')
        if 'InstructionErrorCustom(3005)' not in str(r.err()):raise ValueError('Encoded arguments did not reach account validation')
        out.append({'instruction':spec['name'],'argument_bytes':len(args),'handler_log':ixlogs[0],'account_validation_reached':True})
    return out


def config_write_check(decoder,binary,observation,instruction,updates):
    pid=Pubkey.from_string(decoder.program);svm=virtual_machine(decoder.program,binary)
    account=observation['account'];key=Pubkey.from_string(observation['address']);raw=base64.b64decode(account['data'][0])
    typ=observation['type'];before=Reader(raw[8:],decoder.types).read({'defined':{'name':typ}})
    admin=Pubkey.from_string(before.get('authority',before.get('admin')))
    svm.set_account(admin,Account(100000000,b'',Pubkey.default()))
    svm.set_account(key,Account(account['lamports'],raw,pid))
    event_authority=Pubkey.find_program_address([b'__event_authority'],pid)[0]
    addresses={'global':key,'global_config':key,'authority':admin,'admin':admin,'event_authority':event_authority,'program':pid}
    spec=next(s for s in decoder.instructions.values() if s['name']==instruction)
    args={a['name']:updates.get(a['name'],before.get(a['name'])) for a in spec['args']}
    data=bytes(spec['discriminator'])+b''.join(encode(args[a['name']],a['type'],decoder.types) for a in spec['args'])
    metas=[AccountMeta(addresses[a['name']],bool(a.get('signer')),bool(a.get('writable'))) for a in spec['accounts']]
    if instruction=='set_params':
        metas += [AccountMeta(Pubkey.from_string(k),False,False) for k in [before['fee_recipient']]+before['fee_recipients']]
        for meta in metas[len(spec['accounts']):]:
            svm.set_account(meta.pubkey,Account(100000000,b'',Pubkey.default()))
    result=svm.send_transaction(Transaction.new_unsigned(Message([Instruction(pid,data,metas)],admin)))
    if hasattr(result,'err'):raise ValueError(str(result))
    after=Reader(svm.get_account(key).data[8:],decoder.types).read({'defined':{'name':typ}})
    emitted=[decoder.decode(base64.b64decode(s[14:])) for s in result.logs() if s.startswith('Program data: ')]
    return before,after,emitted,args
