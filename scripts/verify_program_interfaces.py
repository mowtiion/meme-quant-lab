"""Reproduce deployed-interface checks and actual sample argument dispatch offline.

Usage: PYTHONPATH=src:tests python scripts/verify_program_interfaces.py ARCHIVE --out REPORT
Uses frozen deployed bytes and explicitly synthetic VM account state. No RPC,
transaction signing, submission, historical-state defaults or source-build claims.
"""
import argparse
import base64
import gzip
import hashlib
import io
import json
import zipfile
from collections import Counter
from pathlib import Path
from solders.account import Account
from solders.instruction import Instruction
from solders.message import Message
from solders.pubkey import Pubkey
from solders.transaction import Transaction
from meme_quant.cpi import instruction_trace, EVENT_IX_TAG
from meme_quant.decoder import IDLDecoder, PUMP, AMM, unbase58
from meme_quant.program_binding import ProgramRegistry, decode_config_observation
from svm_interfaces import dispatch_checks, config_write_check, virtual_machine, metadata
from verify_alchemy_phase_b import verify


def check(artifact):
    verified=verify(artifact)
    registry=ProgramRegistry(Path('vendor/program_registry.json'))
    decoders={d.program:d for d in [IDLDecoder(Path('vendor/pump.json')),IDLDecoder(Path('vendor/pump_amm.json'))]}
    binaries={r['id']:gzip.decompress(Path(r['binary_fixture']).read_bytes()) for r in registry.regimes}
    for r in registry.regimes:
        if hashlib.sha256(binaries[r['id']]).hexdigest()!=r['binary_sha256']:raise ValueError('Frozen binary hash differs')
    observations=json.loads(Path('tests/fixtures/historical_programs/config-observations.json').read_text())
    config=[decode_config_observation(o,decoders[PUMP if i%2==0 else AMM]) for i,o in enumerate(observations)]
    interfaces={};mutations=[]
    for r in registry.regimes:
        d=decoders[r['program']];binary=binaries[r['id']]
        interfaces[r['id']]=dispatch_checks(d,binary)
        amm=d.program==AMM
        operations=[('toggle_cashback_enabled',{'enabled':False}),('toggle_mayhem_mode',{'enabled':False}),
            ('update_fee_config',{'lp_fee_basis_points':19,'protocol_fee_basis_points':6}) if amm else ('set_params',{'fee_basis_points':93,'creator_fee_basis_points':7})]
        for ix,args in operations:
            before,after,events,_=config_write_check(d,binary,observations[1 if amm else 0],ix,args)
            mutations.append({'regime':r['id'],'instruction':ix,'synthetic_input':True,
                'changed':{k:{'before':before[k],'after':v} for k,v in after.items() if before[k]!=v},'events':events})
    payer=Pubkey.from_bytes(bytes([19])*32);machines={}
    for r in registry.regimes:
        svm=virtual_machine(r['program'],binaries[r['id']]);svm.set_account(payer,Account(1000000000,b'',Pubkey.default()));machines[r['id']]=svm
    seen=set();counts=Counter();transactions=0;self_events=0
    def inspect(tx,slot):
        nonlocal transactions,self_events
        if not tx.get('meta') or tx['meta']['err'] is not None:return
        target=[n for n in instruction_trace(tx) if n['program'] in decoders]
        if not target:return
        transactions+=1
        for n in target:
            d=decoders[n['program']];r=registry.bind(d,slot);raw=unbase58(n['instruction']['data'])
            if raw.startswith(EVENT_IX_TAG):self_events+=1;continue
            spec=d.instructions.get(raw[:8])
            if spec is None:raise ValueError('Unknown sample instruction discriminator')
            counts[(r['id'],spec['name'])]+=1
            key=(r['id'],raw)
            if key in seen:continue
            seen.add(key)
            result=machines[r['id']].send_transaction(Transaction.new_unsigned(Message([Instruction(Pubkey.from_string(d.program),raw,[])],payer)))
            logs=metadata(result).logs();handlers=[s.split('Instruction: ',1)[1] for s in logs if s.startswith('Program log: Instruction: ')]
            if len(handlers)!=1 or handlers[0].replace('_','').lower()!=spec['name'].replace('_','').lower() or 'InstructionErrorCustom(3005)' not in str(result.err()):
                raise ValueError('Actual instruction arguments/selector differ from deployed interface: '+spec['name'])
    with zipfile.ZipFile(artifact) as outer:
        for entry in outer.namelist():
            if not entry.endswith('.zip'):continue
            with zipfile.ZipFile(io.BytesIO(outer.read(entry))) as part:
                for name in part.namelist():
                    if name=='comparison.json' or not name.endswith('.json'):continue
                    slot=int(Path(name).stem);block=json.loads(part.read(name))['result']
                    for tx in block['transactions']:inspect(tx,slot)
    sample_transactions=transactions
    # Six real launch fixtures additionally exercise the older deployment interval
    # and historical EOF-tolerant create arguments without inventing their values.
    launches=json.loads(Path('tests/fixtures/real_launches.json').read_text())
    for f in launches:
        for tx in f['transactions']:inspect(tx,f['slot'])
    return {'status':'LIMITED_DEPLOYED_INTERFACE_CHECKS_PASS','artifact_sha256':verified['artifact_sha256'],
        'registry_sha256':registry.sha256,'regimes':registry.regimes,'vm_instruction_interfaces':interfaces,
        'vm_config_mutations':mutations,'current_config_observations':config,
        'actual_instruction_checks':{'sample_transactions':sample_transactions,'additional_fixture_transactions':transactions-sample_transactions,
            'unique_argument_payloads_checked':len(seen),'self_cpi_events_deferred_to_existing_decoder':self_events,
            'instruction_counts':[{'regime':a,'instruction':b,'count':n} for (a,b),n in sorted(counts.items())]},
        'historical_config_verified':False,'complete_program_semantics_verified':False,
        'verified_source_build':False,'administrative_quarantine_promoted':False,'pilot_ready':False,'network_requests':0}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('artifact',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    result=check(a.artifact);a.out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result['actual_instruction_checks'],indent=2))
