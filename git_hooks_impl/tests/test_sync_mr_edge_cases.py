#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for hooks/sync_mr.py — remaining edge cases: writing the MR body
snapshot to the branch cache (_save_mr_description), _post_discussions when
get_project_path() fails, cmd_sync_mr when an MR is found but the local
plan content is empty, and _is_delete_push stdin-pipe branch-deletion
detection.

Run:  python -m unittest discover -s .git-hooks/hooks/tests -t .git-hooks -p "test_sync_mr_edge_cases.py" -v
"""

import json
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

# Silence all logging — tests that verify log calls use their own @patch
_log_patchers = [
    patch('git_hooks_impl.entry_points.sync_mr.log'),
    patch('git_hooks_impl.entry_points.sync_mr.warn'),
    patch('git_hooks_impl.entry_points.sync_mr.err'),
    patch('git_hooks_impl.entry_points.sync_mr.dbg'),
    patch('git_hooks_impl.entry_points.sync_mr.ok'),
    # plan_cache — _save_mr_description is tested directly in this file
    patch('git_hooks_impl.plan.cache.log'),
    patch('git_hooks_impl.plan.cache.warn'),
    patch('git_hooks_impl.plan.cache.dbg'),
    patch('git_hooks_impl.plan.cache.ok'),
]


def setUpModule():
    for p in _log_patchers:
        p.start()


def tearDownModule():
    for p in _log_patchers:
        p.stop()

import shutil

from git_hooks_impl.entry_points.sync_mr import _is_delete_push, _post_discussions, cmd_sync_mr
from git_hooks_impl.plan.cache import _save_mr_description

# ---------------------------------------------------------------------------
#  _save_mr_description — writes to .ai/cache/<branch>/
# ---------------------------------------------------------------------------

class TestSaveMrDescription(unittest.TestCase):
    """Cover _save_mr_description: writes full MR body to branch cache."""

    def test_writes_description_to_cache(self):
        """Non-empty description -> written to .ai/cache/<branch>/last_mr_description.md.

        Creates cache directory if needed, writes content verbatim.

        Function under test: _save_mr_description()
        """
        with tempfile.TemporaryDirectory() as tmp:
            with patch('git_hooks_impl.plan.cache._CACHE_DIR', tmp):
                _save_mr_description('feature/my-branch', '## Description\n\nMy MR body')
            expected = os.path.join(tmp, 'feature_mybranch', 'last_mr_description.md')
            self.assertTrue(os.path.isfile(expected))
            with open(expected, encoding='utf-8') as f:
                content = f.read()
            self.assertEqual(content, '## Description\n\nMy MR body')

    def test_oserror_silenced(self):
        """OSError during write -> silently caught, no crash.

        Best-effort debug output should never break the actual MR update.

        Function under test: _save_mr_description()
        """
        with patch('git_hooks_impl.plan.cache.os.makedirs',
                   side_effect=OSError('disk full')):
            _save_mr_description('feature/x', 'content')  # should not raise


# ---------------------------------------------------------------------------
#  _post_discussions — project path failure
# ---------------------------------------------------------------------------

class TestPostDiscussionsProjectPathFailure(unittest.IsolatedAsyncioTestCase):
    """Cover _post_discussions when get_project_path returns empty string."""

    async def test_project_path_failure_returns_plan_unchanged(self):
        """get_project_path() returns '' -> warn, return original plan_content.

        Lines 247-249: project_path empty -> skip discussion posting entirely.
        The plan content is returned unmodified.

        Function under test: _post_discussions()
        """
        plan = (
            '# Plan\n\n'
            '## Discussions\n\n'
            '### Topic\n\n'
            'Body text.\n'
        )
        with patch('git_hooks_impl.entry_points.sync_mr.get_project_path',
                   new_callable=AsyncMock, return_value=''), \
             patch('git_hooks_impl.entry_points.sync_mr.find_unposted_discussions',
                   return_value=[('Topic', 'Body text.')]):
            result = await _post_discussions(42, plan)
        self.assertEqual(result, plan)


# ---------------------------------------------------------------------------
#  cmd_sync_mr — no plan content after MR found
# ---------------------------------------------------------------------------

class TestCmdSyncMrNoPlanAfterMrFound(unittest.IsolatedAsyncioTestCase):
    """Cover cmd_sync_mr when MR exists but plan_content is empty."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._cache_patcher = patch(
            'git_hooks_impl.plan.cache._CACHE_DIR',
            os.path.join(self.tmp, 'cache'))
        self._cache_patcher.start()
        self._delete_push_patcher = patch(
            'git_hooks_impl.entry_points.sync_mr._is_delete_push', return_value=False)
        self._delete_push_patcher.start()
        self._save_cache_patcher = patch('git_hooks_impl.entry_points.sync_mr._save_cache')
        self._save_cache_patcher.start()

    def tearDown(self):
        self._save_cache_patcher.stop()
        self._delete_push_patcher.stop()
        self._cache_patcher.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    @patch('git_hooks_impl.entry_points.sync_mr.current_user', new_callable=AsyncMock, return_value='dev')
    @patch('git_hooks_impl.entry_points.sync_mr.find_tool', return_value='/usr/bin/glab')
    @patch('git_hooks_impl.entry_points.sync_mr.run')
    async def test_no_plan_content_skips_mr_update(self, mock_run, mock_tool, mock_user):
        """MR found but read_plan returns '' -> dbg + return 0, no update_mr call.

        Lines 603-605: if not plan_content: dbg(...) return 0.
        Empty plan means nothing to sync to the MR description.

        Function under test: cmd_sync_mr()
        """
        existing_mrs = json.dumps([{
            'iid': 42,
            'title': 'Existing MR',
            'description': '## Description\n\nOld text',
        }])
        mock_run.side_effect = [
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),   # git rev-parse
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),   # git rev-parse
            (0, '', ''),                              # glab auth status
            (0, existing_mrs, ''),                    # glab mr list
        ]
        with patch('git_hooks_impl.entry_points.sync_mr.read_plan', return_value=''), \
             patch('git_hooks_impl.entry_points.sync_mr.update_mr') as mock_update:
            result = await cmd_sync_mr()

        self.assertEqual(result, 0)
        mock_update.assert_not_called()


# ---------------------------------------------------------------------------
#  _is_delete_push — stdin pipe detection
# ---------------------------------------------------------------------------

class TestIsDeletePush(unittest.TestCase):
    """Tests for _is_delete_push() — detects branch deletion from git pre-push stdin."""

    @patch('git_hooks_impl.entry_points.sync_mr.sys.stdin')
    def test_tty_returns_false(self, mock_stdin):
        """TTY stdin (terminal) -> False immediately, no blocking read."""
        mock_stdin.readable.return_value = True
        mock_stdin.isatty.return_value = True
        self.assertFalse(_is_delete_push())

    @patch('git_hooks_impl.entry_points.sync_mr.os.read', return_value=b'')
    @patch('git_hooks_impl.entry_points.sync_mr.sys.stdin')
    def test_empty_pipe_returns_false(self, mock_stdin, mock_read):
        """Empty pipe stdin -> False."""
        mock_stdin.readable.return_value = True
        mock_stdin.isatty.return_value = False
        mock_stdin.fileno.return_value = 0
        self.assertFalse(_is_delete_push())

    @patch('git_hooks_impl.entry_points.sync_mr.os.read')
    @patch('git_hooks_impl.entry_points.sync_mr.sys.stdin')
    def test_all_null_sha_returns_true(self, mock_stdin, mock_read):
        """All refs have null local SHA -> True (branch deletion)."""
        mock_stdin.readable.return_value = True
        mock_stdin.isatty.return_value = False
        mock_stdin.fileno.return_value = 0
        null_sha = '0' * 40
        real_sha = 'a' * 40
        line = f'refs/heads/branch {null_sha} refs/heads/branch {real_sha}\n'
        mock_read.return_value = line.encode()
        self.assertTrue(_is_delete_push())

    @patch('git_hooks_impl.entry_points.sync_mr.os.read')
    @patch('git_hooks_impl.entry_points.sync_mr.sys.stdin')
    def test_non_null_sha_returns_false(self, mock_stdin, mock_read):
        """Non-null local SHA -> False (normal push)."""
        mock_stdin.readable.return_value = True
        mock_stdin.isatty.return_value = False
        mock_stdin.fileno.return_value = 0
        real_sha = 'a' * 40
        line = f'refs/heads/branch {real_sha} refs/heads/branch {real_sha}\n'
        mock_read.return_value = line.encode()
        self.assertFalse(_is_delete_push())

    @patch('git_hooks_impl.entry_points.sync_mr.sys.stdin', None)
    def test_no_stdin_returns_false(self):
        """sys.stdin is None -> False."""
        self.assertFalse(_is_delete_push())


if __name__ == '__main__':
    unittest.main(verbosity=2)
