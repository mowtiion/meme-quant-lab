"""Offline checks of the two-request archive probe and its stop condition."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import probe_alchemy_archives as probe
from compare_second_source import digest, groups


class ArchiveProbe(unittest.TestCase):
    def setUp(self):
        self.blocks = {}
        for slot in probe.SLOTS:
            self.blocks[slot] = {
                'blockHeight': slot, 'blockTime': 1, 'blockhash': 'hash',
                'parentSlot': slot-1, 'previousBlockhash': 'previous',
                'transactions': [{'transaction': {'signatures': [f'sig-{slot}'], 'message': {}},
                                  'version': 'legacy',
                                  'meta': {'err': None, 'fee': 5000, 'status': {'Ok': None},
                                           'computeUnitsConsumed': 1, 'costUnits': 1,
                                           'innerInstructions': [], 'logMessages': ['log 1', 'log 2'],
                                           'loadedAddresses': {}, 'preBalances': [], 'postBalances': [],
                                           'preTokenBalances': [], 'postTokenBalances': []}}]}

    def run_probe(self, mutate=None):
        calls = []

        def fake_call(endpoint, method, params, deadline, remaining_bytes):
            slot = params[0]
            calls.append(slot)
            envelope = json.loads(json.dumps({'jsonrpc': '2.0', 'result': self.blocks[slot]}))
            if mutate and slot == probe.SLOTS[0]:
                mutate(envelope['result'])
            return envelope, json.dumps(envelope).encode()

        with tempfile.TemporaryDirectory() as tmp:
            old = Path.cwd()
            try:
                os.chdir(tmp)
                ref = {'slots': {str(slot): {'transactions': 1, 'group_sha256': {
                    name: digest(value) for name, value in groups(block).items()}}
                    for slot, block in self.blocks.items()}}
                Path('reference.json').write_text(json.dumps(ref))
                with (patch.object(probe, 'REFERENCE', Path('reference.json')),
                      patch.object(probe, 'LONG_LOG_SIGNATURES',
                                   {slot: f'sig-{slot}' for slot in probe.SLOTS}),
                      patch.object(probe, 'call', side_effect=fake_call),
                      patch.dict(os.environ, {'ALCHEMY_API_KEY': 'test-key'}),
                      contextlib.redirect_stdout(io.StringIO())):
                    exit_code = probe.main()
                out = next(Path('data/secondary').glob('alchemy-probe-*'))
                report = json.loads((out / 'comparison.json').read_text())
                with zipfile.ZipFile(out / 'evidence.zip') as z:
                    self.assertIsNone(z.testzip())
                    self.assertEqual(json.loads(z.read('comparison.json')), report)
            finally:
                os.chdir(old)
        return exit_code, calls, report

    def test_full_blocks_pass_and_use_two_calls(self):
        code, calls, report = self.run_probe()
        self.assertEqual((code, calls, report['status']),
                         (0, list(probe.SLOTS), 'MATCH_FOR_TWO_BLOCKS'))

    def test_truncated_long_log_stops_after_one_call(self):
        def truncate(block):
            block['transactions'][0]['meta']['logMessages'] = ['log 1', 'Log truncated']

        code, calls, report = self.run_probe(truncate)
        self.assertEqual((code, calls, report['status']), (2, [probe.SLOTS[0]], 'MISMATCH'))
        self.assertTrue(report['slots'][str(probe.SLOTS[0])]['long_log_truncated'])


if __name__ == '__main__':
    unittest.main()
