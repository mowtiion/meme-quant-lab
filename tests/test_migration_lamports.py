import copy
import json
import unittest
from pathlib import Path
from meme_quant.decoder import IDLDecoder, PUMP, AMM, base58, unbase58
from meme_quant.direct_lamports import program_movements
from meme_quant.event_scope import EventScope
from meme_quant.lamport_ledger import reconcile_lamports

ROOT=Path(__file__).resolve().parents[1]


class MigrationLamports(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases=json.loads((ROOT/'tests/fixtures/migration_and_extra_sell.json').read_text())['cases']
        cls.decoders={d.program:d for d in (IDLDecoder(ROOT/'vendor/pump.json'),IDLDecoder(ROOT/'vendor/pump_amm.json'))}

    def case(self,index):return copy.deepcopy(next(r for r in self.cases if r['tx_index']==index))
    def result(self,r):return reconcile_lamports(r['tx'],r['rows'],self.decoders)

    def test_real_migration_amounts_fund_account_creation_and_pool(self):
        r=self.case(750);out=self.result(r)
        self.assertEqual(out['status'],'LAMPORTS_RECONCILED')
        amounts={m['kind']:m['lamports'] for m in out['movements'] if m['kind'].startswith('migration_')}
        self.assertEqual(amounts,{'migration_expense_budget':15000001,'migration_quote_funding':84990359056})
        self.assertFalse(out['sync_token_amounts_independently_verified'])

    def test_migration_does_not_fit_post_balance_residual(self):
        r=self.case(750);before=program_movements(r['tx'],r['rows'],self.decoders)
        r['tx']['meta']['postBalances'][0]+=1
        self.assertEqual(before,program_movements(r['tx'],r['rows'],self.decoders))
        self.assertEqual(self.result(r)['status'],'UNEXPLAINED_LAMPORT_CHANGES')

    def test_missing_pool_companion_blocks_funding_model(self):
        r=self.case(750);r['rows']=[e for e in r['rows'] if e['name']!='CreatePoolEvent']
        self.assertEqual(self.result(r)['reason'],'MIGRATION_POOL_EVENT_AMBIGUOUS')

    def test_pool_instruction_amount_must_match_event(self):
        r=self.case(750);scope=EventScope(r['tx']);e=next(e for e in r['rows'] if e['name']=='CreatePoolEvent')
        node,_,_=scope.bind(e,self.decoders[AMM],{'create_pool'});raw=unbase58(node['instruction']['data'])
        node['instruction']['data']=base58(raw[:18]+(e['payload']['quote_amount_in']+1).to_bytes(8,'little')+raw[26:])
        self.assertEqual(self.result(r)['reason'],'MIGRATION_POOL_INSTRUCTION_AMOUNT_DIFFERS')

    def test_extra_sell_account_must_be_derived_curve_v2(self):
        r=self.case(502);self.assertEqual(self.result(r)['status'],'LAMPORTS_RECONCILED')
        scope=EventScope(r['tx']);e=next(e for e in r['rows'] if e['name']=='TradeEvent')
        node,_,_=scope.bind(e,self.decoders[PUMP],{'sell_v2'})
        node['instruction']['accounts'][-1]=node['instruction']['accounts'][0]
        self.assertEqual(self.result(r)['reason'],'UNSUPPORTED_DIRECT_SELL_ACCOUNTS')

    def test_shared_creator_fee_still_goes_to_named_vault(self):
        r=self.case(502);out=self.result(r)
        fee=next(m for m in out['movements'] if m['kind']=='pump_sell_creator_or_reward')
        self.assertEqual(fee['lamports'],2998776)
        self.assertEqual(fee['destination'],'4DXoeoUZY1wmfjJFh1mrHonB25MQwEpaEw5fuAobKTGx')
