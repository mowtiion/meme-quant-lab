"""Targeted comparison checks without RPC access or third-party packages."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from compare_second_source import compare, digest, groups


class PreexecutionEncoding(unittest.TestCase):
    def setUp(self):
        self.primary = {'blockHeight': 1, 'blockTime': 1, 'blockhash': 'a',
                        'parentSlot': 0, 'previousBlockhash': 'b',
                        'transactions': [{
                            'transaction': {'signatures': ['sig'], 'message': {}},
                            'version': 'legacy',
                            'meta': {'err': 'MaxLoadedAccountsDataSizeExceeded', 'fee': 5000,
                                     'status': {'Err': 'MaxLoadedAccountsDataSizeExceeded'},
                                     'computeUnitsConsumed': 0, 'costUnits': 0,
                                     'innerInstructions': None, 'logMessages': None,
                                     'loadedAddresses': {}, 'preBalances': [], 'postBalances': [],
                                     'preTokenBalances': [], 'postTokenBalances': []}}]}
        self.expected = {'transactions': 1, 'group_sha256': {
            name: digest(value) for name, value in groups(self.primary).items()}}

    def test_empty_arrays_only_for_preexecution_failure(self):
        other = copy.deepcopy(self.primary)
        other['transactions'][0]['meta'].update(innerInstructions=[], logMessages=[])
        original = copy.deepcopy(other)
        result = compare(other, self.expected)
        self.assertEqual(result['status'], 'MATCH')
        self.assertTrue(all(result['groups'].values()))
        self.assertEqual(result['normalized_preexecution_fields'][0]['fields'],
                         ['innerInstructions', 'logMessages'])
        self.assertEqual(other, original)

    def test_executed_transaction_is_not_normalized(self):
        other = copy.deepcopy(self.primary)
        other['transactions'][0]['meta'].update(innerInstructions=[], logMessages=[],
                                                computeUnitsConsumed=1)
        self.assertEqual(compare(other, self.expected)['status'], 'MISMATCH')

    def test_other_differences_remain_mismatch(self):
        other = copy.deepcopy(self.primary)
        other['transactions'][0]['meta'].update(innerInstructions=[], logMessages=[], fee=6000)
        self.assertEqual(compare(other, self.expected)['status'], 'MISMATCH')

    def test_exact_empty_array_reference_stays_exact(self):
        other = copy.deepcopy(self.primary)
        other['transactions'][0]['meta'].update(innerInstructions=[], logMessages=[])
        expected = {'transactions': 1, 'group_sha256': {
            name: digest(value) for name, value in groups(other).items()}}
        result = compare(other, expected)
        self.assertEqual(result['status'], 'MATCH')
        self.assertEqual(result['normalized_preexecution_fields'], [])


if __name__ == '__main__':
    unittest.main()
