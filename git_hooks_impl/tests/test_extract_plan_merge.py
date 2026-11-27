#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for hooks/extract_plan.py and git_hooks_impl/plan/merge.py —
cache-swap edge cases around the master branch, and the conflict-resolution
helpers: auto-merge via a cached push base, local/remote/merged artifact
file I/O (write, cleanup, diff display), and the top-level _resolve_conflict
branching between auto-merge and manual-artifact fallback.

Run:  python -m unittest discover -s .git-hooks/hooks/tests -t .git-hooks -p "test_extract_plan_merge.py" -v
"""

import os
import tempfile
import unittest
from unittest.mock import patch

# Silence ALL logging functions imported by extract_plan, plan_merge, plan_cache
# to prevent any output to TESTS.log.  Tests that assert on specific log calls
# use their own @patch which overrides the module-level mock for that test.
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
    # git_hooks_impl.glab imports: warn (called by get_project_path on remote URL failure)
    patch('git_hooks_impl.glab.warn'),
]


def setUpModule():
    for p in _log_patchers:
        p.start()


def tearDownModule():
    for p in _log_patchers:
        p.stop()

import shutil

from git_hooks_impl.entry_points.extract_plan import cmd_cache_swap
from git_hooks_impl.plan.cache import (
    _conflict_path,
    _sanitize_branch_name,
)
from git_hooks_impl.plan.merge import (
    _attempt_auto_merge_with_base,
    _cleanup_merged,
    _cleanup_remote,
    _resolve_conflict,
    _show_merge_result,
    _write_local_backup,
    _write_remote,
)

# ---------------------------------------------------------------------------
#  Gap tests — cache swap from master, resolve conflict edge cases
# ---------------------------------------------------------------------------

class TestCacheSwapGaps(unittest.TestCase):
    """Additional gap tests for cmd_cache_swap: master save skip."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.plan_file = os.path.join(self.tmp, '.ai', 'PLAN.md')
        self.cache_dir = os.path.join(self.tmp, '.ai', 'cache')
        os.makedirs(os.path.dirname(self.plan_file), exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    @patch('git_hooks_impl.entry_points.extract_plan._save_cache')
    @patch('git_hooks_impl.plan.cache.run')
    @patch('git_hooks_impl.entry_points.extract_plan.run')
    def test_cache_swap_from_master_no_save(self, mock_run, mock_pc_run, mock_save_cache):
        """old_branch=master -> _save_cache NOT called for master.

        Switching FROM master: no plan to save (master has no PLAN.md).

        Function under test: cmd_cache_swap()
        Refactoring required: YES (cmd_cache_swap: 59 lines, 6 deps)
        Dependency missed/absent: NO
        """
        # Pre-populate cache for target branch so it restores
        branch_dir = os.path.join(self.cache_dir, 'feature_test')
        os.makedirs(branch_dir)
        with open(os.path.join(branch_dir, 'cached_BRANCH_PLAN.md'), 'w') as f:
            f.write('cached plan')
        mock_run.side_effect = [
            (0, 'feature/test\n', ''),    # git rev-parse -> new branch (extract_plan.run)
        ]
        mock_pc_run.side_effect = [
            (0, 'master\n', ''),          # git name-rev -> old branch is master (plan_cache.run)
        ]
        with patch('git_hooks_impl.plan.cache.PLAN_FILE', self.plan_file), \
             patch('git_hooks_impl.plan.cache._CACHE_DIR', self.cache_dir):
            result = cmd_cache_swap(prev_ref='abc123')

        self.assertEqual(result, 0)
        # _save_cache should NOT have been called for master
        mock_save_cache.assert_not_called()


class TestResolveConflictGaps(unittest.TestCase):
    """Gap tests for _resolve_conflict: auto-merge path, artifact write, no-branch."""

    @patch('git_hooks_impl.plan.merge._write_remote')
    @patch('git_hooks_impl.plan.merge._write_local_backup')
    @patch('git_hooks_impl.plan.merge._attempt_auto_merge_with_base', return_value=None)
    @patch('git_hooks_impl.plan.merge._print_diff')
    @patch('git_hooks_impl.plan.merge.dbg')
    def test_no_base_writes_artifacts_returns_local(self, mock_log, mock_diff,
                                                     mock_auto, mock_local,
                                                     mock_remote):
        """No auto-merge -> writes .local/.remote artifacts, returns ('local', content).

        Function under test: _resolve_conflict()
        Refactoring required: NO (plan_merge function, 3 deps)
        Dependency missed/absent: NO
        """
        action, content = _resolve_conflict(
            'local text', 'remote text', branch='feature/x')

        mock_auto.assert_called_once()
        mock_local.assert_called_once_with('feature/x', 'local text')
        mock_remote.assert_called_once_with('feature/x', 'remote text')
        self.assertEqual(action, 'local')

    @patch('git_hooks_impl.plan.merge._write_remote')
    @patch('git_hooks_impl.plan.merge._load_base', return_value='base text')
    @patch('git_hooks_impl.plan.merge._show_merge_result')
    @patch('git_hooks_impl.plan.merge._try_auto_merge', return_value='merged text')
    @patch('git_hooks_impl.plan.merge._print_diff')
    @patch('git_hooks_impl.plan.merge.dbg')
    def test_auto_merge_succeeds_shows_result(self, mock_log, mock_diff,
                                               mock_auto_merge, mock_show,
                                               mock_load_base, mock_write_remote):
        """Base + clean auto-merge -> ('merged', merged_text), _show_merge_result called.

        Function under test: _resolve_conflict()
        Refactoring required: NO (plan_merge function, 3 deps)
        Dependency missed/absent: NO
        """
        action, content = _resolve_conflict(
            'local text', 'remote text', branch='feature/x')

        self.assertEqual(action, 'merged')
        self.assertEqual(content, 'merged text')
        mock_show.assert_called_once_with('feature/x', 'local text', 'merged text')

    @patch('git_hooks_impl.plan.merge._attempt_auto_merge_with_base', return_value=None)
    @patch('git_hooks_impl.plan.merge._print_diff')
    @patch('git_hooks_impl.plan.merge.dbg')
    def test_no_branch_no_artifacts_returns_local(self, mock_log, mock_diff, mock_auto):
        """No branch -> no artifact writes, ('local', local_content).

        Function under test: _resolve_conflict()
        Refactoring required: NO (plan_merge function, 3 deps)
        Dependency missed/absent: NO
        """
        action, content = _resolve_conflict('local text', 'remote text', branch=None)
        self.assertEqual(action, 'local')
        self.assertEqual(content, 'local text')


# ---------------------------------------------------------------------------
#  plan_merge.py — file I/O helpers (coverage gaps)
# ---------------------------------------------------------------------------

class TestWriteRemote(unittest.TestCase):
    """Tests for _write_remote() — saves remote_PLAN.md into branch cache dir."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cache_dir = os.path.join(self.tmp, '.ai', 'cache')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_write_remote_creates_file(self):
        """Branch + content -> remote_PLAN.md written to cache dir.

        Function under test: _write_remote()
        Dependency missed/absent: NO
        """
        with patch('git_hooks_impl.plan.cache._CACHE_DIR', self.cache_dir):
            _write_remote('feature/test', 'remote content here')
            expected_path = _conflict_path('feature/test', 'remote')
        self.assertTrue(os.path.isfile(expected_path))
        with open(expected_path) as f:
            self.assertEqual(f.read(), 'remote content here')


class TestWriteLocalBackup(unittest.TestCase):
    """Tests for _write_local_backup() — saves local_PLAN.md before merge."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cache_dir = os.path.join(self.tmp, '.ai', 'cache')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_write_local_backup_creates_file(self):
        """Branch + content -> local_PLAN.md written to cache dir.

        Function under test: _write_local_backup()
        Dependency missed/absent: NO
        """
        with patch('git_hooks_impl.plan.cache._CACHE_DIR', self.cache_dir):
            _write_local_backup('feature/test', 'local content backup')
            expected_path = _conflict_path('feature/test', 'local')
        self.assertTrue(os.path.isfile(expected_path))
        with open(expected_path) as f:
            self.assertEqual(f.read(), 'local content backup')


class TestCleanupRemote(unittest.TestCase):
    """Tests for _cleanup_remote() — removes remote_PLAN.md after resolution."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cache_dir = os.path.join(self.tmp, '.ai', 'cache')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_cleanup_remote_removes_file(self):
        """Existing remote_PLAN.md -> removed after cleanup.

        Function under test: _cleanup_remote()
        Dependency missed/absent: NO
        """
        branch_dir = os.path.join(self.cache_dir,
                                  _sanitize_branch_name('feature/test'))
        os.makedirs(branch_dir, exist_ok=True)
        path = os.path.join(branch_dir, 'remote_PLAN.md')
        with open(path, 'w') as f:
            f.write('remote content')
        with patch('git_hooks_impl.plan.cache._CACHE_DIR', self.cache_dir):
            _cleanup_remote('feature/test')
        self.assertFalse(os.path.isfile(path))

    def test_cleanup_remote_ignores_missing_file(self):
        """No remote_PLAN.md -> no exception raised.

        Function under test: _cleanup_remote()
        Dependency missed/absent: NO
        """
        with patch('git_hooks_impl.plan.cache._CACHE_DIR', self.cache_dir):
            _cleanup_remote('nonexistent/branch')  # should not raise


class TestCleanupMerged(unittest.TestCase):
    """Tests for _cleanup_merged() — removes merged_PLAN.md after it's been applied."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cache_dir = os.path.join(self.tmp, '.ai', 'cache')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_cleanup_merged_removes_file(self):
        """Existing merged_PLAN.md -> removed after cleanup.

        Function under test: _cleanup_merged()
        Dependency missed/absent: NO
        """
        branch_dir = os.path.join(self.cache_dir,
                                  _sanitize_branch_name('feature/test'))
        os.makedirs(branch_dir, exist_ok=True)
        path = os.path.join(branch_dir, 'merged_PLAN.md')
        with open(path, 'w') as f:
            f.write('merged content')
        with patch('git_hooks_impl.plan.cache._CACHE_DIR', self.cache_dir):
            _cleanup_merged('feature/test')
        self.assertFalse(os.path.isfile(path))

    def test_cleanup_merged_ignores_missing_file(self):
        """No merged_PLAN.md -> no exception raised.

        Function under test: _cleanup_merged()
        Dependency missed/absent: NO
        """
        with patch('git_hooks_impl.plan.cache._CACHE_DIR', self.cache_dir):
            _cleanup_merged('nonexistent/branch')  # should not raise


class TestShowMergeResult(unittest.TestCase):
    """Tests for _show_merge_result() — prints diff and saves merged_PLAN.md."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cache_dir = os.path.join(self.tmp, '.ai', 'cache')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    @patch('git_hooks_impl.plan.merge._build_diff_lines',
           return_value=[('change', '+L1: new line')])
    def test_show_merge_result_writes_file_and_logs_diff(self, mock_diff):
        """Diff lines present -> printed, merged_PLAN.md saved to cache dir.

        Function under test: _show_merge_result()
        Dependency missed/absent: NO
        """
        with patch('git_hooks_impl.plan.cache._CACHE_DIR', self.cache_dir):
            _show_merge_result('feature/test', 'local text', 'merged text')
        branch_dir = os.path.join(self.cache_dir,
                                  _sanitize_branch_name('feature/test'))
        expected_path = os.path.join(branch_dir, 'merged_PLAN.md')
        self.assertTrue(os.path.isfile(expected_path))
        with open(expected_path) as f:
            self.assertEqual(f.read(), 'merged text')
        mock_diff.assert_called_once_with('local text', 'merged text')

    @patch('git_hooks_impl.plan.merge._build_diff_lines', return_value=[])
    def test_show_merge_result_no_diff(self, mock_diff):
        """Empty diff -> 'no diff' message logged, merged_PLAN.md still saved.

        Function under test: _show_merge_result()
        Dependency missed/absent: NO
        """
        with patch('git_hooks_impl.plan.cache._CACHE_DIR', self.cache_dir):
            _show_merge_result('feature/test', 'same text', 'same text')
        branch_dir = os.path.join(self.cache_dir,
                                  _sanitize_branch_name('feature/test'))
        expected_path = os.path.join(branch_dir, 'merged_PLAN.md')
        self.assertTrue(os.path.isfile(expected_path))


# ---------------------------------------------------------------------------
#  plan_merge.py — _attempt_auto_merge_with_base (coverage gaps)
# ---------------------------------------------------------------------------

class TestAttemptAutoMergeWithBase(unittest.TestCase):
    """Tests for _attempt_auto_merge_with_base() — 3-way merge using cached base."""

    @patch('git_hooks_impl.plan.merge._show_merge_result')
    @patch('git_hooks_impl.plan.merge._try_auto_merge', return_value='merged result')
    @patch('git_hooks_impl.plan.merge._load_base', return_value='base text')
    def test_success_returns_merged(self, mock_load, mock_merge, mock_show):
        """Base exists + merge succeeds -> returns merged content, shows result.

        Function under test: _attempt_auto_merge_with_base()
        Dependency missed/absent: NO
        """
        result = _attempt_auto_merge_with_base('local', 'remote', 'feature/x')
        self.assertEqual(result, 'merged result')
        mock_load.assert_called_once_with('feature/x')
        mock_merge.assert_called_once_with('base text', 'local', 'remote')
        mock_show.assert_called_once_with('feature/x', 'local', 'merged result')

    def test_no_branch_returns_none(self):
        """branch=None -> returns None without loading base.

        Function under test: _attempt_auto_merge_with_base()
        Dependency missed/absent: NO
        """
        result = _attempt_auto_merge_with_base('local', 'remote', None)
        self.assertIsNone(result)

    @patch('git_hooks_impl.plan.merge._load_base', return_value=None)
    def test_no_base_returns_none(self, mock_load):
        """No push base in cache -> returns None.

        Function under test: _attempt_auto_merge_with_base()
        Dependency missed/absent: NO
        """
        result = _attempt_auto_merge_with_base('local', 'remote', 'feature/x')
        self.assertIsNone(result)

    @patch('git_hooks_impl.plan.merge._try_auto_merge', return_value=None)
    @patch('git_hooks_impl.plan.merge._load_base', return_value='base text')
    def test_merge_fails_returns_none(self, mock_load, mock_merge):
        """Base exists but merge-file fails (conflicts) -> returns None.

        Function under test: _attempt_auto_merge_with_base()
        Dependency missed/absent: NO
        """
        result = _attempt_auto_merge_with_base('local', 'remote', 'feature/x')
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
#  plan_merge.py — _resolve_conflict merge/manual/abort with branch (coverage gaps)
# ---------------------------------------------------------------------------

class TestResolveConflictBranchPaths(unittest.TestCase):
    """Tests for _resolve_conflict() with a branch arg.

    New behavior: no dialog, no AI. Writes .local/.remote artifacts,
    warns the user, returns ('local', local_content).
    Auto-merge path tested via _attempt_auto_merge_with_base.
    """

    def setUp(self):
        self.local = '# Local Plan\n- local step\n'
        self.remote = '# Remote Plan\n- remote step\n'

    @patch('git_hooks_impl.plan.merge._attempt_auto_merge_with_base', return_value='# Merged\n')
    @patch('git_hooks_impl.plan.merge._print_diff')
    def test_resolve_auto_merge_succeeds_with_branch(self, mock_diff, mock_auto):
        """Auto-merge succeeds -> ('merged', merged_content), no artifacts written.

        Function under test: _resolve_conflict()
        Dependency missed/absent: NO
        """
        action, content = _resolve_conflict(
            self.local, self.remote, branch='feature/x')
        self.assertEqual(action, 'merged')
        self.assertEqual(content, '# Merged\n')

    @patch('git_hooks_impl.plan.merge._write_remote')
    @patch('git_hooks_impl.plan.merge._write_local_backup')
    @patch('git_hooks_impl.plan.merge._attempt_auto_merge_with_base', return_value=None)
    @patch('git_hooks_impl.plan.merge._print_diff')
    def test_resolve_no_auto_merge_writes_artifacts(self, mock_diff, mock_auto,
                                                     mock_local, mock_remote):
        """No auto-merge + branch -> writes .local and .remote artifacts, returns local.

        Function under test: _resolve_conflict()
        Dependency missed/absent: NO
        """
        action, content = _resolve_conflict(
            self.local, self.remote, branch='feature/x')
        self.assertEqual(action, 'local')
        self.assertEqual(content, self.local)
        mock_local.assert_called_once_with('feature/x', self.local)
        mock_remote.assert_called_once_with('feature/x', self.remote)

    @patch('git_hooks_impl.plan.merge._attempt_auto_merge_with_base', return_value=None)
    @patch('git_hooks_impl.plan.merge._print_diff')
    def test_resolve_no_branch_returns_local_no_artifacts(self, mock_diff, mock_auto):
        """No branch -> no artifact writes, returns local content.

        Function under test: _resolve_conflict()
        Dependency missed/absent: NO
        """
        action, content = _resolve_conflict(self.local, self.remote, branch=None)
        self.assertEqual(action, 'local')
        self.assertEqual(content, self.local)


if __name__ == '__main__':
    unittest.main(verbosity=2)
