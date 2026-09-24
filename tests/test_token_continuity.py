import copy
import unittest
from meme_quant.token_continuity import TokenContinuity
from meme_quant.token_ledger import TOKEN


def tx(before,after,err=None):
    def row(value):
        return [] if value is None else [{'accountIndex':0,'mint':'mint','programId':TOKEN,
            'owner':'holder','uiTokenAmount':{'amount':str(value),'decimals':6}}]
    return {'transaction':{'message':{'accountKeys':['account']}},'meta':{
        'err':err,'preTokenBalances':row(before),'postTokenBalances':row(after),
        'preBalances':[0 if before is None else 100],
        'postBalances':[0 if after is None else 100]}}


class Continuity(unittest.TestCase):
    def test_intervening_non_target_and_failed_transactions_included(self):
        c=TokenContinuity()
        for i,t in enumerate([tx(10,20),tx(20,30),tx(30,30,'failed'),tx(30,40)]):
            c.observe_transaction(1,i,t)
        r=c.result();self.assertEqual(r['status'],'TOKEN_BOUNDARY_CONTINUITY_RECONCILED')
        self.assertEqual(r['counts']['matching_token_links'],3)
        self.assertEqual(r['counts']['failed_transactions_included'],1)

    def test_dropped_intervening_transaction_and_one_unit_change_detected(self):
        c=TokenContinuity();c.observe_transaction(1,0,tx(10,20));c.observe_transaction(1,2,tx(30,40))
        self.assertEqual(c.result()['counts']['discontinuities'],1)
        c=TokenContinuity();c.observe_transaction(1,0,tx(10,20));c.observe_transaction(1,1,tx(21,30))
        self.assertEqual(c.result()['status'],'TOKEN_CONTINUITY_BLOCKED')

    def test_closed_account_recreation_is_separate_boundary(self):
        c=TokenContinuity()
        for i,t in enumerate([tx(10,None),tx(None,5),tx(5,7)]):c.observe_transaction(1,i,t)
        r=c.result();self.assertEqual(r['status'],'TOKEN_BOUNDARY_CONTINUITY_RECONCILED')
        self.assertEqual(r['counts']['closure_boundaries'],1)
        self.assertEqual(r['counts']['creation_boundaries'],1)
        self.assertEqual(r['counts']['matching_absent_links'],1)

    def test_funded_account_without_metadata_is_unknown_not_zero(self):
        c=TokenContinuity();c.observe_transaction(1,0,tx(10,20))
        t=tx(None,None);t['meta']['preBalances']=[100];t['meta']['postBalances']=[100]
        c.observe_transaction(1,1,t)
        self.assertEqual(c.result()['status'],'TOKEN_CONTINUITY_BLOCKED')
        self.assertEqual(c.result()['counts']['unprovable_links'],1)

    def test_identity_change_between_transactions_fails(self):
        c=TokenContinuity();c.observe_transaction(1,0,tx(10,20));t=tx(20,30)
        t['meta']['preTokenBalances'][0]['owner']='other'
        c.observe_transaction(1,1,t);self.assertEqual(c.result()['counts']['discontinuities'],1)

    def test_failed_transaction_cannot_change_token_state(self):
        c=TokenContinuity();c.observe_transaction(1,0,tx(10,20,'failure'))
        self.assertEqual(c.result()['counts']['failed_transaction_changes'],1)

    def test_invalid_duplicate_and_missing_metadata_fail(self):
        t=tx(10,20);t['meta']['preTokenBalances']*=2
        with self.assertRaises(ValueError):TokenContinuity().observe_transaction(1,0,t)
        t=tx(10,20);del t['meta']['preTokenBalances']
        with self.assertRaises(ValueError):TokenContinuity().observe_transaction(1,0,t)
        t=tx(10,20);t['meta']['preTokenBalances'][0]['uiTokenAmount']['amount']='1.0'
        with self.assertRaises(ValueError):TokenContinuity().observe_transaction(1,0,t)

    def test_block_chain_and_cross_slot_links(self):
        first={'blockhash':'a','previousBlockhash':'z','parentSlot':0,'transactions':[tx(10,20)]}
        second={'blockhash':'b','previousBlockhash':'a','parentSlot':1,'transactions':[tx(20,30)]}
        c=TokenContinuity();c.observe_block(1,first);c.observe_block(2,second)
        self.assertEqual(c.result()['counts']['cross_slot_matching_links'],1)
        for key,value in [('parentSlot',0),('previousBlockhash','wrong')]:
            c=TokenContinuity();c.observe_block(1,first);bad=copy.deepcopy(second);bad[key]=value
            with self.assertRaises(ValueError):c.observe_block(2,bad)
