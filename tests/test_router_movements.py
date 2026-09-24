import copy
import gzip
import hashlib
import json
import random
import unittest
from pathlib import Path

from meme_quant.decoder import IDLDecoder, base58, unbase58
from meme_quant.event_scope import EventScope
from meme_quant.lamport_ledger import reconcile_lamports
from meme_quant.router_movements import FLASH, REPLENISH, TARGET_LAMPORTS, DEPLOYMENTS, fee_allocations
from sbpf_slice import SliceVM

ROOT = Path(__file__).resolve().parents[1]


class RouterMovements(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence=json.loads((ROOT/'tests/fixtures/router_binary_evidence.json').read_text())
        cls.cases=json.loads((ROOT/'tests/fixtures/router_regression_cases.json').read_text())['cases']
        cls.decoders={d.program:d for d in (IDLDecoder(ROOT/'vendor/pump.json'),IDLDecoder(ROOT/'vendor/pump_amm.json'))}

    def result(self,item):
        return reconcile_lamports(item['tx'],item['rows'],self.decoders)

    def vm(self,program):
        p=self.evidence['programs'][program]
        return SliceVM(bytes.fromhex(p['slice_hex']),p['slice_start'])

    def flash_machine(self,fee,discount,share,recipients):
        vm=self.vm(FLASH);r=vm.registers
        def account(key,balance):
            ptr=vm.allocate(80);vm.write(ptr,255,1)
            vm.memory[ptr+8:ptr+40]=unbase58(key)
            vm.write(ptr+72,balance);return ptr
        source=account(base58(bytes([1])*32),fee+1000)
        destinations=[account(key,0) for key in recipients]
        primary=account(base58(bytes([2])*32),0)
        vector=vm.allocate(40)
        for i,ptr in enumerate([source]+destinations):vm.write(vector+8*i,ptr)
        program_key=vm.allocate(32);vm.memory[program_key:program_key+32]=unbase58(FLASH)
        result=vm.allocate(8)
        r[1:6]=[result,program_key,vector,primary,180000]
        for offset,value in [(4096,fee),(4088,discount),(4080,share)]:vm.write(r[5]-offset,value)
        vm.run()
        self.assertEqual(vm.read(result,4),26)
        self.assertEqual(vm.read(source+72),1000)
        return [vm.read(p+72) for p in destinations],vm.read(primary+72)

    def replenish_machine(self,source,payer):
        vm=self.vm(REPLENISH);array=vm.allocate(48*9);locations=[]
        for index,balance in [(0,source),(8,payer)]:
            cell=vm.allocate(32);value=vm.allocate(8);vm.write(value,balance)
            vm.write(cell+24,value);vm.write(array+48*index+8,cell);locations.append(value)
        vm.write(vm.registers[10]-840,array);vm.write(vm.registers[10]-832,9)
        vm.run()
        return tuple(vm.read(a) for a in locations)

    def test_binary_slices_and_deployment_bounds_are_pinned(self):
        for program,p in self.evidence['programs'].items():
            binary=gzip.decompress((ROOT/p['binary_fixture']).read_bytes())
            self.assertEqual(hashlib.sha256(binary).hexdigest(),p['full_program_sha256'])
            # These deployed ELF text sections have equal file and virtual offsets.
            snippet=binary[p['slice_start']:p['slice_end']]
            self.assertEqual(snippet.hex(),p['slice_hex'])
            self.assertEqual(hashlib.sha256(snippet).hexdigest(),p['slice_sha256'])
            self.assertEqual(DEPLOYMENTS[program],(p['last_deployment_slot'],self.evidence['program_data_context']['slot']))

    def test_flash_formula_matches_deployed_machine_code(self):
        randomizer=random.Random(20260924)
        rates=[(4776442,50,90),(3000,50,60),(0,200,0)]
        rates += [(randomizer.randrange(10**12),randomizer.randrange(201),randomizer.randrange(121)) for _ in range(100)]
        for fee,discount,share in rates:
            keys=[base58(bytes([i+3])*32) if randomizer.choice([True,False]) else FLASH for i in range(3)]+[FLASH]
            amounts,remainder=self.flash_machine(fee,discount,share,keys)
            predicted,rest=fee_allocations(fee,discount,share,keys)
            self.assertEqual([(k,a) for k,a in zip(keys,amounts) if a],predicted)
            self.assertEqual(remainder,rest)

    def test_replenishment_branch_matches_machine_code(self):
        for source,payer in [(1000000,99974500),(1000000,100000000),(1000000,100000001),
                             (1000000,0),(100000000,0),(25499,99974500),(25500,99974500)]:
            needed=max(0,TARGET_LAMPORTS-payer)
            amount=needed if source>=needed else 0
            self.assertEqual(self.replenish_machine(source,payer),(source-amount,payer+amount))

    def test_all_frozen_route_and_replenishment_cases_reconcile(self):
        for item in self.cases:
            with self.subTest(slot=item['slot'],index=item['tx_index']):
                self.assertEqual(self.result(item)['status'],'LAMPORTS_RECONCILED')

    def test_one_lamport_rounding_requires_two_divisions(self):
        item=next(r for r in self.cases if (r['slot'],r['tx_index'])==(449382025,32))
        moves=[m for m in self.result(item)['movements'] if m['kind']=='flash_referral']
        self.assertEqual([m['lamports'] for m in moves],[1612048])
        self.assertEqual(4776442*150*90//40000,1612049)

    def test_replenishment_uses_live_balance_instead_of_fixed_fee(self):
        item=copy.deepcopy(next(r for r in self.cases if (r['slot'],r['tx_index'])==(449382007,255)))
        from meme_quant.reserve_ledger import account_keys
        keys=account_keys(item['tx']);node=EventScope(item['tx']).nodes[0]
        source=keys.index(node['accounts'][0]);payer=keys.index(node['accounts'][8])
        item['tx']['meta']['preBalances'][payer]+=1000
        item['tx']['meta']['postBalances'][source]+=1000
        result=self.result(item)
        self.assertEqual(result['status'],'LAMPORTS_RECONCILED')
        self.assertEqual(next(m['lamports'] for m in result['movements'] if m['kind']=='router_balance_replenishment'),24500)

    def test_postbalance_tamper_does_not_change_predicted_movements(self):
        for program in (FLASH,REPLENISH):
            item=copy.deepcopy(next(r for r in self.cases if any(n['program']==program for n in EventScope(r['tx']).nodes)))
            before=self.result(item)
            item['tx']['meta']['postBalances'][0]+=1
            after=self.result(item)
            self.assertEqual(before['movements'],after['movements'])
            self.assertEqual(after['status'],'UNEXPLAINED_LAMPORT_CHANGES')

    def test_missing_funding_unknown_layout_and_unverified_epoch_reject(self):
        item=copy.deepcopy(self.cases[0]);scope=EventScope(item['tx'])
        node=next(n for n in scope.nodes if n['program']==FLASH and unbase58(n['instruction']['data'])[0]==0)
        node['instruction']['data']=base58(unbase58(node['instruction']['data'])+b'\x00')
        self.assertEqual(self.result(item)['reason'],'UNSUPPORTED_FLASH_ROUTE_LAYOUT')
        item=copy.deepcopy(self.cases[0])
        for row in item['rows']:row['slot']=DEPLOYMENTS[FLASH][1]+1
        self.assertEqual(self.result(item)['reason'],'UNVERIFIED_ROUTER_DEPLOYMENT_SLOT')
        for row in item['rows']:row['slot']=DEPLOYMENTS[FLASH][0]
        self.assertEqual(self.result(item)['reason'],'UNVERIFIED_ROUTER_DEPLOYMENT_SLOT')
        item=copy.deepcopy(self.cases[0]);scope=EventScope(item['tx'])
        node=next(n for n in scope.nodes if n['program']==FLASH and unbase58(n['instruction']['data'])[0]==0)
        funding=scope.nodes[scope.end(node)-1]
        funding['instruction']['accounts'][1]=funding['instruction']['accounts'][0]
        self.assertEqual(self.result(item)['reason'],'FLASH_FEE_FUNDING_AMBIGUOUS')
