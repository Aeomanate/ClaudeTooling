#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Corner-case tests for extract-plan: conflict-resolution dialog artifact writing,
error paths in template/diff/JSON handling, git-helper failure logging, log
size warnings, cache-name sanitization, and stale cache pruning.

Run:  python -m unittest discover -s .git-hooks/hooks/tests -t .git-hooks -p "test_*.py" -v
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from git_hooks_impl.entry_points.extract_plan import (
    _FALLBACK_TEMPLATE,
    _get_commit_messages,
    _get_diff_files,
    _get_diff_stat,
    _get_filtered_diff,
    _get_full_diff,
    _get_merge_base,
    _load_template,
    _resolve_conflict,
    cmd_extract_plan,
)
from git_hooks_impl.logger import _LOG_WARN_BYTES, dbg
from git_hooks_impl.plan.cache import (
    _prune_stale_caches,
    _sanitize_branch_name,
)
from git_hooks_impl.plan.context import PlanContext

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
#  Conflict resolution dialog - 8 tests
# ---------------------------------------------------------------------------

class TestResolveConflict(unittest.TestCase):
    """Tests for _resolve_conflict() - artifact-write, no dialog, no AI.

    New behavior: print diff, attempt auto-merge via git merge-file,
    on true conflict write .local/.remote artifacts and warn the user.
    """

    def setUp(self):
        self.local = '# Local Plan\n- [x] Step 1\n- [ ] Step 2\n'
        self.remote = '# Remote Plan\n- [x] Step 1\n- [x] Step 2\n'

    @patch('git_hooks_impl.plan.merge._attempt_auto_merge_with_base', return_value=None)
    @patch('git_hooks_impl.plan.merge.dbg')
    @patch('git_hooks_impl.plan.merge._print_diff')
    def test_conflict_no_branch_returns_local(self, mock_diff, mock_flog, mock_auto):
        """No branch, no auto-merge -> ('local', local_content), log written.

        Function under test: _resolve_conflict()
        Refactoring required: NO (plan_merge function, 3 deps)
        Dependency missed/absent: NO
        """
        action, content = _resolve_conflict(self.local, self.remote)
        self.assertEqual(action, 'local')
        self.assertEqual(content, self.local)
        mock_flog.assert_any_call('Conflict: artifacts written, manual resolution required')

    @patch('git_hooks_impl.plan.merge._attempt_auto_merge_with_base', return_value='# Merged\n')
    @patch('git_hooks_impl.plan.merge._print_diff')
    def test_conflict_auto_merge_returns_merged(self, mock_diff, mock_auto):
        """Auto-merge succeeds -> ('merged', merged_content), no artifacts.

        Function under test: _resolve_conflict()
        Refactoring required: NO (plan_merge function, 3 deps)
        Dependency missed/absent: NO
        """
        action, content = _resolve_conflict(self.local, self.remote)
        self.assertEqual(action, 'merged')
        self.assertEqual(content, '# Merged\n')

    @patch('git_hooks_impl.plan.merge._write_remote')
    @patch('git_hooks_impl.plan.merge._write_local_backup')
    @patch('git_hooks_impl.plan.merge._attempt_auto_merge_with_base', return_value=None)
    @patch('git_hooks_impl.plan.merge.dbg')
    @patch('git_hooks_impl.plan.merge._print_diff')
    def test_conflict_with_branch_writes_artifacts(self, mock_diff, mock_flog,
                                                    mock_auto, mock_local,
                                                    mock_remote):
        """Branch provided + no auto-merge -> .local and .remote artifacts written.

        Function under test: _resolve_conflict()
        Refactoring required: NO (plan_merge function, 3 deps)
        Dependency missed/absent: NO
        """
        action, content = _resolve_conflict(self.local, self.remote, branch='feature/x')
        self.assertEqual(action, 'local')
        self.assertEqual(content, self.local)
        mock_local.assert_called_once_with('feature/x', self.local)
        mock_remote.assert_called_once_with('feature/x', self.remote)


# ---------------------------------------------------------------------------
#  Error path tests - 4 tests
# ---------------------------------------------------------------------------

class TestErrorPaths(unittest.IsolatedAsyncioTestCase):

    async def test_load_template_missing(self):
        """plan_template.md deleted -> returns _FALLBACK_TEMPLATE, no crash.
        The fallback contains {{TITLE}} and {{CONTEXT}} placeholders so
        scaffold logic still works.

        Function under test: _load_template()
        Refactoring required: NO (8 lines, 1 dep: filesystem read)
        Dependency missed/absent: NO
        """
        with patch('git_hooks_impl.entry_points.extract_plan._TEMPLATE_PATH', '/nonexistent/plan_template.md'), \
             patch('git_hooks_impl.entry_points.extract_plan.dbg') as mock_flog:
            result = _load_template()
        self.assertEqual(result, _FALLBACK_TEMPLATE)
        self.assertIn('{{TITLE}}', result)
        self.assertIn('## Implementation Plan', result)
        # Verify it was logged
        mock_flog.assert_called_once()
        log_msg = mock_flog.call_args.args[0]
        self.assertIn('Template load failed', log_msg)

    @patch('git_hooks_impl.entry_points.extract_plan._try_ai_pipeline', new_callable=AsyncMock)
    @patch('git_hooks_impl.entry_points.extract_plan.template_skeleton', return_value=('skeleton', [], []))
    @patch('git_hooks_impl.entry_points.extract_plan._load_template', return_value='# {{TITLE}}\n{{CONTEXT}}')
    @patch('git_hooks_impl.entry_points.extract_plan.dbg')
    @patch('git_hooks_impl.entry_points.extract_plan.find_tool', return_value='/usr/bin/glab')
    @patch('git_hooks_impl.plan.cache.run', return_value=(0, 'master\n', ''))
    @patch('git_hooks_impl.entry_points.extract_plan.run')
    async def test_glab_json_parse_error_logged(self, mock_run, mock_pc_run, mock_tool, mock_flog, mock_tmpl, mock_skel, mock_pipeline):
        """Glab mr list returns invalid JSON -> warn() + dbg() called.
        Previously this was silently swallowed with 'pass'.

        Function under test: cmd_extract_plan()
        Refactoring required: YES (_extract_plan_inner: 76 lines, 7 deps)
        Dependency missed/absent: YES - was missing plan_cache.run,
            plan_cache.PLAN_FILE, plan_cache._CACHE_DIR patches
        """
        mock_pipeline.return_value = ('', PlanContext())
        mock_run.side_effect = [
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),  # git rev-parse (_extract_plan_inner)
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),  # git rev-parse (_extract_plan_inner)
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),  # cmd_cache_save -> git rev-parse
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),  # cmd_cache_save -> git rev-parse
        ]
        with tempfile.TemporaryDirectory() as tmp:
            plan_file = os.path.join(tmp, 'PLAN.md')
            with patch('git_hooks_impl.entry_points.extract_plan.PLAN_FILE', plan_file), \
                 patch('git_hooks_impl.plan.cache.PLAN_FILE', plan_file), \
                 patch('git_hooks_impl.plan.cache._CACHE_DIR', os.path.join(tmp, 'cache')), \
                 patch('git_hooks_impl.entry_points.extract_plan._NAG_FILE', os.path.join(tmp, '.nag')), \
                 patch('git_hooks_impl.entry_points.extract_plan.run_async', new_callable=AsyncMock,
                       return_value=(0, 'NOT VALID JSON{{{', '')), \
                 patch('git_hooks_impl.entry_points.extract_plan.jira_summary',
                       new_callable=AsyncMock, return_value=('', '')):
                await cmd_extract_plan()
        # Verify dbg was called with JSON parse error message
        flog_calls = [c for c in mock_flog.call_args_list if 'JSON parse error' in str(c)]
        self.assertTrue(len(flog_calls) > 0, 'dbg should be called for JSON parse error')


# ---------------------------------------------------------------------------
#  Logging tests - git helper failures + log size warning
# ---------------------------------------------------------------------------

class TestGitHelperFailuresLogged(unittest.TestCase):
    """Verify that all 6 git helpers call dbg() on rc!=0."""

    @patch('git_hooks_impl.entry_points.extract_plan.dbg')
    @patch('git_hooks_impl.entry_points.extract_plan.run', return_value=(1, '', 'error'))
    def test_get_merge_base_logs_failure(self, mock_run, mock_flog):
        """Git merge-base fails (rc=1) -> dbg records the failure.

        Function under test: _get_merge_base()
        Refactoring required: NO (12 lines, 1 dep: run)
        Dependency missed/absent: NO
        """
        result = _get_merge_base()
        self.assertEqual(result, '')
        mock_flog.assert_called_once()
        self.assertIn('merge-base failed', mock_flog.call_args.args[0])

    @patch('git_hooks_impl.entry_points.extract_plan.dbg')
    @patch('git_hooks_impl.entry_points.extract_plan.run', return_value=(1, '', 'error'))
    def test_get_diff_stat_logs_failure(self, mock_run, mock_flog):
        """Git diff --stat fails (rc=1) -> dbg records the failure.

        Function under test: _get_diff_stat()
        Refactoring required: NO (7 lines, 1 dep: run)
        Dependency missed/absent: NO
        """
        result = _get_diff_stat('abc123')
        self.assertEqual(result, '')
        mock_flog.assert_called_once()
        self.assertIn('diff --stat failed', mock_flog.call_args.args[0])

    @patch('git_hooks_impl.entry_points.extract_plan.dbg')
    @patch('git_hooks_impl.entry_points.extract_plan.run', return_value=(1, '', 'error'))
    def test_get_full_diff_logs_failure(self, mock_run, mock_flog):
        """Git diff fails (rc=1) -> dbg records the failure.

        Function under test: _get_full_diff()
        Refactoring required: NO (7 lines, 1 dep: run)
        Dependency missed/absent: NO
        """
        result = _get_full_diff('abc123')
        self.assertEqual(result, '')
        mock_flog.assert_called_once()
        self.assertIn('git diff failed', mock_flog.call_args.args[0])

    @patch('git_hooks_impl.entry_points.extract_plan.dbg')
    @patch('git_hooks_impl.entry_points.extract_plan.run', return_value=(1, '', 'error'))
    def test_get_commit_messages_logs_failure(self, mock_run, mock_flog):
        """Git log fails (rc=1) -> dbg records the failure.

        Function under test: _get_commit_messages()
        Refactoring required: NO (7 lines, 1 dep: run)
        Dependency missed/absent: NO
        """
        result = _get_commit_messages('abc123')
        self.assertEqual(result, '')
        mock_flog.assert_called_once()
        self.assertIn('git log failed', mock_flog.call_args.args[0])

    @patch('git_hooks_impl.entry_points.extract_plan.dbg')
    @patch('git_hooks_impl.entry_points.extract_plan.run', return_value=(1, '', 'error'))
    def test_get_diff_files_logs_failure(self, mock_run, mock_flog):
        """Git diff --numstat fails (rc=1) -> dbg records the failure.

        Function under test: _get_diff_files()
        Refactoring required: NO (17 lines, 1 dep: run)
        Dependency missed/absent: NO
        """
        result = _get_diff_files('abc123')
        self.assertEqual(result, [])
        mock_flog.assert_called_once()
        self.assertIn('numstat failed', mock_flog.call_args.args[0])

    @patch('git_hooks_impl.entry_points.extract_plan.dbg')
    @patch('git_hooks_impl.entry_points.extract_plan.run', return_value=(1, '', 'error'))
    def test_get_filtered_diff_logs_failure(self, mock_run, mock_flog):
        """Git diff (filtered) fails (rc=1) -> dbg records the failure.

        Function under test: _get_filtered_diff()
        Refactoring required: NO (9 lines, 1 dep: run)
        Dependency missed/absent: NO
        """
        result = _get_filtered_diff('abc123', ['src/main.py'])
        self.assertEqual(result, '')
        mock_flog.assert_called_once()
        self.assertIn('filtered', mock_flog.call_args.args[0])


class TestLogSizeWarning(unittest.TestCase):
    """Verify the 1 GB log size warning fires correctly."""

    def test_log_size_warning_at_threshold(self):
        """Log file exceeding 1 GB -> stderr warning printed every time.
        Uses a real temp file with mocked os.path.getsize to simulate 1 GB+.

        Function under test: dbg()
        Refactoring required: NO (logger function, 2 deps: filesystem, print)
        Dependency missed/absent: NO
        """
        with tempfile.TemporaryDirectory() as tmp, \
             patch('git_hooks_impl.logger._LOG_DIR', tmp), \
             patch('builtins.print') as mock_print:
                # Write a small log file, but mock getsize to return > 1 GB
                with patch('os.path.getsize', return_value=_LOG_WARN_BYTES + 1):
                    dbg('test message')

                warn_calls = [c for c in mock_print.call_args_list
                              if 'exceeds 1 GB' in str(c)]
                self.assertEqual(len(warn_calls), 1, 'Should warn about log size')

                # Second call should ALSO warn (every time, not once per session)
                with patch('os.path.getsize', return_value=_LOG_WARN_BYTES + 1):
                    dbg('another message')

                warn_calls = [c for c in mock_print.call_args_list
                              if 'exceeds 1 GB' in str(c)]
                self.assertEqual(len(warn_calls), 2, 'Should warn every time')


# ---------------------------------------------------------------------------
#  Cache naming - _sanitize_branch_name
# ---------------------------------------------------------------------------

class TestCacheNaming(unittest.TestCase):

    def test_slashes_become_underscores(self):
        """'private/oziuz/ai_plan' -> 'private_oziuz_ai_plan'.

        Function under test: _sanitize_branch_name()
        Refactoring required: NO (pure function)
        Dependency missed/absent: NO
        """
        self.assertEqual(_sanitize_branch_name('private/oziuz/ai_plan'), 'private_oziuz_ai_plan')

    def test_special_chars_stripped(self):
        """'productname/fixes/PROJECTNAME-1234_fix' -> 'productname_fixes_productname_1234_fix'.
        """'productname/fixes/PROJECTNAME-1234_fix' -> 'productname_fixes_productname_1234_fix'.

        Function under test: _sanitize_branch_name()
        Refactoring required: NO (pure function)
        Dependency missed/absent: NO
        """
        self.assertEqual(_sanitize_branch_name('productname/fixes/PROJECTNAME-1234_fix'), 'productname_fixes_productname_1234_fix')
        self.assertEqual(_sanitize_branch_name('productname/fixes/PROJECTNAME-1234_fix'), 'productname_fixes_productname_1234_fix')

    def test_lowercased(self):
        """Mixed case -> all lowercase.

        Function under test: _sanitize_branch_name()
        Refactoring required: NO (pure function)
        Dependency missed/absent: NO
        """
        self.assertEqual(_sanitize_branch_name('Feature/MyBranch'), 'feature_mybranch')

    def test_empty_returns_unknown(self):
        """Empty string -> 'unknown'.

        Function under test: _sanitize_branch_name()
        Refactoring required: NO (pure function)
        Dependency missed/absent: NO
        """
        self.assertEqual(_sanitize_branch_name(''), 'unknown')

    def test_truncated_at_80_chars(self):
        """Very long name -> truncated to 80 chars.

        Function under test: _sanitize_branch_name()
        Refactoring required: NO (pure function)
        Dependency missed/absent: NO
        """
        long_name = 'a' * 100
        result = _sanitize_branch_name(long_name)
        self.assertEqual(len(result), 80)


# ---------------------------------------------------------------------------
#  Stale cache pruning - _prune_stale_caches
# ---------------------------------------------------------------------------

class TestPruneStale(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cache_dir = os.path.join(self.tmp, 'cache')
        os.makedirs(self.cache_dir)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_prunes_deleted_branch(self):
        """Cache dir for deleted branch -> removed after prune.

        Function under test: _prune_stale_caches()
        Refactoring required: NO (29 lines, 2 deps: run, _sanitize_branch_name)
        Dependency missed/absent: NO
        """
        # Create cache for a branch
        branch_dir = os.path.join(self.cache_dir, 'feature_old')
        os.makedirs(branch_dir)
        with open(os.path.join(branch_dir, '.branch'), 'w') as f:
            f.write('feature/old\n')
        with open(os.path.join(branch_dir, 'cached_PLAN.md'), 'w') as f:
            f.write('old plan')

        # git branch --list returns only 'master' - 'feature/old' is deleted
        with patch('git_hooks_impl.plan.cache._CACHE_DIR', self.cache_dir), \
             patch('git_hooks_impl.plan.cache.run',
                   return_value=(0, 'master\nfeature/current\n', '')):
            _prune_stale_caches()

        self.assertFalse(os.path.isdir(branch_dir))

    def test_keeps_existing_branch(self):
        """Cache dir for existing branch -> kept after prune.

        Function under test: _prune_stale_caches()
        Refactoring required: NO (29 lines, 2 deps: run, _sanitize_branch_name)
        Dependency missed/absent: NO
        """
        branch_dir = os.path.join(self.cache_dir, 'feature_current')
        os.makedirs(branch_dir)
        with open(os.path.join(branch_dir, '.branch'), 'w') as f:
            f.write('feature/current\n')
        with open(os.path.join(branch_dir, 'cached_PLAN.md'), 'w') as f:
            f.write('active plan')

        with patch('git_hooks_impl.plan.cache._CACHE_DIR', self.cache_dir), \
             patch('git_hooks_impl.plan.cache.run',
                   return_value=(0, 'master\nfeature/current\n', '')):
            _prune_stale_caches()

        self.assertTrue(os.path.isdir(branch_dir))

    def test_removes_dirs_without_branch_sidecar(self):
        """Dir without .branch file -> removed as invalid cache dir.

        Function under test: _prune_stale_caches()
        Refactoring required: NO (29 lines, 2 deps: run, _sanitize_branch_name)
        Dependency missed/absent: NO
        """
        old_dir = os.path.join(self.cache_dir, 'legacy_dir')
        os.makedirs(old_dir)
        with open(os.path.join(old_dir, '001_backup.md'), 'w') as f:
            f.write('old backup')

        with patch('git_hooks_impl.plan.cache._CACHE_DIR', self.cache_dir), \
             patch('git_hooks_impl.plan.cache.run',
                   return_value=(0, 'master\n', '')):
            _prune_stale_caches()

        self.assertFalse(os.path.isdir(old_dir))


if __name__ == '__main__':
    unittest.main(verbosity=2)
