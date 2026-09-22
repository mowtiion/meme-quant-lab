"""Regression cases found by replaying real data and reviewing the research gates."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from dataclasses import replace

from meme_quant.decoder import AMM, IDLDecoder, decode_block, normalize_block
from meme_quant.domain import IntegrityError
from meme_quant.features import snapshot
from meme_quant.pipeline import load_manifest, run
from test_integrity import event, BASE

ROOT = Path(__file__).resolve().parents[1]


class BoostReconciliation(unittest.TestCase):
    def setUp(self):
        self.decoder = IDLDecoder(ROOT / 'vendor/pump_amm.json')
        self.fixture = json.loads((ROOT / 'tests/fixtures/real_amm_unresolved_449382008.json').read_text())
        self.rows, self.issues = decode_block(self.fixture, self.fixture['slot'],
                                              self.fixture['raw_block_sha256'], {AMM: self.decoder})

    def normalized(self, fixture=None, rows=None):
        return normalize_block(fixture or self.fixture, self.rows if rows is None else rows, self.decoder)

    def test_all_three_real_actions_reconcile_known_amounts(self):
        known = {449382008: (97841686487, 358886388),
                 449382021: (175892295483, 781595681),
                 449382027: (230676585266, 694587958)}
        for slot, amounts in known.items():
            with self.subTest(slot=slot):
                f = json.loads((ROOT / f'tests/fixtures/real_amm_unresolved_{slot}.json').read_text())
                rows, issues = decode_block(f, slot, f['raw_block_sha256'], {AMM: self.decoder})
                events, errors = self.normalized(f, rows)
                self.assertEqual(issues + errors, [])
                self.assertEqual(len(events), 1)
                e = events[0]
                self.assertEqual(e.kind, 'protocol_buy_burn')
                self.assertEqual((e.base_raw, e.quote_raw), amounts)
                self.assertIsNone(e.wallet)
                self.assertIsNone(e.side)

    def test_protocol_action_never_increases_buyers_or_trading_volume(self):
        events, errors = self.normalized()
        self.assertEqual(errors, [])
        e = events[0]
        launch = replace(event('create', 0), mint=e.mint, event_ms=e.event_ms-1000,
                         slot=e.slot-1)
        result = snapshot(launch, [launch, e], 10)
        self.assertEqual(result['unique_buyers'], 0)
        self.assertEqual(result['n_buys'], 0)
        self.assertEqual(result['buy_volume'], '0')
        self.assertIsNone(result['last_trade_price'])

    def test_missing_companion_stays_quarantined(self):
        events, issues = self.normalized(rows=self.rows[:1])
        self.assertEqual(events, [])
        self.assertTrue(issues)

    def test_companion_without_buy_cannot_disappear(self):
        events, issues = self.normalized(rows=self.rows[1:])
        self.assertEqual(events, [])
        self.assertEqual(issues[0]['reason'], 'UNMATCHED_BOOST_COMPANION')

    def test_wrong_companion_amount_rejected(self):
        rows = copy.deepcopy(self.rows)
        rows[1]['payload']['base_amount_burned'] += 1
        events, issues = self.normalized(rows=rows)
        self.assertEqual(events, [])
        self.assertTrue(issues)

    def test_post_balance_mismatch_rejected(self):
        f = copy.deepcopy(self.fixture)
        f['transactions'][0]['meta']['postTokenBalances'][0]['uiTokenAmount']['amount'] = '1'
        events, issues = self.normalized(fixture=f)
        self.assertEqual(events, [])
        self.assertTrue(issues)

    def test_missing_burn_instruction_rejected(self):
        f = copy.deepcopy(self.fixture)
        for group in f['transactions'][0]['meta']['innerInstructions']:
            group['instructions'] = []
        events, issues = self.normalized(fixture=f)
        self.assertEqual(events, [])
        self.assertTrue(issues)

    def test_repeated_buy_is_ambiguous(self):
        rows = copy.deepcopy(self.rows)
        rows.append(copy.deepcopy(rows[0]))
        events, issues = self.normalized(rows=rows)
        self.assertEqual(events, [])
        self.assertTrue(issues)

    def test_mint_mismatch_rejected(self):
        rows = copy.deepcopy(self.rows)
        rows[1]['payload']['mint'] = 'wrong-mint'
        events, issues = self.normalized(rows=rows)
        self.assertEqual(events, [])
        self.assertTrue(issues)

    def test_caught_failed_cpi_does_not_emit_committed_events(self):
        # A successful router may catch a failed AMM invocation after it emitted logs.
        f = copy.deepcopy(self.fixture)
        meta = f['transactions'][0]['meta']
        encoded = next(l for l in meta['logMessages'] if l.startswith('Program data: '))
        meta['logMessages'] = ['Program router invoke [1]', f'Program {AMM} invoke [2]',
                              encoded, f'Program {AMM} failed: custom program error: 1',
                              'Program router success']
        rows, issues = decode_block(f, f['slot'], f['raw_block_sha256'], {AMM: self.decoder})
        self.assertEqual(rows, [])
        self.assertEqual(issues, [])


class ResearchGates(unittest.TestCase):
    def test_small_real_sample_cannot_pass_thousand_launch_gate(self):
        config = json.loads((ROOT / 'configs/exp000.json').read_text())
        config['sample_size'] = 1
        with tempfile.TemporaryDirectory() as d:
            report = run([event('create', 0)], config,
                         {'synthetic': False, 'enumeration_complete': True,
                          'coverage_start_ms': BASE, 'coverage_end_ms': BASE+999999},
                         Path(d)/'out', parquet=False)
        self.assertEqual(report['gates']['real_launch_sample_1000'], 'FAIL')

    def test_parquet_and_duckdb_preserve_large_raw_amounts(self):
        import duckdb
        import pyarrow.parquet as pq
        from meme_quant.storage import export_parquet
        rows = [{'mint': 'mint', 'base_raw': 2**64-1, 'quote_raw': 2**53+1}]
        with tempfile.TemporaryDirectory() as d:
            export_parquet(Path(d), {'events': rows, 'issues': []})
            self.assertFalse((Path(d)/'research.duckdb.wal').exists())
            payload = pq.read_table(Path(d)/'events.parquet').to_pylist()[0]['payload_json']
            self.assertEqual(json.loads(payload), rows[0])
            with duckdb.connect(str(Path(d)/'research.duckdb'), read_only=True) as con:
                self.assertEqual(json.loads(con.execute('select payload_json from events').fetchone()[0]), rows[0])
                self.assertEqual(con.execute('select count(*) from issues').fetchone()[0], 0)

    def test_preflight_blocks_small_real_sample_even_if_report_gates_claim_pass(self):
        from meme_quant.preflight import pilot_readiness
        report = {'synthetic': False, 'dataset_version': 'fixture',
                  'counts': {'sampled_launches': 5}, 'gates': {'sample': 'PASS'}}
        plan = json.loads((ROOT/'configs/pilot1000.json').read_text())
        result = pilot_readiness(report, plan)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertFalse(result['bulk_download_started'])

    def test_non_finalized_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'manifest.json'
            p.write_text(json.dumps({'commitment': 'confirmed', 'blocks': []}))
            with self.assertRaisesRegex(IntegrityError, 'finalized'):
                load_manifest(p, Path(d), ROOT/'vendor')


if __name__ == '__main__':
    unittest.main()
