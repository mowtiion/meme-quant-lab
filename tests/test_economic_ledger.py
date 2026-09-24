import copy
import hashlib
import json
import unittest
from pathlib import Path
from meme_quant.decoder import IDLDecoder, AMM, PUMP, base58, unbase58
from meme_quant.event_scope import EventScope
from meme_quant.fee_audit import audit_amm_fees
from meme_quant.lamport_ledger import reconcile_lamports
from meme_quant.token_extensions import effect_data, TOKEN_2022
from meme_quant.token_ledger import TOKEN

ROOT=Path(__file__).resolve().parents[1]


class EconomicLedger(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases=json.loads((ROOT/'tests/fixtures/economic_cases.json').read_text())['cases']
        cls.decoders={d.program:d for d in (IDLDecoder(ROOT/'vendor/pump.json'),IDLDecoder(ROOT/'vendor/pump_amm.json'))}

    def case(self,index):return copy.deepcopy(next(r for r in self.cases if r['tx_index']==index))
    def sol(self,r):return reconcile_lamports(r['tx'],r['rows'],self.decoders)
    def fees(self,r):return audit_amm_fees(r['tx'],r['rows'],self.decoders[AMM])

    def test_real_pump_sell_funds_later_router_transfer(self):
        r=self.case(837);base=reconcile_lamports(r['tx']);full=self.sol(r)
        self.assertEqual(base['reason'],'MODELED_INTERMEDIATE_FUNDS_DEFICIT')
        self.assertEqual(full['status'],'LAMPORTS_RECONCILED')
        self.assertEqual(next(m['lamports'] for m in full['movements'] if m['kind']=='pump_sell_user'),1062597817)

    def test_missing_event_cannot_be_solved_from_postbalances(self):
        r=self.case(837);r['rows']=[]
        self.assertNotEqual(self.sol(r)['status'],'LAMPORTS_RECONCILED')

    def test_changed_event_payload_and_duplicate_event_rejected(self):
        r=self.case(837);r['rows'][0]['payload']['sol_amount']+=1
        self.assertEqual(self.sol(r)['reason'],'EVENT_LOG_PAYLOAD_DIFFERS')
        r=self.case(837);r['rows'].append(copy.deepcopy(r['rows'][0]))
        self.assertEqual(self.sol(r)['reason'],'DUPLICATE_DIRECT_EVENT')

    def test_real_volume_close_uses_balance_not_rent_constant(self):
        r=self.case(223);out=self.sol(r)
        self.assertEqual(out['status'],'LAMPORTS_RECONCILED')
        self.assertEqual(next(m['lamports'] for m in out['movements'] if m['kind']=='close_volume_account'),1346200)
        r['tx']['meta']['postBalances'][0]+=1
        self.assertEqual(self.sol(r)['status'],'UNEXPLAINED_LAMPORT_CHANGES')

    def test_holder_fee_is_alias_not_second_payment(self):
        fees=self.fees(self.case(223));self.assertEqual(len(fees),1)
        self.assertEqual(fees[0]['status'],'CORE_FEES_RECONCILED')
        self.assertEqual(fees[0]['holder_rewards'],fees[0]['creator_fee'])
        self.assertEqual(fees[0]['holder_rewards'],125728)

    def test_cashback_destination_is_derived_user_accumulator_ata(self):
        fees=self.fees(self.case(163));self.assertEqual(fees[0]['status'],'CORE_FEES_RECONCILED')
        self.assertEqual(fees[0]['cashback'],238080)
        self.assertEqual(fees[0]['creator_fee'],0)

    def test_multi_action_same_pool_has_distinct_instruction_scopes(self):
        out=self.fees(self.case(95));self.assertEqual(len(out),2)
        self.assertTrue(all(r['status']=='CORE_FEES_RECONCILED' for r in out))
        self.assertEqual(len({tuple(r['instruction_path']) for r in out}),2)

    def test_buyback_wrong_recipient_is_not_accepted_by_matching_amount(self):
        r=self.case(223);scope=EventScope(r['tx'])
        e=next(e for e in r['rows'] if e['name']=='BuyEvent')
        node,a,spec=scope.bind(e,self.decoders[AMM],{'buy_exact_quote_in'})
        node['instruction']['accounts'][-1]=node['instruction']['accounts'][0]
        self.assertEqual(self.fees(r)[0]['reason'],'BUYBACK_ATA_DIFFERS')

    def test_unwrap_all_uses_known_token_amount_and_preserves_account(self):
        r=self.case(746);out=self.sol(r)
        self.assertEqual(out['status'],'LAMPORTS_RECONCILED')
        op=next(m for m in out['movements'] if m['kind']=='unwrap_lamports')
        self.assertGreater(op['lamports'],0)
        boundary=next(b for b in out['native_token_boundaries'] if b['account']==op['source'])
        self.assertEqual((boundary['status'],boundary['predicted']),('MATCH',0))
        self.assertEqual(self.fees(r)[0]['status'],'CORE_FEES_RECONCILED')

    def test_native_token_boundary_tamper_detected_independently_of_lamports(self):
        r=self.case(746);r['tx']['meta']['postTokenBalances'][0]['uiTokenAmount']['amount']='1'
        self.assertEqual(self.sol(r)['reason'],'NATIVE_TOKEN_BOUNDARY_DIFFERS')

    def test_sync_native_does_not_invent_stored_reserve(self):
        out=self.sol(self.case(95));self.assertFalse(out['sync_token_amounts_independently_verified'])

    def test_unknown_instruction_inside_fee_scope_blocks_it(self):
        r=self.case(223);scope=EventScope(r['tx'])
        e=next(e for e in r['rows'] if e['name']=='BuyEvent')
        node,_,_=scope.bind(e,self.decoders[AMM],{'buy_exact_quote_in'})
        child=next(n for n in scope.nodes[node['position']+1:scope.end(node)] if n['program'] in (TOKEN,TOKEN_2022))
        child['instruction']['data']=base58(bytes([99]))
        self.assertEqual(self.fees(r)[0]['reason'],'UNSUPPORTED_TOKEN_EXTENSION')

    def test_unwrap_all_without_known_starting_token_amount_fails(self):
        r=self.case(746)
        r['tx']['meta']['preTokenBalances'][0]['uiTokenAmount']['amount']=None
        self.assertEqual(self.sol(r)['reason'],'UNWRAP_AMOUNT_REQUIRES_STORED_RESERVE')

    def test_zero_fee_extension_exact_decoding_and_nonzero_fee_rejection(self):
        data=bytes([26,1])+(123).to_bytes(8,'little')+bytes([8])+bytes(8)
        self.assertEqual(effect_data(TOKEN_2022,data),bytes([12])+(123).to_bytes(8,'little')+bytes([8]))
        self.assertEqual(effect_data(TOKEN,data),data)
        with self.assertRaisesRegex(ValueError,'NONZERO_TRANSFER_FEE'):effect_data(TOKEN_2022,data[:-1]+b'\x01')
        with self.assertRaises(ValueError):effect_data(TOKEN_2022,data[:-1])

    def test_metadata_initialization_binary_lengths_and_program(self):
        tag=hashlib.sha256(b'spl_token_metadata_interface:initialize_account').digest()[:8]
        data=tag+b''.join(len(s).to_bytes(4,'little')+s for s in (b'name',b'SYM',b'uri'))
        self.assertIsNone(effect_data(TOKEN_2022,data,['mint','authority','mint','signer']))
        for bad in (data[:-1],data+b'\0'):
            with self.assertRaises(ValueError):effect_data(TOKEN_2022,bad)
        with self.assertRaises(ValueError):effect_data(TOKEN_2022,data,['mint','authority','other','signer'])
        self.assertIsNone(effect_data(TOKEN_2022,bytes([39,0])+bytes(64),['mint']))
        with self.assertRaises(ValueError):effect_data(TOKEN_2022,bytes([39,0])+bytes(63))
        authority=hashlib.sha256(b'spl_token_metadata_interface:update_the_authority').digest()[:8]+bytes(32)
        self.assertIsNone(effect_data(TOKEN_2022,authority,['mint','authority']))
        with self.assertRaises(ValueError):effect_data(TOKEN_2022,authority[:-1])
