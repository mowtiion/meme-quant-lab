import base64
import copy
import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from solders.account import Account
from solders.clock import Clock
from solders.instruction import AccountMeta, Instruction
from solders.message import Message
from solders.pubkey import Pubkey
from solders.transaction import Transaction
from meme_quant.cpi import instruction_trace, EVENT_IX_TAG
from meme_quant.decoder import IDLDecoder, PUMP, AMM, unbase58
from meme_quant.domain import IntegrityError
from meme_quant.program_binding import ProgramRegistry, decode_config_observation, verify_history_window
from meme_quant.regimes import upgrade_evidence, LOADER
from svm_interfaces import dispatch_checks, config_write_check, virtual_machine, metadata

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT/'tests/fixtures/historical_programs'


class HistoricalPrograms(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ProgramRegistry(ROOT/'vendor/program_registry.json')
        cls.decoders = {n:IDLDecoder(ROOT/'vendor'/n) for n in ('pump.json','pump_amm.json')}
        cls.binaries = {r['id']:gzip.decompress((ROOT/r['binary_fixture']).read_bytes()) for r in cls.registry.regimes}
        cls.observations = json.loads((FIX/'config-observations.json').read_text())

    def test_exact_binary_hashes_and_loader_payload(self):
        for r in self.registry.regimes:
            self.assertEqual(hashlib.sha256(self.binaries[r['id']]).hexdigest(),r['binary_sha256'])
            self.assertEqual(len(self.binaries[r['id']]),r['binary_bytes'])
        obs=json.loads((FIX/'loader-observation.json').read_text());a=obs['accounts'][3]
        raw=base64.b64decode(a['header_base64'])+self.binaries['amm']
        self.assertEqual(hashlib.sha256(raw).hexdigest(),a['account_sha256'])
        self.assertEqual(int.from_bytes(raw[4:12],'little'),446462733)
        self.assertEqual(a['owner'],LOADER)
        self.assertFalse(a['executable'])
        self.assertEqual(len(raw),a['account_bytes'])
        self.assertEqual(str(Pubkey.from_bytes(base64.b64decode(obs['accounts'][1]['header_base64'])[4:])),a['key'])

    def test_registry_slot_boundaries_and_current_pump_excluded(self):
        d=self.decoders['pump.json']
        self.assertEqual(self.registry.bind(d,447000000)['id'],'pump_old')
        self.assertEqual(self.registry.bind(d,449382040)['id'],'pump_sample')
        for slot in (446462760,447228373,449734335,450120404,None,True):
            with self.assertRaises(IntegrityError):self.registry.bind(d,slot)
        a=self.decoders['pump_amm.json']
        self.assertEqual(self.registry.bind(a,450120404)['id'],'amm')
        with self.assertRaises(IntegrityError):self.registry.bind(a,450120405)

    def test_wrong_idl_hash_and_overlapping_intervals_rejected(self):
        d=copy.copy(self.decoders['pump.json']);d.hash='0'*64
        with self.assertRaisesRegex(IntegrityError,'IDL hash'):self.registry.bind(d,449382000)
        data=json.loads((ROOT/'vendor/program_registry.json').read_text());data['regimes'].append(data['regimes'][0])
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'registry.json';p.write_text(json.dumps(data))
            with self.assertRaisesRegex(IntegrityError,'Overlapping'):ProgramRegistry(p)

    def test_programdata_histories_have_only_the_verified_upgrades(self):
        # Old upgrade receipt is pinned independently of ignored local artifacts.
        expected_pump={(446462760,'SgEwKjomLvZgYWZVHkqLZAzB7LHtyQo7hWu5VgYKoVb82jqtz3fum7sAaCB7yzL2GNks5BwRB5wvpuyy4CKFbQV'),
                       (447228373,'5mfXpjh9SFxVq61V6z31nv3Mvp6UopTpjHdNvqimcWioFHQKrhW5apJxn5UFNSjBRAEixdi3bjotprVAgEPhYGmY'),
                       (449734335,'4WRMFG9YnYqbouLzayMGUjJTN3rKdEcApaxdekf5mAxBsx4NdfgKVXTuQZhmWvEa5uLJCVQ9DcSarEmvfQF133kq')}
        pump=json.loads((FIX/'pump-programdata-history.json').read_text())
        self.assertEqual(verify_history_window(pump,446462000,450120404,expected_pump),100)
        amm=json.loads((FIX/'amm-programdata-history.json').read_text())
        self.assertEqual(verify_history_window(amm,446462000,450120404,{(446462733,'3kTQq7ETwHfaq6mfRAYy2NZmiD9Qm7EJ6moPcoU2Wt18tTX9zUFYZ55daC1okHBueQWXqNx9gZxwYGom3N3SQvTD')}),45)
        pump['result'][1]['signature']='unexplained-change'
        with self.assertRaises(IntegrityError):verify_history_window(pump,446462000,450120404,expected_pump)
        with self.assertRaises(IntegrityError):verify_history_window({'result':amm['result'][:1]},446462000,450120404,set())

    def test_upgrade_transactions_are_successful_loader_calls(self):
        fixtures=json.loads((ROOT/'tests/fixtures/real_program_updates.json').read_text())
        latest=json.loads((FIX/'latest-pump-upgrade.json').read_text())['result']
        fixtures.append({'slot':latest['slot'],'blockTime':latest['blockTime'],'transactions':[latest],'raw_block_sha256':hashlib.sha256((FIX/'latest-pump-upgrade.json').read_bytes()).hexdigest()})
        for f,pid in zip(fixtures,[PUMP,AMM,PUMP]):
            self.assertEqual(len(upgrade_evidence(f,f['slot'],f['raw_block_sha256'],pid)),1)

    def test_all_126_declared_selectors_reach_correct_deployed_handler(self):
        count=0
        for r in self.registry.regimes:
            with self.subTest(binary=r['id']):
                count+=len(dispatch_checks(self.decoders[r['idl_file']],self.binaries[r['id']]))
        self.assertEqual(count,126)

    def test_unknown_selectors_and_truncated_required_arguments_fail_in_vm(self):
        for r in self.registry.regimes:
            d=self.decoders[r['idl_file']];pid=Pubkey.from_string(d.program);payer=Pubkey.from_bytes(bytes([19])*32)
            svm=virtual_machine(d.program,self.binaries[r['id']]);svm.set_account(payer,Account(100000000,b'',Pubkey.default()))
            required=next(s for s in d.instructions.values() if s['name']=='toggle_cashback_enabled')
            for data,code in [(bytes.fromhex('0123456789abcdef'),101),(bytes(required['discriminator']),102)]:
                result=svm.send_transaction(Transaction.new_unsigned(Message([Instruction(pid,data,[])],payer)))
                self.assertIn(f'InstructionErrorCustom({code})',str(result.err()))

    def test_nine_config_mutations_and_admin_events_match_deployed_layout(self):
        for r in self.registry.regimes:
            d=self.decoders[r['idl_file']];amm=d.program==AMM;o=self.observations[1 if amm else 0]
            operations=[('toggle_cashback_enabled',{'enabled':False},{'is_cashback_enabled':False}),
                        ('toggle_mayhem_mode',{'enabled':False},{'mayhem_mode_enabled':False})]
            updates={'lp_fee_basis_points':19,'protocol_fee_basis_points':6} if amm else {'fee_basis_points':93,'creator_fee_basis_points':7}
            operations.append(('update_fee_config' if amm else 'set_params',updates,updates))
            for ix,args,expected in operations:
                with self.subTest(binary=r['id'],instruction=ix):
                    before,after,events,encoded=config_write_check(d,self.binaries[r['id']],o,ix,args)
                    self.assertEqual({k:v for k,v in after.items() if before[k]!=v},expected)
                    if ix.startswith('toggle'):
                        self.assertEqual(events,[])
                    else:
                        self.assertEqual(len(events),1)
                        name,payload=events[0]
                        self.assertEqual(name,'UpdateFeeConfigEvent' if amm else 'SetParamsEvent')
                        self.assertNotIn('_missing_trailing_fields',payload)
                        for k,v in expected.items():self.assertEqual(payload[k],v)

    def test_close_vm_reproduces_real_admin_event_bytes_without_promoting_quarantine(self):
        f=json.loads((ROOT/'tests/fixtures/truncated_amm_447000002.json').read_text());tx=f['transactions'][0]
        nodes=instruction_trace(tx);n=next(n for n in nodes if n['program']==AMM and unbase58(n['instruction']['data'])==bytes.fromhex('f945a4da9667548a'))
        a=[Pubkey.from_string(k) for k in n['accounts']];pid=Pubkey.from_string(AMM)
        svm=virtual_machine(AMM,self.binaries['amm']);svm.set_clock(Clock(f['slot'],0,0,0,f['blockTime']))
        svm.set_account(a[0],Account(100000000,b'',Pubkey.default()))
        raw=bytes.fromhex('56ff700e66359afa')+bytes(a[0])+bytes(33)+b'\1'+bytes(16)
        svm.set_account(a[1],Account(1346200,raw.ljust(137,b'\0'),pid))
        metas=[AccountMeta(a[0],True,True),AccountMeta(a[1],False,True),AccountMeta(a[2],False,False),AccountMeta(a[3],False,False)]
        result=svm.send_transaction(Transaction.new_unsigned(Message([Instruction(pid,unbase58(n['instruction']['data']),metas)],a[0])))
        self.assertFalse(hasattr(result,'err'))
        self.assertIsNone(svm.get_account(a[1]));self.assertEqual(svm.get_account(a[0]).lamports,101341200)
        event=next(x for x in nodes if x['position']==n['position']+1)
        payload=unbase58(event['instruction']['data'])[8:]
        inner=result.inner_instructions()[0]
        self.assertIn(EVENT_IX_TAG+payload,[bytes(ix.instruction().data) for ix in inner])
        self.assertEqual(self.decoders['pump_amm.json'].decode(payload)[0],'CloseUserVolumeAccumulatorEvent')

    def test_config_observations_check_owners_addresses_layout_and_slot(self):
        for i,o in enumerate(self.observations):
            d=self.decoders['pump.json' if i%2==0 else 'pump_amm.json']
            v=decode_config_observation(o,d,target_slot=450121512)
            self.assertEqual(v['observed_slot'],450121512)
            for slot in (449382000,447000000,450121513):
                with self.assertRaises(IntegrityError):decode_config_observation(o,d,target_slot=slot)
            for key,val in [('address',str(Pubkey.default())),('type','Unknown')]:
                bad=copy.deepcopy(o);bad[key]=val
                with self.assertRaises(IntegrityError):decode_config_observation(bad,d)
            bad=copy.deepcopy(o);bad['account']['owner']=str(Pubkey.default())
            with self.assertRaises(IntegrityError):decode_config_observation(bad,d)
            bad=copy.deepcopy(o);raw=bytearray(base64.b64decode(bad['account']['data'][0]));raw[0]^=1;bad['account']['data'][0]=base64.b64encode(raw).decode()
            with self.assertRaises(IntegrityError):decode_config_observation(bad,d)

    def test_nonzero_config_extension_is_not_silently_ignored(self):
        o=copy.deepcopy(self.observations[2]);raw=bytearray(base64.b64decode(o['account']['data'][0]));raw[-1]=1;o['account']['data'][0]=base64.b64encode(raw).decode()
        with self.assertRaisesRegex(IntegrityError,'extension'):decode_config_observation(o,self.decoders['pump.json'])
