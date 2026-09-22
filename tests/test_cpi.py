"""Recovery invariants using immutable real transaction excerpts and adversarial edits."""
import copy
import json
import unittest
from pathlib import Path

from meme_quant.cpi import committed, instruction_trace, recover_transaction
from meme_quant.decoder import AMM, IDLDecoder, base58, unbase58, decode_block, normalize_block
from meme_quant.domain import IntegrityError

ROOT = Path(__file__).resolve().parents[1]


class CPIRecovery(unittest.TestCase):
    def setUp(self):
        self.decoder = IDLDecoder(ROOT/'vendor/pump_amm.json')
        self.a = self.fixture(447000000)
        self.b = self.fixture(447000002)

    def fixture(self, slot):
        return json.loads((ROOT/f'tests/fixtures/truncated_amm_{slot}.json').read_text())

    def decode(self, f):
        return decode_block(f, f['slot'], f['raw_block_sha256'], {AMM:self.decoder})

    def ix(self, f, outer, inner):
        return next(g for g in f['transactions'][0]['meta']['innerInstructions'] if g['index']==outer)['instructions'][inner]

    def assert_rejected(self, f):
        _, issues = self.decode(f)
        self.assertIn('CPI_RECOVERY_REJECTED', [i['reason'] for i in issues])
        self.assertIn('TRUNCATED_LOGS', [i['reason'] for i in issues])

    def test_existing_copies_are_deduplicated_in_execution_order(self):
        rows, issues = self.decode(self.a)
        self.assertEqual(issues, [])
        self.assertEqual([r['instruction_path'] for r in rows], [[3,23],[4,7]])
        self.assertEqual([r['source_log_index'] for r in rows], [83,120])
        self.assertEqual([r['event_index'] for r in rows], [27,36])
        self.assertFalse(any(r['recovered_missing_log'] for r in rows))
        self.assertEqual([r['payload']['base_amount_out'] for r in rows], [10598482426,1024552048286])

    def test_missing_buy_restored_and_unproven_admin_quarantined(self):
        rows, issues = self.decode(self.b)
        self.assertEqual(len(rows),1)
        row = rows[0]
        self.assertEqual((row['name'],row['instruction_path']), ('BuyEvent',[8,14]))
        self.assertEqual(row['parent_instruction_path'],[8,7])
        self.assertIsNone(row['source_log_index'])
        self.assertTrue(row['recovered_missing_log'])
        self.assertEqual((row['payload']['base_amount_out'],row['payload']['quote_amount_in']), (947612248707,905904))
        self.assertEqual([(i['reason'],i['event_name'],i['instruction_path']) for i in issues],
                         [('CPI_EXECUTION_UNPROVEN','CloseUserVolumeAccumulatorEvent',[8,16])])
        events, errors = normalize_block(self.b, rows, self.decoder)
        self.assertEqual(errors,[])
        self.assertEqual(len(events),1)
        self.assertEqual(events[0].extra['recovery']['instruction_path'],[8,14])
        self.assertEqual(events[0].raw_sha256,self.b['raw_block_sha256'])

    def test_removed_known_logs_restore_exact_payloads_without_duplication(self):
        expected, _ = self.decode(self.a)
        for removed in ([83],[120],[83,120]):
            with self.subTest(removed=removed):
                f = copy.deepcopy(self.a)
                for index in removed:
                    f['transactions'][0]['meta']['logMessages'][index] = 'Log truncated'
                rows, issues = self.decode(f)
                self.assertEqual(issues,[])
                self.assertEqual([r['payload'] for r in rows],[r['payload'] for r in expected])
                self.assertEqual([r['event_index'] for r in rows],[27,36])
                self.assertEqual(sum(r['recovered_missing_log'] for r in rows),len(removed))

    def test_payload_contradiction_rejects_recovery(self):
        ix = self.ix(self.a,3,23)
        raw = bytearray(unbase58(ix['data']))
        raw[24] ^= 1
        ix['data'] = base58(raw)
        self.assert_rejected(self.a)

    def test_wrong_event_authority_rejects(self):
        self.ix(self.a,3,23)['accounts'] = [0]
        self.assert_rejected(self.a)

    def test_wrong_program_rejects_log_alignment(self):
        self.ix(self.a,3,23)['programIdIndex'] = 0
        self.assert_rejected(self.a)

    def test_wrong_tag_does_not_create_event(self):
        ix = self.ix(self.b,8,14)
        ix['data'] = base58(b'BAD_TAG!'+unbase58(ix['data'])[8:])
        rows, issues = self.decode(self.b)
        self.assertEqual(rows,[])
        self.assertIn('CPI_MISSING_EXPECTED_EVENT',[i['reason'] for i in issues])

    def test_unknown_event_discriminator_rejects(self):
        ix = self.ix(self.b,8,14)
        raw = unbase58(ix['data'])
        ix['data'] = base58(raw[:8]+b'UNKNOWN!'+raw[16:])
        self.assert_rejected(self.b)

    def test_missing_stack_height_rejects(self):
        self.ix(self.a,3,23).pop('stackHeight')
        self.assert_rejected(self.a)

    def test_invalid_stack_height_rejects(self):
        self.ix(self.a,3,23)['stackHeight'] = 12
        self.assert_rejected(self.a)

    def test_negative_account_index_rejects(self):
        self.ix(self.a,3,23)['accounts'] = [-1]
        self.assert_rejected(self.a)

    def test_missing_inner_metadata_rejects(self):
        self.a['transactions'][0]['meta'].pop('innerInstructions')
        self.assert_rejected(self.a)

    def test_duplicate_group_rejects(self):
        groups = self.a['transactions'][0]['meta']['innerInstructions']
        groups.append(copy.deepcopy(groups[-1]))
        self.assert_rejected(self.a)

    def test_duplicate_cpi_never_adds_duplicate_trade(self):
        groups = self.a['transactions'][0]['meta']['innerInstructions']
        groups[0]['instructions'].append(copy.deepcopy(self.ix(self.a,3,23)))
        self.assert_rejected(self.a)
        rows, _ = self.decode(self.a)
        self.assertEqual(len(rows),2)

    def test_missing_success_never_inferred_from_transaction_success(self):
        self.b['transactions'][0]['meta']['logMessages'] = self.b['transactions'][0]['meta']['logMessages'][:135]
        rows, issues = self.decode(self.b)
        self.assertEqual(rows,[])
        self.assertEqual([i['event_name'] for i in issues],['BuyEvent','CloseUserVolumeAccumulatorEvent'])
        self.assertTrue(all(i['reason']=='CPI_EXECUTION_UNPROVEN' for i in issues))

    def test_caught_failed_parent_rolls_back_successful_event_cpi(self):
        logs = self.b['transactions'][0]['meta']['logMessages']
        logs[137] = f'Program {AMM} failed: custom program error: 0x1'
        rows, issues = self.decode(self.b)
        self.assertEqual(rows,[])
        self.assertEqual([i['event_name'] for i in issues],['CloseUserVolumeAccumulatorEvent'])

    def test_unknown_intermediate_ancestor_blocks_promotion(self):
        nodes = [{'parent':None,'status':'success'}, {'parent':0,'status':None},
                 {'parent':1,'status':'success'}]
        self.assertIsNone(committed(nodes,2))
        nodes[1]['status']='failed'
        self.assertIs(committed(nodes,2),False)
        nodes[1]['status']='success'
        self.assertIs(committed(nodes,2),True)

    def test_non_self_event_cpi_rejected(self):
        # Preserve exact metadata/log alignment while changing the event caller.
        f = self.b
        parent = self.ix(f,8,7)
        parent['programIdIndex'] = 0
        tx = f['transactions'][0]
        keys = tx['transaction']['message']['accountKeys']
        nodes = instruction_trace(tx)
        target = next(n for n in nodes if (n['outer_index'],n['inner_index'])==(8,7))
        logs = tx['meta']['logMessages']
        invokes = [i for i,l in enumerate(logs) if ' invoke [' in l]
        logs[invokes[target['position']]] = f"Program {keys[0]} invoke [2]"
        logs[137] = f"Program {keys[0]} success"
        with self.assertRaisesRegex(IntegrityError,'not a self invocation'):
            recover_transaction(tx,[],f['slot'],0,f['blockTime']*1000,f['raw_block_sha256'],{AMM:self.decoder},[])

    def test_failed_transaction_not_recovered(self):
        self.b['transactions'][0]['meta']['err'] = {'InstructionError':[8,'Custom']}
        rows, _ = self.decode(self.b)
        self.assertEqual(rows,[])

    def test_untruncated_trade_remains_on_log_decoder(self):
        f = json.loads((ROOT/'tests/fixtures/real_amm_trade.json').read_text())
        rows, issues = self.decode(f)
        self.assertEqual(issues,[])
        self.assertTrue(rows)
        self.assertTrue(all('event_source' not in r for r in rows))

    def test_complete_transactions_match_cpi_stream_including_protocol_actions(self):
        paths = [ROOT/'tests/fixtures/real_amm_trade.json',
                 *sorted((ROOT/'tests/fixtures').glob('real_amm_unresolved*.json'))]
        for path in paths:
            with self.subTest(fixture=path.name):
                f = json.loads(path.read_text())
                original, issues = self.decode(f)
                self.assertEqual(issues, [])
                # Exercise fallback against a fully known answer, then remove
                # every known event log while retaining execution evidence.
                for remove in (False, True):
                    changed = copy.deepcopy(f)
                    logs = changed['transactions'][0]['meta']['logMessages']
                    logs.append('Log truncated')
                    if remove:
                        for row in original:
                            logs[row['event_index']] = 'Log truncated'
                    recovered, issues = self.decode(changed)
                    self.assertEqual(issues, [])
                    self.assertEqual([(r['name'],r['payload']) for r in recovered],
                                     [(r['name'],r['payload']) for r in original])
                    old_events, errors = normalize_block(f, original, self.decoder)
                    new_events, new_errors = normalize_block(changed, recovered, self.decoder)
                    self.assertEqual(errors+new_errors, [])
                    economics = lambda events: [(e.kind,e.mint,e.wallet,e.side,e.base_raw,e.quote_raw) for e in events]
                    self.assertEqual(economics(old_events), economics(new_events))


if __name__ == '__main__':
    unittest.main()
