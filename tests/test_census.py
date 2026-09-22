import base64
import copy
import json
import tempfile
import unittest
from pathlib import Path

from meme_quant.census import audit_block, audit_manifests, create_arguments, holder_creator
from meme_quant.decoder import IDLDecoder, PUMP, Reader, base58, unbase58
from meme_quant.domain import IntegrityError
from meme_quant.regimes import LOADER, programdata_address, programdata_header, upgrade_evidence
from meme_quant.storage import store_raw, json_bytes
from solders.pubkey import Pubkey

ROOT=Path(__file__).resolve().parents[1]


class CensusAudit(unittest.TestCase):
    def setUp(self):
        self.decoder=IDLDecoder(ROOT/'vendor/pump.json')
        self.fixtures=json.loads((ROOT/'tests/fixtures/real_launches.json').read_text())
        self.f=copy.deepcopy(self.fixtures[0])

    def audit(self,f=None):
        f=f or self.f
        return audit_block(f,f['slot'],f['raw_block_sha256'],self.decoder)

    def create_ix(self,f=None):
        f=f or self.f
        return next(ix for ix in f['transactions'][0]['transaction']['message']['instructions']
                    if unbase58(ix['data'])[:8] in self.decoder.instructions and
                    self.decoder.instructions[unbase58(ix['data'])[:8]]['name']=='create_v2')

    def test_six_real_launches_match_including_regimes(self):
        rows=[]
        for f in self.fixtures:
            r,issues,_=self.audit(f)
            self.assertEqual(issues,[])
            self.assertEqual(len(r),1)
            self.assertEqual(r[0]['status'],'PASS')
            rows+=r
        self.assertEqual(sum(r['regime_observed']['is_mayhem_mode'] for r in rows),2)
        self.assertEqual(sum(r['regime_observed']['is_holder_reward'] for r in rows),1)
        self.assertTrue(all(r['historical_program_version']=='UNVALIDATED' for r in rows))

    def test_holder_rewards_creator_is_derived_not_input_wallet(self):
        r,issues,_=self.audit(self.fixtures[2]);r=r[0]
        self.assertEqual(issues,[])
        self.assertNotEqual(r['input_creator'],r['event_creator'])
        self.assertEqual(r['event_creator'],'AUrq8QNERDZpT5HTgukkAbcYamLjY5fhFTfn2SGBeD3G')
        self.assertEqual(holder_creator(r['mint']),r['event_creator'])
        self.assertEqual(r['creator_role'],'holder_rewards_pda')

    def test_optional_eof_fields_remain_omitted_not_guessed(self):
        r,_,_=self.audit();r=r[0]
        self.assertEqual(r['omitted_arguments'],['creator_fee_bps','is_holder_reward'])
        self.assertNotIn('is_holder_reward',r['arguments'])
        self.assertFalse(r['regime_observed']['is_holder_reward'])

    def test_tuple_struct_bool_decodes_without_option_tag(self):
        self.assertEqual(Reader(b'\x01',self.decoder.types).read({'defined':{'name':'OptionBool'}}),[True])
        with self.assertRaises(IntegrityError):
            Reader(b'\x02',self.decoder.types).read({'defined':{'name':'OptionBool'}})

    def test_changed_instruction_creator_fails(self):
        ix=self.create_ix();raw=bytearray(unbase58(ix['data']));raw[-34]^=1;ix['data']=base58(raw)
        r,issues,_=self.audit()
        self.assertEqual(r[0]['status'],'FAIL')
        self.assertTrue(issues)

    def test_missing_create_event_blocks(self):
        tx=self.f['transactions'][0]
        from meme_quant.decoder import decode_block
        rows,_=decode_block(self.f,self.f['slot'],self.f['raw_block_sha256'],{PUMP:self.decoder})
        for r in rows:
            if r['name']=='CreateEvent':tx['meta']['logMessages'][r['event_index']]='Program log: removed'
        r,issues,_=self.audit()
        self.assertEqual(r[0]['status'],'FAIL')
        self.assertIn('CREATE_RECONCILIATION_FAILED',[i['reason'] for i in issues])

    def test_duplicate_create_event_blocks(self):
        from meme_quant.decoder import decode_block
        rows,_=decode_block(self.f,self.f['slot'],self.f['raw_block_sha256'],{PUMP:self.decoder})
        index=next(r['event_index'] for r in rows if r['name']=='CreateEvent')
        logs=self.f['transactions'][0]['meta']['logMessages'];logs.insert(index,logs[index])
        r,issues,_=self.audit()
        self.assertEqual(r[0]['status'],'FAIL');self.assertTrue(issues)

    def test_unknown_discriminator_is_not_silently_excluded(self):
        ix=self.create_ix();ix['data']=base58(b'UNKNOWN!'+unbase58(ix['data'])[8:])
        rows,issues,inventory=self.audit()
        self.assertEqual(rows,[])
        self.assertEqual(inventory['UNKNOWN'],1)
        self.assertIn('UNKNOWN_PUMP_INSTRUCTION',[i['reason'] for i in issues])
        self.assertIn('ORPHAN_CREATE_EVENT',[i['reason'] for i in issues])

    def test_extra_instruction_bytes_rejected(self):
        f=copy.deepcopy(self.fixtures[1]);ix=self.create_ix(f);ix['data']=base58(unbase58(ix['data'])+b'\x00')
        rows,issues,_=self.audit(f)
        self.assertEqual(rows[0]['status'],'FAIL');self.assertTrue(issues)

    def test_partial_optional_integer_is_not_eof_default(self):
        f=copy.deepcopy(self.fixtures[1]);ix=self.create_ix(f);ix['data']=base58(unbase58(ix['data'])[:-5])
        rows,issues,_=self.audit(f)
        self.assertEqual(rows[0]['status'],'FAIL');self.assertTrue(issues)

    def test_missing_required_instruction_bytes_rejected(self):
        ix=self.create_ix();raw=unbase58(ix['data']);spec=self.decoder.instructions[raw[:8]]
        with self.assertRaises(IntegrityError):create_arguments(raw[:10],spec,self.decoder)

    def test_wrong_mint_cannot_match_event_by_transaction_alone(self):
        self.create_ix()['accounts'][0]=0
        rows,issues,_=self.audit()
        self.assertEqual(rows[0]['status'],'FAIL');self.assertTrue(issues)

    def test_missing_inner_instructions_blocks_census(self):
        self.f['transactions'][0]['meta'].pop('innerInstructions')
        rows,issues,_=self.audit()
        self.assertEqual(rows,[])
        self.assertIn('CENSUS_TRACE_UNPROVEN',[i['reason'] for i in issues])

    def test_failed_transactions_are_not_launches(self):
        self.f['transactions'][0]['meta']['err']={'InstructionError':[1,'Custom']}
        self.assertEqual(self.audit(),([],[],{}))

    def manifest(self,root):
        digest,_=store_raw(root,json_bytes({'result':self.f}))
        enum,_=store_raw(root,json_bytes({'result':[self.f['slot']]}))
        manifest={'commitment':'finalized','complete':True,'start_slot':self.f['slot'],'end_slot':self.f['slot'],
                  'blocks':[{'slot':self.f['slot'],'raw_sha256':digest}], 'enumeration_sha256':enum,
                  'enumerated_slots':[self.f['slot']]}
        path=root/'manifest.json';path.write_bytes(json_bytes(manifest));return path

    def test_internal_agreement_does_not_unlock_independent_or_historical_gates(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=self.manifest(root)
            report=audit_manifests([path],root,ROOT/'vendor')
            self.assertEqual(report['gates']['local_create_instruction_event_agreement'],'PASS')
            self.assertEqual(report['status'],'FAIL')
            self.assertFalse(report['continue_to_exp001'])
            self.assertEqual(report['gates']['independent_launch_census'],'UNPROVEN')
            self.assertEqual(report['gates']['historical_program_binary_idl_mapping'],'UNPROVEN')

    def test_overlapping_manifests_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=self.manifest(root)
            with self.assertRaisesRegex(IntegrityError,'Overlapping'):
                audit_manifests([path,path],root,ROOT/'vendor')


class DeploymentEvidence(unittest.TestCase):
    def envelope(self,raw,executable=False,slot=100):
        return {'result':{'context':{'slot':slot},'value':{'owner':LOADER,'executable':executable,
                'data':[base64.b64encode(raw).decode(),'base64']}}}

    def header(self,slot=90,tag=1):
        return (3).to_bytes(4,'little')+slot.to_bytes(8,'little')+bytes([tag])+bytes(32)

    def test_current_metadata_never_proves_historical_mapping(self):
        r=programdata_header(self.envelope(self.header()),99)
        self.assertEqual(r['last_modified_slot'],90)
        self.assertEqual(r['historical_binary_idl_mapping'],'UNPROVEN')

    def test_wrong_owner_rejected(self):
        e=self.envelope(self.header());e['result']['value']['owner']=PUMP
        with self.assertRaises(IntegrityError):programdata_header(e,0)

    def test_future_upgrade_slot_and_stale_context_rejected(self):
        for e,minimum in [(self.envelope(self.header(101)),0),(self.envelope(self.header()),101)]:
            with self.subTest(minimum=minimum),self.assertRaises(IntegrityError):programdata_header(e,minimum)

    def test_bad_option_tag_and_short_header_rejected(self):
        for raw in [self.header(tag=2),self.header()[:-1]]:
            with self.subTest(raw=raw),self.assertRaises(IntegrityError):programdata_header(self.envelope(raw),0)

    def test_programdata_pointer_must_match_loader_pda(self):
        expected,_=Pubkey.find_program_address([bytes(Pubkey.from_string(PUMP))],Pubkey.from_string(LOADER))
        raw=(2).to_bytes(4,'little')+bytes(expected)
        self.assertEqual(programdata_address(PUMP,self.envelope(raw,True)),(str(expected),100))
        bad=raw[:4]+bytes(32)
        with self.assertRaises(IntegrityError):programdata_address(PUMP,self.envelope(bad,True))

    def test_two_real_program_upgrades_have_committed_instruction_evidence(self):
        fixtures=json.loads((ROOT/'tests/fixtures/real_program_updates.json').read_text())
        from meme_quant.decoder import AMM
        for f,program in zip(fixtures,[PUMP,AMM]):
            result=upgrade_evidence(f,f['slot'],f['raw_block_sha256'],program)
            self.assertEqual(len(result),1)
            self.assertEqual(result[0]['instruction'],'loader_v3_upgrade')
            self.assertEqual(result[0]['historical_binary_idl_mapping'],'UNPROVEN')

    def test_successful_transaction_without_inner_upgrade_success_is_unproven(self):
        f=json.loads((ROOT/'tests/fixtures/real_program_updates.json').read_text())[0]
        f['transactions'][0]['meta']['logMessages']=[]
        with self.assertRaises(IntegrityError):upgrade_evidence(f,f['slot'],f['raw_block_sha256'],PUMP)

    def test_wrong_upgrade_programdata_account_is_rejected(self):
        f=json.loads((ROOT/'tests/fixtures/real_program_updates.json').read_text())[0]
        for group in f['transactions'][0]['meta']['innerInstructions']:
            for ix in group['instructions']:
                if unbase58(ix['data'])==bytes.fromhex('03000000'):
                    ix['accounts'][0]=0
        with self.assertRaises(IntegrityError):upgrade_evidence(f,f['slot'],f['raw_block_sha256'],PUMP)

    def test_immutable_program_header_preserves_absent_authority(self):
        self.assertIsNone(programdata_header(self.envelope(self.header(tag=0)),0)['upgrade_authority'])


if __name__=='__main__':unittest.main()
