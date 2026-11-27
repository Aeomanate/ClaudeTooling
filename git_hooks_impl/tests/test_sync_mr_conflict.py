#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for hooks/sync_mr.py — push-time conflict detection and
resolution when the MR plan was edited on GitLab (_resolve_push_plan_conflict,
auto-merge and manual-resolution artifact paths), re-embedding the local
plan-hash after a push (_update_local_plan_hash), tolerant parsing of glab's
`mr list` JSON output, and additional gap coverage for cmd_sync_mr and
_post_discussions.

Run:  python -m unittest discover -s .git-hooks/hooks/tests -t .git-hooks -p "test_sync_mr_conflict.py" -v
"""

import json
import os
import re
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
    # plan_merge — auto-merge path in _resolve_push_plan_conflict
    patch('git_hooks_impl.plan.merge.log'),
    patch('git_hooks_impl.plan.merge.warn'),
    patch('git_hooks_impl.plan.merge.dbg'),
    # plan_cache — used by cmd_sync_mr flows exercised in the gap tests
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

from git_hooks_impl.entry_points.sync_mr import (
    _post_discussions,
    _resolve_push_plan_conflict,
    _update_local_plan_hash,
    cmd_sync_mr,
)
from git_hooks_impl.plan.parser import compute_plan_hash, extract_plan_hash
from git_hooks_impl.tests.utils import build_mr_description

# ---------------------------------------------------------------------------
#  _resolve_push_plan_conflict — detects/resolves remote edits during push
# ---------------------------------------------------------------------------

class TestResolvePushPlanConflict(unittest.TestCase):
    """Push-time conflict detection: local plan vs MR plan that was edited on GitLab."""

    def _mr_desc_with_edited_plan(self, plan_text):
        """MR description whose footer carries a stale plan-hash, simulating
        a manual edit to the MR body outside the tool.
        """
        desc = build_mr_description(plan_text)
        return re.sub(r'plan-hash: [0-9a-f]+', 'plan-hash: 000000000000', desc, count=1)

    def test_auto_merge_when_base_exists_and_no_overlap(self):
        """Base exists + non-overlapping changes -> auto-merged, should_continue=True.

        base='line A\\nline B', local adds 'line C', remote edits 'line A'
        -> _try_auto_merge returns merged content, push continues.
        """
        local_content = '# Plan\n\nline A\nline B\nline C\n'
        remote_clean = '# Plan\n\nline A-edited\nline B\n'
        current_desc = self._mr_desc_with_edited_plan(remote_clean)

        with patch('git_hooks_impl.entry_points.sync_mr._print_diff'), \
             patch('git_hooks_impl.entry_points.sync_mr._write_local_backup'), \
             patch('git_hooks_impl.entry_points.sync_mr._load_base', return_value='# Plan\n\nline A\nline B\n'), \
             patch('git_hooks_impl.entry_points.sync_mr._try_auto_merge', return_value='merged result'), \
             patch('git_hooks_impl.entry_points.sync_mr._show_merge_result'), \
             patch('git_hooks_impl.entry_points.sync_mr._write_plan') as _:
            result_content, should_continue = _resolve_push_plan_conflict(
                current_desc, local_content, 'feature/branch')

        self.assertTrue(should_continue)
        self.assertEqual(result_content, 'merged result')

    def test_conflict_stops_push_writes_artifacts(self):
        """Diverged MR plan -> writes artifacts, should_continue=False.

        No dialog, no AI — user must resolve manually then re-push.
        """
        local_content = '# Plan\n\nlocal version\n'
        remote_clean = '# Plan\n\nremote version\n'
        current_desc = self._mr_desc_with_edited_plan(remote_clean)

        with patch('git_hooks_impl.entry_points.sync_mr._print_diff'), \
             patch('git_hooks_impl.entry_points.sync_mr._write_local_backup') as _, \
             patch('git_hooks_impl.entry_points.sync_mr._load_base', return_value=None), \
             patch('git_hooks_impl.entry_points.sync_mr._write_remote') as mock_remote:
            result_content, should_continue = _resolve_push_plan_conflict(
                current_desc, local_content, 'feature/branch')

        self.assertFalse(should_continue)
        self.assertEqual(result_content, local_content)
        mock_remote.assert_called_once()

    def test_conflict_local_content_preserved(self):
        """Diverged MR plan -> returns local_content unchanged (not remote).

        Conflict keeps local so the push can detect the divergence and stop.
        """
        local_content = '# Plan\n\nlocal version\n'
        remote_clean = '# Plan\n\nremote version\n'
        current_desc = self._mr_desc_with_edited_plan(remote_clean)

        with patch('git_hooks_impl.entry_points.sync_mr._print_diff'), \
             patch('git_hooks_impl.entry_points.sync_mr._write_local_backup'), \
             patch('git_hooks_impl.entry_points.sync_mr._load_base', return_value=None), \
             patch('git_hooks_impl.entry_points.sync_mr._write_remote'):
            result_content, should_continue = _resolve_push_plan_conflict(
                current_desc, local_content, 'feature/branch')

        self.assertEqual(result_content, local_content)

    def test_no_plan_section_passes_through(self):
        """MR description has no plan-meta footer -> returns original content unchanged.

        current_desc='## Description\\nNo plan here' -> (plan_content, True).
        """
        plan_content = '# My local plan\n'
        current_desc = '## Description\nNo plan here'
        result_content, should_continue = _resolve_push_plan_conflict(
            current_desc, plan_content, 'feature/branch')
        self.assertTrue(should_continue)
        self.assertEqual(result_content, plan_content)

    def test_no_edit_detected_passes_through(self):
        """MR plan hash matches (no GitLab edit) -> returns original, should_continue=True."""
        plan_content = '# Plan\n\nSome content\n'
        current_desc = build_mr_description(plan_content)

        result_content, should_continue = _resolve_push_plan_conflict(
            current_desc, plan_content, 'feature/branch')

        self.assertTrue(should_continue)
        self.assertEqual(result_content, plan_content)


# ---------------------------------------------------------------------------
#  _update_local_plan_hash — re-embeds plan hash after push
# ---------------------------------------------------------------------------

class TestUpdateLocalPlanHash(unittest.TestCase):
    """After push, re-embed plan-hash in local PLAN.md so next push detects real changes."""

    def test_hash_re_embedded_matches_computed(self):
        """After call, embedded hash == compute_plan_hash -> mr:status shows 'synced'.

        '# Plan\\nSome content' -> plan-hash in meta matches compute_plan_hash().
        """
        with tempfile.TemporaryDirectory() as tmp:
            plan_file = os.path.join(tmp, 'PLAN.md')
            with open(plan_file, 'w', encoding='utf-8') as f:
                f.write('# Plan\nSome content\n')
            with patch('git_hooks_impl.entry_points.sync_mr.PLAN_FILE', plan_file):
                _update_local_plan_hash()
            with open(plan_file, encoding='utf-8') as f:
                content = f.read()
            stored_hash = extract_plan_hash(content)
            computed_hash = compute_plan_hash(content)
            self.assertIsNotNone(stored_hash)
            self.assertEqual(stored_hash, computed_hash)

    def test_missing_plan_file_no_error(self):
        """Plan file does not exist -> OSError caught, no crash.

        Best-effort — never fails.
        """
        with patch('git_hooks_impl.entry_points.sync_mr.PLAN_FILE', '/nonexistent/PLAN.md'):
            _update_local_plan_hash()  # should not raise


# ---------------------------------------------------------------------------
#  glab JSON parsing edge cases — single dict, non-dict items
# ---------------------------------------------------------------------------

class TestGlabJsonParsing(unittest.IsolatedAsyncioTestCase):
    """Edge cases in the glab mr list JSON parsing (_discover_open_mr lines 495-530)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._cache_patcher = patch(
            'git_hooks_impl.plan.cache._CACHE_DIR',
            os.path.join(self.tmp, 'cache'))
        self._cache_patcher.start()
        # _is_delete_push reads sys.stdin via os.read — mock to avoid I/O
        self._delete_push_patcher = patch(
            'git_hooks_impl.entry_points.sync_mr._is_delete_push', return_value=False)
        self._delete_push_patcher.start()
        # _save_cache reads PLAN_FILE from disk — mock to avoid side effects
        self._save_cache_patcher = patch('git_hooks_impl.entry_points.sync_mr._save_cache')
        self._save_cache_patcher.start()
        # _save_base writes base plan to disk — mock to avoid file I/O
        self._save_base_patcher = patch('git_hooks_impl.entry_points.sync_mr._save_base')
        self._save_base_patcher.start()
        # cmd_sync_mr canonicalizes the plan and writes it back to PLAN_FILE.
        # Redirect to a temp path so the real .ai/BRANCH_PLAN.md is untouched.
        self._plan_file_patcher = patch(
            'git_hooks_impl.entry_points.sync_mr.PLAN_FILE',
            os.path.join(self.tmp, 'BRANCH_PLAN.md'))
        self._plan_file_patcher.start()

    def tearDown(self):
        self._plan_file_patcher.stop()
        self._save_base_patcher.stop()
        self._save_cache_patcher.stop()
        self._delete_push_patcher.stop()
        self._cache_patcher.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    @patch('git_hooks_impl.entry_points.sync_mr._post_discussions', new_callable=AsyncMock, return_value='plan text')
    @patch('git_hooks_impl.entry_points.sync_mr.update_mr', new_callable=AsyncMock)
    @patch('git_hooks_impl.entry_points.sync_mr.current_user', new_callable=AsyncMock, return_value='oziuz')
    @patch('git_hooks_impl.entry_points.sync_mr.plan_check_dialog', return_value=True)
    @patch('git_hooks_impl.entry_points.sync_mr.find_tool', return_value='/usr/bin/glab')
    @patch('git_hooks_impl.entry_points.sync_mr.run_async', new_callable=AsyncMock, return_value=(0, '', ''))
    @patch('git_hooks_impl.entry_points.sync_mr.run')
    async def test_single_dict_response_treated_as_one_mr(self, mock_run, mock_run_async,
                                                      mock_tool, mock_dlg, mock_user,
                                                      mock_update, mock_post_disc):
        """Glab returns a single dict (not a list) with 'iid' -> treated as 1 MR.

        Some glab versions return {} instead of [{}] for single results.
        """
        single_dict = json.dumps({'iid': 42, 'title': 'Test MR', 'description': '## Desc'})
        mock_run.side_effect = [
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),   # git rev-parse --abbrev-ref
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),   # git rev-parse --abbrev-ref
            (0, single_dict, ''),                   # glab mr list (_discover_open_mr uses run)
        ]
        with patch('git_hooks_impl.entry_points.sync_mr.read_plan', return_value='plan text'):
            await cmd_sync_mr()

        # update_mr should have been called (found 1 MR)
        mock_update.assert_called_once()

    @patch('git_hooks_impl.entry_points.sync_mr._post_discussions', new_callable=AsyncMock, return_value='plan text')
    @patch('git_hooks_impl.entry_points.sync_mr.update_mr', new_callable=AsyncMock)
    @patch('git_hooks_impl.entry_points.sync_mr.current_user', new_callable=AsyncMock, return_value='oziuz')
    @patch('git_hooks_impl.entry_points.sync_mr.plan_check_dialog', return_value=True)
    @patch('git_hooks_impl.entry_points.sync_mr.find_tool', return_value='/usr/bin/glab')
    @patch('git_hooks_impl.entry_points.sync_mr.run_async', new_callable=AsyncMock, return_value=(0, '', ''))
    @patch('git_hooks_impl.entry_points.sync_mr.run')
    async def test_non_dict_items_in_list_filtered_out(self, mock_run, mock_run_async,
                                                   mock_tool, mock_dlg, mock_user,
                                                   mock_update, mock_post_disc):
        """List with [null, 'string', {iid: 42}] -> only the dict with 'iid' kept.

        Malformed JSON from glab: non-dict items are silently filtered.
        """
        mixed_list = json.dumps([None, 'string', {'iid': 42, 'title': 'Valid MR', 'description': ''}])
        mock_run.side_effect = [
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),   # git rev-parse --abbrev-ref
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),   # git rev-parse --abbrev-ref
            (0, mixed_list, ''),                    # glab mr list (_discover_open_mr uses run)
        ]
        with patch('git_hooks_impl.entry_points.sync_mr.read_plan', return_value='plan text'):
            await cmd_sync_mr()

        mock_update.assert_called_once()


# ---------------------------------------------------------------------------
#  Gap tests — base_PLAN.md saved after push, multiple discussions, dialog
# ---------------------------------------------------------------------------

class TestSyncMrGaps(unittest.IsolatedAsyncioTestCase):
    """Additional gap tests for cmd_sync_mr and _post_discussions."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._cache_patcher = patch(
            'git_hooks_impl.plan.cache._CACHE_DIR',
            os.path.join(self.tmp, 'cache'))
        self._cache_patcher.start()
        # _is_delete_push reads sys.stdin via os.read — mock to avoid I/O
        self._delete_push_patcher = patch(
            'git_hooks_impl.entry_points.sync_mr._is_delete_push', return_value=False)
        self._delete_push_patcher.start()
        # _save_cache reads PLAN_FILE from disk — mock to avoid side effects
        self._save_cache_patcher = patch('git_hooks_impl.entry_points.sync_mr._save_cache')
        self._save_cache_patcher.start()
        # cmd_sync_mr canonicalizes the plan and writes it back to PLAN_FILE.
        # Redirect to a temp path so the real .ai/BRANCH_PLAN.md is untouched.
        self._plan_file_patcher = patch(
            'git_hooks_impl.entry_points.sync_mr.PLAN_FILE',
            os.path.join(self.tmp, 'BRANCH_PLAN.md'))
        self._plan_file_patcher.start()

    def tearDown(self):
        self._plan_file_patcher.stop()
        self._save_cache_patcher.stop()
        self._delete_push_patcher.stop()
        self._cache_patcher.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    @patch('git_hooks_impl.entry_points.sync_mr.plan_check_dialog', return_value=True)
    @patch('git_hooks_impl.entry_points.sync_mr._post_discussions', new_callable=AsyncMock)
    @patch('git_hooks_impl.entry_points.sync_mr.update_mr', new_callable=AsyncMock)
    @patch('git_hooks_impl.entry_points.sync_mr.current_user', new_callable=AsyncMock, return_value='dev')
    @patch('git_hooks_impl.entry_points.sync_mr.find_tool', return_value='/usr/bin/glab')
    @patch('git_hooks_impl.entry_points.sync_mr.run_async', new_callable=AsyncMock, return_value=(0, '', ''))
    @patch('git_hooks_impl.entry_points.sync_mr.run')
    async def test_base_plan_saved_after_update_mr(self, mock_run, mock_run_async, mock_tool,
                                              mock_user, mock_update,
                                              mock_post_disc, mock_dlg):
        """After update_mr succeeds, _save_base is called with stripped plan content.

        Verifies the push-base snapshot is saved for 3-way merge on next push.
        """
        existing_mrs = json.dumps([{
            'iid': 42,
            'title': 'Existing MR',
            'description': '## Description\n\nOld text',
        }])
        mock_run.side_effect = [
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),
            (0, existing_mrs, ''),
        ]
        mock_post_disc.return_value = 'plan text'
        with patch('git_hooks_impl.entry_points.sync_mr.read_plan', return_value='plan text'), \
             patch('git_hooks_impl.entry_points.sync_mr._save_base', new_callable=AsyncMock) as mock_save_base:
            await cmd_sync_mr()

        mock_save_base.assert_called_once()
        args = mock_save_base.call_args.args
        self.assertEqual(args[0], 'productname/fixes/PROJECTNAME-1_fix')
        self.assertEqual(args[0], 'productname/fixes/PROJECTNAME-1_fix')

    @patch('git_hooks_impl.entry_points.sync_mr.find_tool', return_value='/usr/bin/glab')
    @patch('git_hooks_impl.entry_points.sync_mr.run')
    async def test_master_branch_skips_sync(self, mock_run, mock_tool):
        """Master branch -> rc=0, no MR operations.

        is_master_or_main('master') -> True -> skips sync, never blocks push.
        """
        mock_run.return_value = (0, 'master\n', '')
        result = await cmd_sync_mr()
        self.assertEqual(result, 0)
        # Only rev-parse should have been called
        self.assertEqual(mock_run.call_count, 1)

    @patch.dict(os.environ, {}, clear=False)
    @patch('git_hooks_impl.entry_points.sync_mr.plan_check_dialog')
    @patch('git_hooks_impl.entry_points.sync_mr.find_tool')
    @patch('git_hooks_impl.entry_points.sync_mr.run_async', new_callable=AsyncMock, return_value=(0, '', ''))
    @patch('git_hooks_impl.entry_points.sync_mr.run')
    async def test_dialog_not_called_when_no_plan(self, mock_run, mock_run_async, mock_tool, mock_dlg):
        """read_plan returns '' -> plan_check_dialog never called.

        No PLAN.md on disk means there's nothing to review before push.
        """
        mock_tool.side_effect = ['/usr/bin/glab', '/usr/bin/claude']
        mock_run.side_effect = [
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),  # git rev-parse
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),  # git rev-parse
            (0, '[]', ''),                          # glab mr list -> empty
        ]
        with patch('git_hooks_impl.entry_points.sync_mr.read_plan', return_value=''), \
             patch('git_hooks_impl.entry_points.sync_mr.create_mr'), \
             patch('git_hooks_impl.entry_points.sync_mr.current_user', return_value='dev'), \
             patch('git_hooks_impl.entry_points.sync_mr._save_cache'):
            await cmd_sync_mr()

        mock_dlg.assert_not_called()


class TestPostDiscussionsGaps(unittest.IsolatedAsyncioTestCase):
    """Additional gap tests for _post_discussions: multiple discussions, failures."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.plan_file = os.path.join(self.tmp, 'PLAN.md')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    @patch('git_hooks_impl.entry_points.sync_mr.glab_api_post')
    @patch('git_hooks_impl.entry_points.sync_mr.get_project_path', return_value='group/productname/reponame')
    @patch('git_hooks_impl.entry_points.sync_mr.get_project_path', return_value='group/productname/reponame')
    async def test_posts_multiple_discussions_in_one_push(self, mock_proj, mock_post):
        """2 unposted discussions -> 2 API calls, both URLs embedded.

        Iterates over all unposted entries, posts each, embeds URL in title.
        """
        plan = (
            '# Plan\n\n'
            '## Discussions\n\n'
            '### Topic Alpha\n\n'
            'Body for Alpha.\n\n'
            '### Topic Beta\n\n'
            'Body for Beta.\n'
        )
        with open(self.plan_file, 'w') as f:
            f.write(plan)
        mock_post.side_effect = [
            {'notes': [{'id': 100}]},
            {'notes': [{'id': 200}]},
        ]

        with patch('git_hooks_impl.entry_points.sync_mr.PLAN_FILE', self.plan_file):
            result = await _post_discussions(42, plan)

        self.assertEqual(mock_post.call_count, 2)
        self.assertIn('### [Topic Alpha]', result)
        self.assertIn('#note_100', result)
        self.assertIn('### [Topic Beta]', result)
        self.assertIn('#note_200', result)
        # Original bodies should be gone
        self.assertNotIn('Body for Alpha', result)
        self.assertNotIn('Body for Beta', result)

    @patch('git_hooks_impl.entry_points.sync_mr.glab_api_post')
    @patch('git_hooks_impl.entry_points.sync_mr.get_project_path', return_value='group/productname/reponame')
    @patch('git_hooks_impl.entry_points.sync_mr.get_project_path', return_value='group/productname/reponame')
    async def test_failed_discussion_post_preserves_body(self, mock_proj, mock_post):
        """glab_api_post returns None -> title stays plain, body preserved.

        Failed API call means the discussion is NOT converted to a link.
        """
        plan = (
            '## Discussions\n\n'
            '### Topic\n\n'
            'Important body text.\n'
        )
        with open(self.plan_file, 'w') as f:
            f.write(plan)
        mock_post.return_value = None

        with patch('git_hooks_impl.entry_points.sync_mr.PLAN_FILE', self.plan_file):
            result = await _post_discussions(42, plan)

        # Title should stay plain (no link conversion)
        self.assertIn('### Topic', result)
        self.assertNotIn('### [Topic]', result)
        # Body should be preserved (not stripped)
        self.assertIn('Important body text.', result)


if __name__ == '__main__':
    unittest.main(verbosity=2)
