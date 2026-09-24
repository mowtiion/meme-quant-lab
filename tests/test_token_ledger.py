import copy
import unittest
from meme_quant.decoder import base58
from meme_quant.token_ledger import TOKEN, TOKEN_2022, NATIVE, reconcile_token_accounts


class TokenLedger(unittest.TestCase):
    def setUp(self):
        self.keys=['source','destination','mint','authority',TOKEN]
        self.tx={'transaction':{'signatures':['sig'],'message':{'accountKeys':self.keys,'instructions':[]}},
                 'meta':{'err':None,'logMessages':[],'innerInstructions':[],
                         'preTokenBalances':[], 'postTokenBalances':[]}}
        self.balance('preTokenBalances',0,1000);self.balance('preTokenBalances',1,0)
        self.balance('postTokenBalances',0,900);self.balance('postTokenBalances',1,100)
        self.add(12,[0,2,1,3],100,6)

    def balance(self,field,index,amount,mint='mint',program=TOKEN):
        self.tx['meta'][field].append({'accountIndex':index,'mint':mint,'programId':program,
            'uiTokenAmount':{'amount':str(amount),'decimals':6}})

    def add(self,tag,accounts,amount=None,decimals=None):
        data=bytes([tag])+(amount.to_bytes(8,'little') if amount is not None else b'')
        if decimals is not None:data+=bytes([decimals])
        self.tx['transaction']['message']['instructions'].append({'programIdIndex':4,'accounts':accounts,'data':base58(data)})

    def result(self):return reconcile_token_accounts(self.tx)

    def test_checked_transfer_accounts_reconcile(self):
        self.assertEqual(self.result()['status'],'RECONCILED')
        self.assertEqual(self.result()['flows'][0]['amount'],100)

    def test_exact_one_unit_difference_fails(self):
        self.tx['meta']['postTokenBalances'][1]['uiTokenAmount']['amount']='99'
        self.assertEqual(self.result()['status'],'PARTIAL')
        self.assertIn('TOKEN_DELTA_DIFFERS',{a.get('reason') for a in self.result()['accounts']})

    def test_checked_decimal_and_program_conflicts_fail(self):
        self.tx['meta']['postTokenBalances'][0]['uiTokenAmount']['decimals']=9
        self.assertEqual(self.result()['reason'],'MINT_DECIMALS_CONFLICT')
        self.tx['meta']['postTokenBalances'][0]['uiTokenAmount']['decimals']=6
        self.tx['meta']['postTokenBalances'][0]['programId']=TOKEN_2022
        self.assertEqual(self.result()['reason'],'ACCOUNT_IDENTITY_CHANGED')

    def test_mint_and_burn_net_not_transfer(self):
        self.tx['transaction']['message']['instructions']=[]
        self.tx['meta']['postTokenBalances'][0]['uiTokenAmount']['amount']='990'
        self.tx['meta']['postTokenBalances'][1]['uiTokenAmount']['amount']='20'
        self.add(8,[0,2,3],10);self.add(14,[2,1,3],20,6)
        r=self.result();self.assertEqual(r['status'],'RECONCILED')
        self.assertEqual([f['kind'] for f in r['flows']],['burn','mint'])

    def test_new_nonnative_account_needs_initialization(self):
        self.tx['meta']['preTokenBalances'].pop()
        self.assertEqual(self.result()['status'],'PARTIAL')
        init={'programIdIndex':4,'accounts':[1,2,3],'data':base58(bytes([1]))}
        self.tx['transaction']['message']['instructions'].insert(0,init)
        self.assertEqual(self.result()['status'],'RECONCILED')

    def test_nonnative_closed_account_can_have_zero_post(self):
        self.tx['meta']['preTokenBalances'][0]['uiTokenAmount']['amount']='100'
        self.tx['meta']['postTokenBalances'].pop(0)
        self.add(9,[0,1,3])
        self.assertEqual(self.result()['status'],'RECONCILED')

    def test_sync_native_does_not_fake_conservation(self):
        self.keys[2]=NATIVE
        for field in ('preTokenBalances','postTokenBalances'):
            for row in self.tx['meta'][field]:row['mint']=NATIVE
        self.add(17,[0])
        self.assertEqual(self.result()['status'],'PARTIAL')
        self.assertIn('WSOL_LIFECYCLE_REQUIRES_LAMPORT_LEDGER',{a.get('reason') for a in self.result()['accounts']})

    def test_unknown_extension_blocks_even_balanced_accounts(self):
        self.add(26,[0,1,2])
        self.assertEqual(self.result()['status'],'PARTIAL')
        self.assertTrue(self.result()['unknown'])
        self.assertTrue(all(a['status']=='UNRESOLVED' for a in self.result()['accounts']))

    def test_caught_inner_failure_is_not_counted(self):
        self.tx['meta']['logMessages']=['Program abc failed: custom error']
        self.assertEqual(self.result()['reason'],'INCOMPLETE_OR_FAILED_INNER_EXECUTION')
        self.assertEqual(self.result()['flows'],[])

    def test_duplicate_balance_and_inner_group_rejected(self):
        self.tx['meta']['preTokenBalances'].append(copy.deepcopy(self.tx['meta']['preTokenBalances'][0]))
        self.assertEqual(self.result()['reason'],'DUPLICATE_BALANCE')
        self.tx['meta']['preTokenBalances'].pop()
        self.tx['meta']['innerInstructions']=[{'index':0,'instructions':[]},{'index':0,'instructions':[]}]
        self.assertEqual(self.result()['reason'],'DUPLICATE_INNER_GROUP')

    def test_inner_transfer_counted_exactly_once(self):
        transfer=self.tx['transaction']['message']['instructions'].pop()
        self.keys.append('router')
        self.tx['transaction']['message']['instructions']=[{'programIdIndex':5,'accounts':[],'data':''}]
        self.tx['meta']['innerInstructions']=[{'index':0,'instructions':[transfer]}]
        self.assertEqual(self.result()['status'],'RECONCILED')
        self.assertEqual(len(self.result()['flows']),1)

    def test_malformed_binary_amount_rejected(self):
        self.tx['transaction']['message']['instructions'][0]['data']=base58(bytes([12,1]))
        self.assertEqual(self.result()['reason'],'MALFORMED_TOKEN_FLOW')
