import base64
import copy
import gzip
import hashlib
import json
import random
import struct
import unittest
from pathlib import Path
from unittest.mock import patch

from meme_quant.decoder import IDLDecoder, base58, unbase58
from meme_quant.economic import audit_transaction
from meme_quant.lamport_ledger import reconcile_lamports
from meme_quant.native_rules import native_reserve, SAMPLE_START, SAMPLE_END
from meme_quant.token_ledger import TOKEN, TOKEN_2022, NATIVE, ordered_instructions
from meme_quant.token_lifecycles import replay_token_lifecycles
from meme_quant.reserve_ledger import account_keys
from sbpf_slice import SliceVM

ROOT = Path(__file__).resolve().parents[1]


class NativeBinaryEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = json.loads((ROOT/'reports/TOKEN_NATIVE_RULES.json').read_text())
        cls.binary = gzip.decompress((ROOT/cls.evidence['program']['fixture']).read_bytes())

    def vm(self,name):
        item = self.evidence['program']['slices'][name]
        return SliceVM(bytes.fromhex(item['hex']),item['start'])

    def test_deployed_binary_and_slices_are_pinned(self):
        e = self.evidence['program']
        self.assertEqual(hashlib.sha256(self.binary).hexdigest(),e['binary_sha256'])
        self.assertEqual(len(self.binary),e['binary_bytes'])
        header = bytes.fromhex(e['programdata_header_hex'])
        self.assertEqual(int.from_bytes(header[:4],'little'),3)
        self.assertEqual(int.from_bytes(header[4:12],'little'),419472000)
        self.assertLess(e['last_deployment'],SAMPLE_START)
        self.assertGreater(e['observed_context']['slot'],SAMPLE_END)
        # ELF64 little-endian section table; no disassembly dependency needed in CI.
        offset = struct.unpack_from('<Q',self.binary,40)[0]
        size,count = struct.unpack_from('<HH',self.binary,58)
        sections = [struct.unpack_from('<IIQQQQIIQQ',self.binary,offset+i*size) for i in range(count)]
        for item in e['slices'].values():
            section = next(s for s in sections if s[3]<=item['start']<s[3]+s[5] and s[2]&4)
            at = section[4]+item['start']-section[3]
            raw = self.binary[at:at+item['end']-item['start']]
            self.assertEqual(raw.hex(),item['hex'])
            self.assertEqual(hashlib.sha256(raw).hexdigest(),item['sha256'])

    def test_feature_activation_evidence_selects_historical_rent(self):
        e = self.evidence; active = {}
        for name,row in zip(e['rent_features']['keys'],e['rent_features']['response']['result']['value']):
            if row is None: continue
            self.assertEqual(row['owner'],'Feature111111111111111111111111111111111111')
            raw = base64.b64decode(row['data'][0]);self.assertEqual(raw[0],1)
            active[name] = int.from_bytes(raw[1:9],'little')
        self.assertEqual(active,{'deprecate_rent_exemption_threshold':407376000,
            'set_lamports_per_byte_to_6333':444096000,'set_lamports_per_byte_to_5080':446256000})
        self.assertLess(max(active.values()),SAMPLE_START)
        rate,threshold,burn = struct.unpack('<QdB',base64.b64decode(e['rent_sysvar']['account']['data'][0]))
        self.assertEqual((rate,threshold),(5080,1))
        self.assertEqual(native_reserve(TOKEN,SAMPLE_START),(165+128)*rate)
        self.assertEqual(native_reserve(TOKEN,SAMPLE_END),1488440)
        for p,slot in [(TOKEN,SAMPLE_START-1),(TOKEN,SAMPLE_END+1),(TOKEN,None),(TOKEN_2022,SAMPLE_START)]:
            with self.assertRaisesRegex(ValueError,'HISTORICAL_NATIVE_RULES_REQUIRED'): native_reserve(p,slot)

    def test_actual_rent_multiply_instructions(self):
        vm = self.vm('rent_multiply');a = vm.allocate(256);vm.registers[8] = a
        vm.write(a+0x50,165);vm.write(vm.registers[10]-16,0x3ff0000000000000)
        vm.write(vm.registers[10]-24,5080);vm.run()
        self.assertEqual(vm.registers[1],native_reserve(TOKEN,SAMPLE_START))
        self.assertEqual(vm.registers[6],0x3ff0000000000000) # threshold=1 fast path

    def test_actual_sync_overwrites_old_reserve_and_token_amount(self):
        rng = random.Random(734)
        for amount in [0,1,550840,10**12]+[rng.randrange(10**14) for _ in range(50)]:
            reserve = native_reserve(TOKEN,SAMPLE_START)
            vm = self.vm('sync_native');a = vm.allocate(256)
            vm.registers[8] = a;vm.registers[7] = 165;vm.registers[1] = reserve
            vm.write(a+0xc4,1,1);vm.write(a+0xc5,1,1)
            vm.write(a+0x48,reserve+amount);vm.write(a+0xc9,2039280);vm.write(a+0x98,10**15)
            vm.run()
            self.assertEqual(vm.read(a+0xc9),reserve)
            self.assertEqual(vm.read(a+0x98),amount)
            self.assertEqual(vm.read(a+0x48),reserve+amount)

    def test_actual_sync_rejects_wrong_size_or_insufficient_lamports(self):
        for size,lamports in [(166,2000000),(165,1488439)]:
            vm=self.vm('sync_native');a=vm.allocate(256)
            vm.registers[8]=a;vm.registers[7]=size;vm.registers[1]=1488440
            vm.write(a+0xc4,1,1);vm.write(a+0xc5,1,1);vm.write(a+0x48,lamports)
            with self.assertRaisesRegex(ValueError,'Jump outside verified slice'):vm.run()

    def test_actual_initialization_and_explicit_unwrap_amount_writes(self):
        vm=self.vm('initialize_native');a=vm.allocate(256);vm.registers[8]=a
        vm.registers[1]=1488440+12345;vm.registers[2]=1488440;vm.run()
        self.assertEqual((vm.read(a+0xc9),vm.read(a+0x98),vm.read(a+0xc5,1)),(1488440,12345,1))
        vm=self.vm('unwrap_remaining');vm.registers[4]=12345;vm.registers[7]=2345;vm.run()
        self.assertEqual(vm.read(vm.registers[10]-360),10000)


class TokenLifecycles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases=json.loads((ROOT/'tests/fixtures/token_lifecycle_cases.json').read_text())
        cls.decoders={d.program:d for d in (IDLDecoder(ROOT/'vendor/pump.json'),IDLDecoder(ROOT/'vendor/pump_amm.json'))}

    def case(self,name):return copy.deepcopy(self.cases[name])
    def sol(self,e):return reconcile_lamports(e['tx'],e['rows'],self.decoders)
    def replay(self,e):return replay_token_lifecycles(e['tx'],self.sol(e),e['slot'])

    def test_all_real_lifecycle_cases_and_shared_production_entrypoint(self):
        for name,e in self.cases.items():
            with self.subTest(name=name):
                result=audit_transaction(e['tx'],e['rows'],self.decoders)
                self.assertEqual(result['status'],'NO_TOKEN_ACCOUNT_ACTIVITY' if name=='no_token_activity' else 'RECONCILED')
                self.assertEqual(result['lamport_check'],self.sol(e))
                self.assertFalse(result['unknown'])

    def test_close_and_reopen_creates_distinct_generations(self):
        r=self.replay(self.case('reuse'))
        groups={}
        for l in r['lifetimes']:groups.setdefault(l['account'],[]).append(l)
        repeated=[ls for ls in groups.values() if len(ls)>1]
        self.assertTrue(repeated)
        for ls in repeated:
            self.assertTrue(all(a['end']<b['start'] for a,b in zip(ls,ls[1:])))
            self.assertEqual(len({l['generation'] for l in ls}),len(ls))

    def test_single_token_tamper_is_rejected_while_sol_still_matches(self):
        e=self.case('surviving_native');keys=account_keys(e['tx'])
        native=next(l['account'] for l in self.replay(e)['lifetimes'] if l.get('initial_reserve') and not l.get('end'))
        row=next(r for r in e['tx']['meta']['postTokenBalances'] if keys[r['accountIndex']]==native)
        row['uiTokenAmount']['amount']=str(int(row['uiTokenAmount']['amount'])+1)
        self.assertEqual(self.sol(e)['status'],'LAMPORTS_RECONCILED')
        r=self.replay(e);self.assertEqual(r['status'],'PARTIAL')
        self.assertIn('TOKEN_DELTA_DIFFERS',{a.get('reason') for a in r['accounts']})

    def test_historical_rent_must_not_be_replaced_by_old_constant(self):
        with patch('meme_quant.token_lifecycles.native_reserve',return_value=2039280):
            self.assertNotEqual(self.replay(self.case('surviving_native'))['status'],'RECONCILED')

    def test_missing_or_wrong_epoch_does_not_assume_rent(self):
        e=self.case('transient_native');sol=self.sol(e)
        for slot in [None,SAMPLE_START-1,SAMPLE_END+1]:
            r=replay_token_lifecycles(e['tx'],sol,slot)
            self.assertEqual(r['reason'],'HISTORICAL_NATIVE_RULES_REQUIRED')

    def test_native_close_accounts_for_remaining_units(self):
        r=self.replay(self.case('transient_native'))
        closed=[l for l in r['lifetimes'] if l.get('end') and l['mint']==NATIVE]
        self.assertTrue(closed)
        for l in closed:
            self.assertEqual(l['amount'],0)
            self.assertEqual(l['operations'][-1]['delta'],-l['amount_at_close'])

    def test_unwrap_all_and_explicit_amount_have_same_actual_effect(self):
        e=self.case('unwrap_all');r=self.replay(e)
        flow=next(f for f in r['flows'] if f['kind']=='unwrap')
        keys=account_keys(e['tx'])
        ix=next(ix for _,_,ix in ordered_instructions(e['tx']) if keys[ix['programIdIndex']]==TOKEN and unbase58(ix['data'])[:1]==b'\x2d')
        ix['data']=base58(b'\x2d\x01'+flow['amount'].to_bytes(8,'little'))
        self.assertEqual(self.replay(e)['status'],'RECONCILED')
        ix['data']=base58(b'\x2d\x01'+(flow['amount']+1).to_bytes(8,'little'))
        self.assertNotEqual(self.replay(e)['status'],'RECONCILED')

    def test_unreconciled_cash_flow_cannot_certify_token_lifecycles(self):
        e=self.case('transient_native');sol=self.sol(e);sol['status']='UNEXPLAINED_LAMPORT_CHANGES'
        self.assertEqual(replay_token_lifecycles(e['tx'],sol,e['slot'])['reason'],'RECONCILED_LAMPORT_REPLAY_REQUIRED')

    def test_missing_instruction_time_lamports_cannot_use_post_state(self):
        e=self.case('transient_native');sol=self.sol(e);sol['lifecycles']=[]
        self.assertEqual(replay_token_lifecycles(e['tx'],sol,e['slot'])['reason'],'LAMPORT_LIFECYCLE_MISSING')

    def test_account_reinitialized_before_close_is_rejected(self):
        e=self.case('reuse');sol=self.sol(e);keys=account_keys(e['tx'])
        # The independently supplied cash trace cannot rescue invalid token ordering.
        for _,_,ix in ordered_instructions(e['tx']):
            if keys[ix['programIdIndex']]==TOKEN and unbase58(ix['data'])[:1]==b'\x09':
                ix['data']=base58(b'\x04'+bytes(8));break
        self.assertEqual(replay_token_lifecycles(e['tx'],sol,e['slot'])['reason'],'INITIALIZE_ACTIVE_ACCOUNT')

    def test_unsupported_instruction_is_not_counted_as_no_activity(self):
        e=self.case('no_token_activity');sol=self.sol(e)
        keys=e['tx']['transaction']['message']['accountKeys'];keys.append(TOKEN)
        e['tx']['transaction']['message']['instructions'].append({'programIdIndex':len(keys)-1,'accounts':[],'data':base58(bytes([99]))})
        r=replay_token_lifecycles(e['tx'],sol,e['slot'])
        self.assertEqual(r['reason'],'UNSUPPORTED_TOKEN_EXTENSION')
        self.assertEqual(r['status'],'UNRESOLVED')
