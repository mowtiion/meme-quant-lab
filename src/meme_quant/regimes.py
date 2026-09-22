"""Observe current loader metadata without backdating it into historical regimes."""
import base64
from datetime import datetime, timezone

from solders.pubkey import Pubkey

from .decoder import PUMP, AMM, base58
from .decoder import unbase58
from .cpi import instruction_trace, execution_evidence, committed
from .domain import IntegrityError
from .rpc import RPC
from .storage import store_raw

LOADER = 'BPFLoaderUpgradeab1e11111111111111111111111'
PUBLIC_RPC = 'https://api.mainnet-beta.solana.com'


def upgrade_evidence(block, slot, raw_hash, program):
    """Locate successful loader-v3 Upgrade calls; this does not recover bytecode."""
    expected, _ = Pubkey.find_program_address([bytes(Pubkey.from_string(program))], Pubkey.from_string(LOADER))
    evidence = []
    for tx in block['transactions']:
        if not tx.get('meta') or tx['meta'].get('err') is not None:
            continue
        nodes = instruction_trace(tx)
        candidates = [n for n in nodes if n['program'] == LOADER
                      and unbase58(n['instruction']['data']) == b'\x03\x00\x00\x00'
                      and len(n['accounts']) >= 2 and n['accounts'][1] == program]
        if not candidates:
            continue
        execution_evidence(nodes, tx['meta'].get('logMessages') or [])
        for node in candidates:
            if node['accounts'][0] != str(expected):
                raise IntegrityError('Upgrade ProgramData address mismatch')
            if committed(nodes, node['position']) is not True:
                raise IntegrityError('Upgrade execution is unproven or rolled back')
            evidence.append({'slot':slot,'block_time':block['blockTime'],'program':program,
                             'programdata':str(expected),'signature':tx['transaction']['signatures'][0],
                             'instruction_path':[node['outer_index'],node['inner_index']],
                             'raw_sha256':raw_hash,'instruction':'loader_v3_upgrade',
                             'historical_binary_idl_mapping':'UNPROVEN'})
    return evidence


def account_bytes(envelope, executable):
    result = envelope['result']; value = result['value']
    if (not value or value['owner'] != LOADER or value['executable'] is not executable
            or value['data'][1] != 'base64'):
        raise IntegrityError('Unexpected loader account metadata')
    return base64.b64decode(value['data'][0],validate=True), result['context']['slot']


def programdata_address(program, envelope):
    raw, context = account_bytes(envelope, True)
    if len(raw)!=36 or int.from_bytes(raw[:4],'little')!=2:
        raise IntegrityError('Invalid loader Program account')
    address = base58(raw[4:36])
    expected,_ = Pubkey.find_program_address([bytes(Pubkey.from_string(program))],Pubkey.from_string(LOADER))
    if address != str(expected):
        raise IntegrityError('ProgramData address contradicts loader PDA')
    return address, context


def programdata_header(envelope, minimum_context):
    raw, context = account_bytes(envelope,False)
    if len(raw)!=45 or int.from_bytes(raw[:4],'little')!=3 or raw[12] not in (0,1):
        raise IntegrityError('Invalid ProgramData metadata header')
    slot = int.from_bytes(raw[4:12],'little')
    if type(context) is not int or context < minimum_context or slot > context:
        raise IntegrityError('Inconsistent ProgramData observation slot')
    return {'observed_context_slot':context,'last_modified_slot':slot,
            'upgrade_authority':base58(raw[13:45]) if raw[12] else None,
            'historical_binary_idl_mapping':'UNPROVEN'}


def observe_programs(raw_root):
    """Four bounded requests to the public RPC; metadata only, no credentials."""
    rpc = RPC(PUBLIC_RPC,attempts=1)
    report = {'source':PUBLIC_RPC,'commitment':'finalized',
              'observed_at':datetime.now(timezone.utc).isoformat(),'programs':[], 'issues':[],
              'warning':'Current metadata is not historical bytecode or an IDL deployment interval.'}
    for program in (PUMP,AMM):
        item={'program':program,'requests':[]}; report['programs'].append(item)
        try:
            params=[program,{'commitment':'finalized','encoding':'base64','dataSlice':{'offset':0,'length':36}}]
            envelope,raw=rpc.call('getAccountInfo',params)
            digest,_=store_raw(raw_root,raw); item['requests'].append({'method':'getAccountInfo','params':params,'raw_sha256':digest})
            address,context=programdata_address(program,envelope)
            params=[address,{'commitment':'finalized','encoding':'base64','minContextSlot':context,
                             'dataSlice':{'offset':0,'length':45}}]
            envelope,raw=rpc.call('getAccountInfo',params)
            digest,_=store_raw(raw_root,raw); item['requests'].append({'method':'getAccountInfo','params':params,'raw_sha256':digest})
            item.update(programdata=address,**programdata_header(envelope,context))
        except (ValueError,KeyError,TypeError,IndexError) as exc:
            report['issues'].append({'program':program,'reason':str(exc)})
    return report
