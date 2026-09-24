import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from diagnose_economic_runtime import FLASH, OTHER, diagnose_residual, replay_one
from meme_quant.decoder import IDLDecoder
from meme_quant.economic import DetailsDigest
from compare_second_source import digest


class EconomicRuntime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads((ROOT/'tests/fixtures/unmodeled_router_movements.json').read_text())['cases']
        cls.decoders = {d.program:d for d in (IDLDecoder(ROOT/'vendor/pump.json'),
                                            IDLDecoder(ROOT/'vendor/pump_amm.json'))}

    def test_complete_decoder_and_fee_work_runs_inside_probe(self):
        item = self.cases[0]
        rows, result, timing = replay_one(item, self.decoders)
        self.assertEqual(rows, item['rows'])
        self.assertGreater(len(rows), 0)
        self.assertEqual([f['status'] for f in result['fee_checks']], ['CORE_FEES_RECONCILED'])
        self.assertGreater(timing[2], 0)

    def test_missing_time_cannot_produce_deceptively_fast_empty_benchmark(self):
        item = {**self.cases[0], 'blockTime': None}
        with self.assertRaisesRegex(ValueError, 'NULL_BLOCK_TIME'):
            replay_one(item, self.decoders)

    def test_balanced_router_residuals_remain_unresolved(self):
        for item, program, amount in zip(self.cases, [FLASH, OTHER], [191973, 25500]):
            _, result, _ = replay_one(item, self.decoders)
            row = diagnose_residual(item, result)
            self.assertEqual(row['status'], 'UNEXPLAINED_LAMPORT_CHANGES')
            self.assertEqual(row['associated_programs'], [program])
            self.assertEqual(row['residual_sum'], 0)
            self.assertEqual(row['positive_residual_lamports'], amount)
            self.assertFalse(row['causal_mapping_verified'])

    def test_replenishment_is_not_assumed_equal_to_transaction_fee(self):
        item = self.cases[1]
        _, result, _ = replay_one(item, self.decoders)
        row = diagnose_residual(item, result)
        self.assertEqual(row['payer_residual_lamports'], 25500)
        self.assertEqual(row['transaction_fee_lamports'], 5100)
        self.assertEqual(row['payer_post_lamports'], 100000000)

    def test_diagnosis_does_not_hide_one_lamport_tamper(self):
        item = copy.deepcopy(self.cases[0])
        item['tx']['meta']['postBalances'][0] += 1
        _, result, _ = replay_one(item, self.decoders)
        row = diagnose_residual(item, result)
        self.assertEqual(row['residual_sum'], 1)
        self.assertEqual(row['status'], 'UNEXPLAINED_LAMPORT_CHANGES')

    def test_incremental_digest_matches_canonical_array_and_is_nondestructive(self):
        values = [{'z':3,'a':'é'}, {'native':18446744073709551615,'none':None}]
        accumulator = DetailsDigest()
        self.assertEqual(accumulator.hexdigest(), digest([]))
        accumulator.add(values[0])
        self.assertEqual(accumulator.hexdigest(), digest(values[:1]))
        self.assertEqual(accumulator.hexdigest(), digest(values[:1]))
        accumulator.add(values[1])
        self.assertEqual(accumulator.hexdigest(), digest(values))
