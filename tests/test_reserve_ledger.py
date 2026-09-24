import copy
import unittest
from types import SimpleNamespace
from meme_quant.decoder import AMM, ZERO, base58
from meme_quant.reserve_ledger import reconcile_pool_transaction


class ReserveLedger(unittest.TestCase):
    def setUp(self):
        names = ['pool', 'user', 'user_base_token_account', 'user_quote_token_account',
                 'pool_base_token_account', 'pool_quote_token_account', 'base_mint', 'quote_mint']
        self.decoder = SimpleNamespace(instructions={b'12345678': {
            'name': 'buy', 'accounts': [{'name': n} for n in names]}})
        self.tx = {'transaction': {'signatures': ['sig'], 'message': {
            'accountKeys': names + [AMM], 'instructions': [{'programIdIndex':8, 'accounts':list(range(8)),
                                                         'data':base58(b'12345678')}] }},
            'meta': {'err':None, 'logMessages':['Program test success'], 'innerInstructions':[],
                     'preTokenBalances':[], 'postTokenBalances':[]}}
        for field, amounts in [('preTokenBalances',(1000,2000)), ('postTokenBalances',(900,2110))]:
            self.tx['meta'][field] = [{'accountIndex':index, 'mint':names[index+2],
                                      'uiTokenAmount':{'amount':str(amount),'decimals':6}}
                                     for index, amount in zip((4,5), amounts)]
        self.row = {'program':AMM, 'name':'BuyEvent', 'event_index':1,
                    'payload':{**{n:n for n in names[:4]}, 'pool_base_token_reserves':1000,
                               'pool_quote_token_reserves':2000, 'base_amount_out':100,
                               'quote_amount_in_with_lp_fee':110}}

    def check(self, rows=None):
        return reconcile_pool_transaction(self.tx, rows or [self.row], self.decoder)[0]

    def test_integer_vault_flow(self):
        result=self.check()
        self.assertEqual(result['status'],'RECONCILED')
        self.assertEqual((result['predicted_post_base'],result['predicted_post_quote']),(900,2110))

    def test_changed_post_balance_is_not_accepted(self):
        self.tx['meta']['postTokenBalances'][0]['uiTokenAmount']['amount']='901'
        self.assertEqual(self.check()['reason'],'POST_RESERVES_DIFFER')

    def test_multi_action_replay(self):
        second=copy.deepcopy(self.row); second['event_index']=2
        second['payload'].update(pool_base_token_reserves=900,pool_quote_token_reserves=2110)
        self.tx['transaction']['message']['instructions'] *= 2
        self.tx['meta']['postTokenBalances'][0]['uiTokenAmount']['amount']='800'
        self.tx['meta']['postTokenBalances'][1]['uiTokenAmount']['amount']='2220'
        self.assertEqual(self.check([self.row,second])['status'],'RECONCILED')
        second['payload']['pool_base_token_reserves']=899
        self.assertEqual(self.check([self.row,second])['reason'],'EVENT_PRE_RESERVES_DIFFER')

    def test_duplicate_event_cannot_create_extra_flow(self):
        self.assertEqual(self.check([self.row,self.row])['reason'],'INSTRUCTION_EVENT_COUNT_DIFFERS')

    def test_missing_balance_not_assumed_zero(self):
        self.tx['meta']['preTokenBalances']=[]
        self.assertEqual(self.check()['reason'],'MISSING_OR_CONFLICTING_VAULT_BALANCE')

    def test_null_logs_failed_execution_and_burn_are_unresolved(self):
        for logs in (None,['Log truncated'],['Program test failed: error']):
            self.tx['meta']['logMessages']=logs
            self.assertEqual(self.check()['status'],'UNRESOLVED')
        self.tx['meta']['logMessages']=[]
        self.row['payload']['user_base_token_account']=ZERO
        self.assertEqual(self.check()['reason'],'PROTOCOL_BURN_SEPARATE_LEDGER')

    def test_different_mint_and_decimals_fail(self):
        self.tx['meta']['postTokenBalances'][0]['mint']='other'
        self.assertEqual(self.check()['reason'],'MISSING_OR_CONFLICTING_VAULT_BALANCE')
        self.tx['meta']['postTokenBalances'][0]['mint']='base_mint'
        self.tx['meta']['postTokenBalances'][0]['uiTokenAmount']['decimals']=9
        self.assertEqual(self.check()['reason'],'DECIMALS_CHANGED')

    def test_amounts_above_float_exact_range_stay_exact(self):
        large=2**60
        self.row['payload']['pool_base_token_reserves']=large
        self.tx['meta']['preTokenBalances'][0]['uiTokenAmount']['amount']=str(large)
        self.tx['meta']['postTokenBalances'][0]['uiTokenAmount']['amount']=str(large-100)
        self.assertEqual(self.check()['status'],'RECONCILED')
        self.tx['meta']['postTokenBalances'][0]['uiTokenAmount']['amount']=str(large-99)
        self.assertEqual(self.check()['reason'],'POST_RESERVES_DIFFER')
