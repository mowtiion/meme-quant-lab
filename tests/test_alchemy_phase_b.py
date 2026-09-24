"""Check full-run bounds and persistence without any network requests."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import compare_alchemy_phase_b as runner
from compare_second_source import digest, groups
import test_second_source as fixture


class PhaseB(unittest.TestCase):
    def run_fake(self, fail=False):
        sample = fixture.PreexecutionEncoding(); sample.setUp()
        block = sample.primary
        reference = {'slots': {str(s): {'transactions': 1, 'group_sha256': {
            k:digest(v) for k,v in groups(block).items()}} for s in runner.PHASE_B_SLOTS}}
        calls = []
        def rpc(endpoint, method, params, deadline, remaining):
            calls.append(method)
            if fail and len(calls) == 3:
                raise RuntimeError('HTTP 403')
            result = list(runner.PHASE_B_SLOTS) if method == 'getBlocks' else block
            envelope = {'result': result}
            return envelope, json.dumps(envelope).encode()
        old = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp); Path('configs').mkdir()
                Path('configs/second_source_reference41.json').write_text(json.dumps(reference))
                with patch.object(runner, 'call', side_effect=rpc), patch.dict(os.environ, {'ALCHEMY_API_KEY':'test-key'}), contextlib.redirect_stdout(io.StringIO()):
                    code = runner.main()
                out = next(Path('data/secondary').iterdir())
                report = json.loads((out/'comparison.json').read_text())
                parts = list(out.glob('evidence-*.zip'))
                return code, report, calls, len(parts)
            finally:
                os.chdir(old)

    def test_complete_41_blocks_42_calls_six_parts(self):
        code, report, calls, parts = self.run_fake()
        self.assertEqual((code, report['status'], len(calls), len(report['slots']), parts),
                         (0, 'MATCH_FOR_41_BLOCKS', 42, 41, 6))

    def test_error_preserves_completed_block_without_retry(self):
        code, report, calls, parts = self.run_fake(fail=True)
        self.assertEqual((code, report['status'], report['requests'], len(calls), len(report['slots']), parts),
                         (2, 'INCOMPLETE', 3, 3, 1, 1))
        self.assertEqual(report['issue'], 'HTTP 403')
