#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Corner-case tests for extract-plan: the tool-hint nag cooldown, cache pruning
triggered from the reference-transaction hook, branch/ticket discovery, and
tiered diff-budget selection.

Run:  python -m unittest discover -s .git-hooks/hooks/tests -t .git-hooks -p "test_*.py" -v
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from git_hooks_impl.entry_points.extract_plan import (
    _TOKEN_BUDGET_CHARS,
    _build_tiered_diff,
    _discover_branch_and_ticket,
    _should_nag,
    cmd_cache_prune,
)
from git_hooks_impl.plan.cache import _sanitize_branch_name

# Silence ALL logging functions imported by extract_plan, plan_merge, plan_cache
# to prevent any output to TESTS.log.  Tests that assert on specific log calls
# (e.g. mock_flog.assert_any_call) use their own @patch which overrides these.
_log_patchers = [
    # git_hooks_impl.entry_points.extract_plan imports: config, dbg, err, log, ok, warn
    patch('git_hooks_impl.entry_points.extract_plan.log'),
    patch('git_hooks_impl.entry_points.extract_plan.warn'),
    patch('git_hooks_impl.entry_points.extract_plan.err'),
    patch('git_hooks_impl.entry_points.extract_plan.dbg'),
    patch('git_hooks_impl.entry_points.extract_plan.ok'),
    # git_hooks_impl.plan.merge imports: dbg, log, warn
    patch('git_hooks_impl.plan.merge.log'),
    patch('git_hooks_impl.plan.merge.warn'),
    patch('git_hooks_impl.plan.merge.dbg'),
    # git_hooks_impl.plan.cache imports: dbg, log, ok, warn
    patch('git_hooks_impl.plan.cache.log'),
    patch('git_hooks_impl.plan.cache.warn'),
    patch('git_hooks_impl.plan.cache.dbg'),
    patch('git_hooks_impl.plan.cache.ok'),
    # git_hooks_impl.branch_utils imports: dbg, log, warn
    patch('git_hooks_impl.branch_utils.log'),
    patch('git_hooks_impl.branch_utils.warn'),
    patch('git_hooks_impl.branch_utils.dbg'),
    # git_hooks_impl.utils imports: dbg
    patch('git_hooks_impl.utils.dbg'),
]


def setUpModule():
    for p in _log_patchers:
        p.start()


def tearDownModule():
    for p in _log_patchers:
        p.stop()


# ---------------------------------------------------------------------------
#  _should_nag — 24h cooldown for "tool not found" hint
# ---------------------------------------------------------------------------

class TestShouldNag(unittest.TestCase):
    """Verify _should_nag() respects the 24-hour cooldown window."""

    def test_within_cooldown_returns_false(self):
        """Nag file written recently (< 24h) -> False (suppress hint).

        _NAG_FILE mtime is 100s ago, well within the 86400s cooldown.

        Function under test: _should_nag()
        """
        with tempfile.TemporaryDirectory() as tmp:
            nag_path = os.path.join(tmp, 'tool_hint_setup_suppressor')
            with open(nag_path, 'w') as f:
                f.write('')
            now = 1_700_000_000.0
            with patch('git_hooks_impl.entry_points.extract_plan._NAG_FILE', nag_path), \
                 patch('git_hooks_impl.entry_points.extract_plan.time.time', return_value=now), \
                 patch('git_hooks_impl.entry_points.extract_plan.os.path.getmtime',
                       return_value=now - 100):
                result = _should_nag()
            self.assertFalse(result)

    def test_after_cooldown_returns_true(self):
        """Nag file written > 24h ago -> True (show hint again).

        _NAG_FILE mtime is 90000s ago, past the 86400s cooldown.

        Function under test: _should_nag()
        """
        with tempfile.TemporaryDirectory() as tmp:
            nag_path = os.path.join(tmp, 'tool_hint_setup_suppressor')
            with open(nag_path, 'w') as f:
                f.write('')
            now = 1_700_000_000.0
            with patch('git_hooks_impl.entry_points.extract_plan._NAG_FILE', nag_path), \
                 patch('git_hooks_impl.entry_points.extract_plan.time.time', return_value=now), \
                 patch('git_hooks_impl.entry_points.extract_plan.os.path.getmtime',
                       return_value=now - 90_000):
                result = _should_nag()
            self.assertTrue(result)

    def test_no_nag_file_returns_true(self):
        """No nag file on disk -> True (first run, show hint).

        Function under test: _should_nag()
        """
        with patch('git_hooks_impl.entry_points.extract_plan._NAG_FILE', '/nonexistent/nag_file'):
            result = _should_nag()
        self.assertTrue(result)

    def test_os_error_returns_true(self):
        """OSError reading nag file -> True (safe fallback: show hint).

        Function under test: _should_nag()
        """
        with tempfile.TemporaryDirectory() as tmp:
            nag_path = os.path.join(tmp, 'tool_hint_setup_suppressor')
            with open(nag_path, 'w') as f:
                f.write('')
            with patch('git_hooks_impl.entry_points.extract_plan._NAG_FILE', nag_path), \
                 patch('git_hooks_impl.entry_points.extract_plan.os.path.getmtime',
                       side_effect=OSError('permission denied')):
                result = _should_nag()
            self.assertTrue(result)


# ---------------------------------------------------------------------------
#  cmd_cache_prune — delete cache dirs for deleted branches
# ---------------------------------------------------------------------------

class TestCmdCachePrune(unittest.TestCase):
    """Verify cmd_cache_prune removes cache dirs for branches deleted via
    reference-transaction hook.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cache_dir = os.path.join(self.tmp, 'cache')
        os.makedirs(self.cache_dir)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    @patch('git_hooks_impl.entry_points.extract_plan._read_deleted_branches')
    def test_deletes_existing_cache_dir(self, mock_read):
        """Deleted branch 'feature/old' has cache dir -> rmtree removes it.

        Function under test: cmd_cache_prune()
        """
        mock_read.return_value = ['feature/old']
        branch_dir = os.path.join(self.cache_dir,
                                  _sanitize_branch_name('feature/old'))
        os.makedirs(branch_dir)
        with open(os.path.join(branch_dir, 'cached_PLAN.md'), 'w') as f:
            f.write('old plan')

        with patch('git_hooks_impl.entry_points.extract_plan._CACHE_DIR', self.cache_dir):
            result = cmd_cache_prune()

        self.assertEqual(result, 0)
        self.assertFalse(os.path.isdir(branch_dir))

    @patch('git_hooks_impl.entry_points.extract_plan._read_deleted_branches')
    def test_no_cache_dir_logs_debug(self, mock_read):
        """Deleted branch has no cache dir -> no crash, returns 0.

        Function under test: cmd_cache_prune()
        """
        mock_read.return_value = ['feature/nonexistent']
        with patch('git_hooks_impl.entry_points.extract_plan._CACHE_DIR', self.cache_dir):
            result = cmd_cache_prune()
        self.assertEqual(result, 0)

    @patch('git_hooks_impl.entry_points.extract_plan._read_deleted_branches')
    def test_no_deletions_returns_early(self, mock_read):
        """No branches deleted -> returns 0, no rmtree calls.

        Function under test: cmd_cache_prune()
        """
        mock_read.return_value = []
        result = cmd_cache_prune()
        self.assertEqual(result, 0)

    @patch('git_hooks_impl.entry_points.extract_plan._read_deleted_branches')
    def test_multiple_deletions_all_pruned(self, mock_read):
        """Multiple deleted branches -> all their cache dirs removed.

        Function under test: cmd_cache_prune()
        """
        mock_read.return_value = ['feature/a', 'feature/b']
        dir_a = os.path.join(self.cache_dir,
                             _sanitize_branch_name('feature/a'))
        dir_b = os.path.join(self.cache_dir,
                             _sanitize_branch_name('feature/b'))
        os.makedirs(dir_a)
        os.makedirs(dir_b)

        with patch('git_hooks_impl.entry_points.extract_plan._CACHE_DIR', self.cache_dir):
            result = cmd_cache_prune()

        self.assertEqual(result, 0)
        self.assertFalse(os.path.isdir(dir_a))
        self.assertFalse(os.path.isdir(dir_b))


# ---------------------------------------------------------------------------
#  _discover_branch_and_ticket — branch validation and Jira ticket parsing
# ---------------------------------------------------------------------------

class TestDiscoverBranchAndTicket(unittest.TestCase):
    """Verify _discover_branch_and_ticket() validates branch and parses ticket."""

    @patch('git_hooks_impl.entry_points.extract_plan.run')
    def test_success_returns_branch_type_ticket(self, mock_run):
        """Normal feature branch -> (branch, template_type, jira_ticket).

        Branch 'productname/fixes/PROJECTNAME-12345_race_fix' parsed by parse_branch
        Branch 'productname/fixes/PROJECTNAME-12345_race_fix' parsed by parse_branch
        -> template_type='fix', jira_ticket='PROJECTNAME-12345'.

        Function under test: _discover_branch_and_ticket()
        """
        mock_run.return_value = (0, 'productname/fixes/PROJECTNAME-12345_race_fix\n', '')
        mock_run.return_value = (0, 'productname/fixes/PROJECTNAME-12345_race_fix\n', '')
        branch, ttype, ticket = _discover_branch_and_ticket()
        self.assertEqual(branch, 'productname/fixes/PROJECTNAME-12345_race_fix')
        self.assertEqual(branch, 'productname/fixes/PROJECTNAME-12345_race_fix')
        self.assertEqual(ticket, 'PROJECTNAME-12345')
        self.assertIsNotNone(ttype)

    @patch('git_hooks_impl.entry_points.extract_plan.run')
    def test_detached_head_returns_none_triple(self, mock_run):
        """Git rev-parse returns 'HEAD' (detached) -> (None, None, None).

        Function under test: _discover_branch_and_ticket()
        """
        mock_run.return_value = (0, 'HEAD\n', '')
        branch, ttype, ticket = _discover_branch_and_ticket()
        self.assertIsNone(branch)
        self.assertIsNone(ttype)
        self.assertIsNone(ticket)

    @patch('git_hooks_impl.entry_points.extract_plan.run')
    def test_master_returns_none_triple(self, mock_run):
        """Branch is 'master' -> (None, None, None) -- skip master.

        Function under test: _discover_branch_and_ticket()
        """
        mock_run.return_value = (0, 'master\n', '')
        branch, ttype, ticket = _discover_branch_and_ticket()
        self.assertIsNone(branch)

    @patch('git_hooks_impl.entry_points.extract_plan.run')
    def test_master_or_main_returns_none_triple(self, mock_run):
        """Branch is 'main' -> (None, None, None) — skipped without error.

        Function under test: _discover_branch_and_ticket()
        """
        mock_run.return_value = (0, 'main\n', '')
        branch, ttype, ticket = _discover_branch_and_ticket()
        self.assertIsNone(branch)

    @patch('git_hooks_impl.entry_points.extract_plan.run')
    def test_git_failure_returns_none_triple(self, mock_run):
        """Git rev-parse fails (rc=1) -> (None, None, None).

        Function under test: _discover_branch_and_ticket()
        """
        mock_run.return_value = (1, '', 'fatal: error')
        branch, ttype, ticket = _discover_branch_and_ticket()
        self.assertIsNone(branch)

    @patch('git_hooks_impl.entry_points.extract_plan.run')
    def test_branch_without_ticket_returns_empty_ticket(self, mock_run):
        """Branch 'productname/fixes/no_ticket_here' -> ticket=''.
        """Branch 'productname/fixes/no_ticket_here' -> ticket=''.

        Function under test: _discover_branch_and_ticket()
        """
        mock_run.return_value = (0, 'productname/fixes/no_ticket_here\n', '')
        mock_run.return_value = (0, 'productname/fixes/no_ticket_here\n', '')
        branch, ttype, ticket = _discover_branch_and_ticket()
        self.assertEqual(branch, 'productname/fixes/no_ticket_here')
        self.assertEqual(branch, 'productname/fixes/no_ticket_here')
        self.assertEqual(ticket, '')


# ---------------------------------------------------------------------------
#  _build_tiered_diff — tier 2 path (tests + configs omitted)
# ---------------------------------------------------------------------------

class TestBuildTieredDiff(unittest.TestCase):
    """Verify _build_tiered_diff tier selection logic."""

    @patch('git_hooks_impl.entry_points.extract_plan._get_filtered_diff',
           return_value='filtered keep-only diff')
    def test_tier2_omits_tests_and_configs(self, mock_filtered):
        """Diff exceeds budget even after omitting tests -> also omit configs.

        Total = 700k chars. Tests = 50k, configs = 200k.
        After tier 1 (tests omitted): 650k > 600k budget.
        After tier 2 (configs omitted): 450k <= 600k budget -> use filtered diff.

        Function under test: _build_tiered_diff()
        """
        budget = _TOKEN_BUDGET_CHARS  # 600_000
        full_diff = 'x' * 700_000

        diff_files = [
            ('tests/test_foo.py', 50_000),        # test tier
            ('package.json', 100_000),              # config tier
            ('docs/readme.md', 100_000),            # config tier
            ('src/main.py', 200_000),               # keep
            ('src/utils.py', 250_000),              # keep
        ]

        label, text = _build_tiered_diff(
            diff_files, 'abc123', full_diff, 'stat summary', budget)

        self.assertEqual(label, 'Diff (tests + configs omitted)')
        self.assertEqual(text, 'filtered keep-only diff')
        # Filtered diff should only include keep paths
        called_paths = mock_filtered.call_args[0][1]
        self.assertIn('src/main.py', called_paths)
        self.assertIn('src/utils.py', called_paths)
        self.assertNotIn('tests/test_foo.py', called_paths)
        self.assertNotIn('package.json', called_paths)

    @patch('git_hooks_impl.entry_points.extract_plan._get_filtered_diff',
           return_value='filtered without tests')
    def test_tier1_omits_tests_only(self, mock_filtered):
        """Diff fits budget after omitting tests -> only tests omitted.

        Total = 650k chars. Tests = 100k.
        After tier 1: 550k <= 600k -> use filtered diff with configs kept.

        Function under test: _build_tiered_diff()
        """
        budget = _TOKEN_BUDGET_CHARS  # 600_000
        full_diff = 'x' * 650_000

        diff_files = [
            ('tests/test_main.py', 100_000),       # test tier
            ('package.json', 50_000),               # config tier
            ('src/core.py', 500_000),               # keep
        ]

        label, text = _build_tiered_diff(
            diff_files, 'abc123', full_diff, 'stat', budget)

        self.assertEqual(label, 'Diff (tests omitted)')
        called_paths = mock_filtered.call_args[0][1]
        self.assertIn('package.json', called_paths)
        self.assertIn('src/core.py', called_paths)

    def test_tier3_falls_back_to_diffstat(self):
        """All tiers exhausted -> falls back to diffstat.

        Total = 800k. Tests = 10k, configs = 10k. Remaining = 780k > 600k.

        Function under test: _build_tiered_diff()
        """
        budget = _TOKEN_BUDGET_CHARS
        full_diff = 'x' * 800_000
        diffstat = '3 files changed, 100 insertions(+), 50 deletions(-)'

        diff_files = [
            ('test_x.py', 10_000),
            ('data.json', 10_000),
            ('src/huge_module.py', 780_000),
        ]

        label, text = _build_tiered_diff(
            diff_files, 'abc123', full_diff, diffstat, budget)

        self.assertEqual(label, 'Diffstat')
        self.assertEqual(text, diffstat)


if __name__ == '__main__':
    unittest.main(verbosity=2)
