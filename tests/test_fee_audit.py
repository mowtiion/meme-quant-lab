import copy
import json
import unittest
from pathlib import Path
from meme_quant.decoder import AMM, IDLDecoder, decode_block, unbase58, base58
from meme_quant.fee_audit import audit_amm_fees
from meme_quant.token_ledger import TOKEN, TOKEN_2022
from meme_quant.reserve_ledger import account_keys

ROOT=Path(__file__).resolve().parents[1]


class FeeAudit(unittest.TestCase):
    def setUp(self):
        self.fixture=json.loads((ROOT/'tests/fixtures/real_amm_fee_split.json').read_text())
        self.block=self.fixture['block']; self.tx=self.block['transactions'][0]
        self.decoder=IDLDecoder(ROOT/'vendor/pump_amm.json')
        self.rows,self.issues=decode_block(self.block,self.fixture['source_slot'],self.fixture['source_raw_sha256'],{AMM:self.decoder})
        self.assertEqual(self.issues,[])

    def result(self):return audit_amm_fees(self.tx,self.rows,self.decoder)[0]

    def transfer(self,amount):
        keys=account_keys(self.tx)
        for group in self.tx['meta']['innerInstructions']:
            for ix in group['instructions']:
                if keys[ix['programIdIndex']] in (TOKEN,TOKEN_2022):
                    data=unbase58(ix['data'])
                    if data[0] in (3,12) and int.from_bytes(data[1:9],'little')==amount:
                        return ix
        self.fail('Fixture transfer missing')

    def test_real_split_protocol_creator_and_buyback(self):
        r=self.result()
        self.assertEqual(r['status'],'CORE_FEES_RECONCILED')
        self.assertEqual((r['protocol_net'],r['creator_fee'],r['buyback_amount']),(26,804,25))
        self.assertFalse(r['buyback_recipient_identity_verified'])

    def test_one_unit_fee_change_fails(self):
        ix=self.transfer(804); raw=unbase58(ix['data'])
        ix['data']=base58(raw[:1]+(803).to_bytes(8,'little')+raw[9:])
        self.assertEqual(self.result()['reason'],'CORE_TRANSFER_DIFFERS')

    def test_fee_to_other_recipient_fails(self):
        ix=self.transfer(804)
        dest=2 if unbase58(ix['data'])[0]==12 else 1
        ix['accounts'][dest]=ix['accounts'][0]
        self.assertEqual(self.result()['reason'],'CORE_TRANSFER_DIFFERS')

    def test_sibling_transfer_cannot_satisfy_child_fee(self):
        ix=self.transfer(804); ix['stackHeight']=1
        self.assertNotEqual(self.result()['status'],'CORE_FEES_RECONCILED')

    def test_missing_depth_does_not_guess_attribution(self):
        del self.transfer(804)['stackHeight']
        self.assertEqual(self.result()['reason'],'MISSING_CPI_DEPTH')

    def test_buyback_residual_amount_checked(self):
        ix=self.transfer(25);raw=unbase58(ix['data'])
        ix['data']=base58(raw[:1]+(24).to_bytes(8,'little')+raw[9:])
        self.assertEqual(self.result()['reason'],'BUYBACK_AMOUNT_DIFFERS')

    def test_multi_event_and_new_fee_variant_remain_explicit(self):
        self.rows.append(copy.deepcopy(next(r for r in self.rows if r['name']=='SellEvent')))
        self.assertEqual(self.result()['reason'],'MULTI_EVENT_FEE_ATTRIBUTION')
        self.rows.pop()
        next(r for r in self.rows if r['name']=='SellEvent')['payload']['holder_rewards']=10
        self.assertEqual(self.result()['reason'],'FEE_VARIANT_REQUIRES_SEPARATE_MAPPING')
