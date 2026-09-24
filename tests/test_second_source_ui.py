"""UI rounding must not hide changed exact balances or other chain data."""
import copy
import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from compare_second_source import canonical_token_ui, compare, digest, groups, normalize_preexecution_empty
from test_second_source import PreexecutionEncoding


class TokenUI(unittest.TestCase):
    def setUp(self):
        fixture = PreexecutionEncoding()
        fixture.setUp()
        self.block = fixture.primary
        token = {'accountIndex': 1, 'mint': 'mint', 'owner': 'owner', 'uiTokenAmount': {
            'amount': '12645191192770476', 'decimals': 6,
            'uiAmountString': '12645191192.770476', 'uiAmount': 12645191192.770477}}
        self.block['transactions'][0]['meta']['postTokenBalances'] = [token]
        canonical, _ = canonical_token_ui(normalize_preexecution_empty(self.block)[0])
        self.reference = {'transactions': 1,
                          'group_sha256': {k:digest(v) for k,v in groups(self.block).items()},
                          'canonical_group_sha256': {k:digest(v) for k,v in groups(canonical).items()}}
        self.other = copy.deepcopy(self.block)
        self.ui = self.other['transactions'][0]['meta']['postTokenBalances'][0]['uiTokenAmount']
        self.ui['uiAmount'] = 12645191192.770475

    def test_one_ulp_preserves_original_and_reports_nonexact(self):
        before = copy.deepcopy(self.other)
        result = compare(self.other, self.reference)
        self.assertEqual(result['status'], 'MATCH')
        self.assertEqual(result['comparison_mode'], 'CANONICAL_TOKEN_UI_V1')
        self.assertFalse(result['exact_groups']['balances'])
        self.assertEqual(self.other, before)

    def test_wrong_ui_amount_is_rejected(self):
        self.ui['uiAmount'] += 0.01
        self.assertEqual(compare(self.other, self.reference)['status'], 'MISMATCH')

    def test_each_exact_field_and_logs_still_must_match(self):
        for field, value in [('amount', '12645191192770477'), ('decimals', 5),
                             ('uiAmountString', '12645191192.770477')]:
            with self.subTest(field=field):
                block = copy.deepcopy(self.other)
                block['transactions'][0]['meta']['postTokenBalances'][0]['uiTokenAmount'][field] = value
                self.assertEqual(compare(block, self.reference)['status'], 'MISMATCH')
        self.other['transactions'][0]['meta']['logMessages'] = ['Log truncated']
        self.assertEqual(compare(self.other, self.reference)['status'], 'MISMATCH')

    def test_consistently_changed_exact_balance_is_rejected(self):
        self.ui.update(amount='12645191192770477', uiAmountString='12645191192.770477',
                       uiAmount=12645191192.770477)
        self.assertEqual(compare(self.other, self.reference)['status'], 'MISMATCH')

    def test_null_missing_and_nan_do_not_pass(self):
        for value in (None, math.nan, math.inf, True):
            with self.subTest(value=value):
                self.ui['uiAmount'] = value
                self.assertNotEqual(compare(self.other, self.reference)['status'], 'MATCH')
        del self.ui['uiAmount']
        self.assertNotEqual(compare(self.other, self.reference)['status'], 'MATCH')

    def test_both_encoding_rules_can_apply_together(self):
        self.other['transactions'][0]['meta'].update(innerInstructions=[], logMessages=[])
        result = compare(self.other, self.reference)
        self.assertEqual(result['status'], 'MATCH')
        self.assertTrue(result['normalized_preexecution_fields'])


if __name__ == '__main__':
    unittest.main()
