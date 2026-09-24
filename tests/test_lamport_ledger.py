import copy
import unittest
import json
from pathlib import Path
from meme_quant.decoder import base58
from meme_quant.lamport_ledger import SYSTEM, reconcile_lamports, system_movement
from meme_quant.token_ledger import TOKEN, NATIVE


class LamportLedger(unittest.TestCase):
    def setUp(self):
        self.keys=['payer','temporary','pool',NATIVE,TOKEN,SYSTEM,'authority']
        self.tx={'transaction':{'signatures':['sig'],'message':{'accountKeys':self.keys,'instructions':[]}},
                 'meta':{'err':None,'logMessages':[],'innerInstructions':[], 'fee':5,
                 'preBalances':[1000,0,300,1,1,1,1],'postBalances':[945,0,350,1,1,1,1],
                 'preTokenBalances':[{'accountIndex':2,'mint':NATIVE,'programId':TOKEN}],
                 'postTokenBalances':[{'accountIndex':2,'mint':NATIVE,'programId':TOKEN}]}}
        self.create(200);self.initialize();self.transfer(1,2,50);self.close()

    def append(self,program,accounts,data):
        self.tx['transaction']['message']['instructions'].append({'programIdIndex':program,'accounts':accounts,'data':base58(data)})

    def create(self,amount):self.append(5,[0,1],(0).to_bytes(4,'little')+amount.to_bytes(8,'little')+(165).to_bytes(8,'little')+bytes(32))
    def initialize(self):self.append(4,[1,3,6],bytes([1]))
    def close(self):self.append(4,[1,0,6],bytes([9]))
    def transfer(self,source,dest,amount):self.append(4,[source,3,dest,6],bytes([12])+amount.to_bytes(8,'little')+bytes([9]))
    def result(self):return reconcile_lamports(self.tx)

    def test_wrap_transfer_close_without_rent_assumption(self):
        r=self.result();self.assertEqual(r['status'],'LAMPORTS_RECONCILED')
        self.assertFalse(r['rent_assumed']);self.assertFalse(r['sync_token_amounts_independently_verified'])
        self.assertEqual(r['movements'][-1]['lamports'],150)

    def test_account_reuse_two_lifetimes(self):
        self.create(100);self.initialize();self.transfer(2,1,20);self.close()
        self.tx['meta']['postBalances'][0]=965;self.tx['meta']['postBalances'][2]=330
        r=self.result();self.assertEqual(r['status'],'LAMPORTS_RECONCILED')
        self.assertEqual(r['reused_accounts'],['temporary'])
        self.assertEqual([x['lamports_returned'] for x in r['lifecycles'] if x['kind']=='close'],[150,120])

    def test_sync_native_is_not_a_second_cash_transfer(self):
        self.tx['transaction']['message']['instructions'].insert(2,{'programIdIndex':4,'accounts':[1],'data':base58(bytes([17]))})
        r=self.result();self.assertEqual(r['status'],'LAMPORTS_RECONCILED')
        self.assertEqual(len(r['movements']),3)
        self.assertEqual(sum(x['kind']=='sync_native' for x in r['lifecycles']),1)

    def test_fee_charged_once_and_one_lamport_error_detected(self):
        self.tx['meta']['postBalances'][0]+=1
        r=self.result();self.assertEqual(r['status'],'UNEXPLAINED_LAMPORT_CHANGES')
        self.assertEqual(r['mismatches'][0]['residual'],1)

    def test_internal_direct_program_change_is_not_balanced_away(self):
        self.tx['meta']['postBalances'][0]-=10;self.tx['meta']['postBalances'][2]+=10
        r=self.result();self.assertEqual(r['status'],'UNEXPLAINED_LAMPORT_CHANGES')
        self.assertEqual(len(r['mismatches']),2)

    def test_close_twice_and_use_after_close_fail(self):
        self.close();self.assertEqual(self.result()['reason'],'CLOSE_WITHOUT_ACCOUNT_IDENTITY')
        self.tx['transaction']['message']['instructions'].pop()
        self.transfer(1,2,1)
        self.assertEqual(self.result()['reason'],'INACTIVE_OR_CONFLICTING_TOKEN_ACCOUNT')

    def test_unknown_extension_and_malformed_system_fail(self):
        self.append(4,[2],bytes([26]));self.assertEqual(self.result()['reason'],'UNSUPPORTED_TOKEN_INSTRUCTION_26')
        self.tx['transaction']['message']['instructions'].pop()
        self.tx['transaction']['message']['instructions'][0]['data']=base58(bytes([0]))
        self.assertEqual(self.result()['reason'],'MALFORMED_SYSTEM_INSTRUCTION')

    def test_negative_indices_and_missing_boundary_fail(self):
        self.tx['transaction']['message']['instructions'][0]['accounts'][0]=-1
        self.assertEqual(self.result()['reason'],'INVALID_ACCOUNT_INDEX')
        self.tx['transaction']['message']['instructions'][0]['accounts'][0]=0
        self.tx['meta']['preBalances'].pop()
        self.assertEqual(self.result()['reason'],'MISSING_LAMPORT_BOUNDARY')

    def test_failed_inner_execution_not_replayed(self):
        self.tx['meta']['logMessages']=['Program abc failed: error']
        self.assertEqual(self.result()['reason'],'INCOMPLETE_OR_FAILED_INNER_EXECUTION')

    def test_insufficient_intermediate_funds_fail(self):
        ix=self.tx['transaction']['message']['instructions'][2]
        ix['data']=base58(bytes([12])+(201).to_bytes(8,'little')+bytes([9]))
        self.assertEqual(self.result()['reason'],'MODELED_INTERMEDIATE_FUNDS_DEFICIT')

    def test_seed_layout_and_truncation(self):
        seed=b'abc';data=(3).to_bytes(4,'little')+bytes(32)+len(seed).to_bytes(8,'little')+seed+(123).to_bytes(8,'little')+(165).to_bytes(8,'little')+bytes(32)
        self.assertEqual(system_movement(data,[0,1]),('create_with_seed',0,1,123))
        with self.assertRaises(ValueError):system_movement(data[:-1],[0,1])
        data=(11).to_bytes(4,'little')+(25).to_bytes(8,'little')+len(seed).to_bytes(8,'little')+seed+bytes(32)
        self.assertEqual(system_movement(data,[0,1,2]),('transfer_with_seed',0,2,25))

    def test_inner_calls_counted_once(self):
        ixs=self.tx['transaction']['message']['instructions'];self.keys.append('router')
        self.tx['meta']['preBalances'].append(1);self.tx['meta']['postBalances'].append(1)
        self.tx['transaction']['message']['instructions']=[{'programIdIndex':7,'accounts':[],'data':''}]
        self.tx['meta']['innerInstructions']=[{'index':0,'instructions':ixs}]
        self.assertEqual(self.result()['status'],'LAMPORTS_RECONCILED')
        self.assertEqual(len(self.result()['movements']),3)

    def test_real_wrapped_sol_reuse_and_one_lamport_tamper(self):
        fixture=json.loads((Path(__file__).parent/'fixtures'/'real_wsol_reuse.json').read_text())
        tx=fixture['transaction']
        r=reconcile_lamports(tx)
        self.assertEqual(r['status'],'LAMPORTS_RECONCILED')
        self.assertEqual(len(r['reused_accounts']),1)
        self.assertEqual([e['lamports_returned'] for e in r['lifecycles'] if e['kind']=='close'],[1488440,13853114874])
        changed=copy.deepcopy(tx);changed['meta']['postBalances'][0]+=1
        self.assertEqual(reconcile_lamports(changed)['status'],'UNEXPLAINED_LAMPORT_CHANGES')
