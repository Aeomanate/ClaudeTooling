#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for hooks/sync_mr.py — pure validation and lookup helpers used
before mutating an MR: plan divergence detection (_detect_plan_divergence),
branch-name preconditions for running sync (_validate_sync_preconditions),
whether a branch exists on origin (_branch_on_remote), glab MR discovery
(_discover_open_mr), cross-branch plan protection (_check_plan_uuid_mismatch),
and the merge/manual-resolution dialog paths of _resolve_push_plan_conflict.

Run:  python -m unittest discover -s .git-hooks/hooks/tests -t .git-hooks -p "test_sync_mr_validation.py" -v
"""

import json
import re
import unittest
from unittest.mock import patch

# Silence all logging — tests that verify log calls use their own @patch
_log_patchers = [
    patch('git_hooks_impl.entry_points.sync_mr.log'),
    patch('git_hooks_impl.entry_points.sync_mr.warn'),
    patch('git_hooks_impl.entry_points.sync_mr.err'),
    patch('git_hooks_impl.entry_points.sync_mr.dbg'),
    patch('git_hooks_impl.entry_points.sync_mr.ok'),
]


def setUpModule():
    for p in _log_patchers:
        p.start()


def tearDownModule():
    for p in _log_patchers:
        p.stop()

from git_hooks_impl.entry_points.sync_mr import (
    _branch_on_remote,
    _check_plan_uuid_mismatch,
    _detect_plan_divergence,
    _discover_open_mr,
    _resolve_push_plan_conflict,
    _validate_sync_preconditions,
)
from git_hooks_impl.plan.parser import (
    canonical_plan,
    embed_meta,
)
from git_hooks_impl.tests.utils import build_mr_description

# ---------------------------------------------------------------------------
#  _detect_plan_divergence — pure plan comparison logic
# ---------------------------------------------------------------------------

class TestDetectPlanDivergence(unittest.TestCase):
    """Pure helper: compare local plan vs MR plan section to detect divergence."""

    def _mr_desc_with_edited_plan(self, plan_text):
        """MR description whose footer carries a stale plan-hash, simulating
        a manual edit to the MR body outside the tool.
        """
        desc = build_mr_description(plan_text)
        return re.sub(r'plan-hash: [0-9a-f]+', 'plan-hash: 000000000000', desc, count=1)

    def test_no_plan_section_in_mr_returns_not_diverged(self):
        """MR description has no plan-meta footer -> diverged=False, empty strings."""
        diverged, mr_plan, local_c, remote_c, meta = _detect_plan_divergence(
            '## Description\nPlain MR text', '# Local plan\n')
        self.assertFalse(diverged)
        self.assertEqual(mr_plan, '')

    def test_plan_not_edited_on_mr_returns_not_diverged(self):
        """Plan hash matches (no GitLab edit) -> diverged=False."""
        plan_content = '# Plan\n\nSome content\n'
        current_desc = build_mr_description(plan_content)

        diverged, mr_plan, local_c, remote_c, meta = _detect_plan_divergence(
            current_desc, plan_content)

        self.assertFalse(diverged)
        self.assertEqual(mr_plan, canonical_plan(plan_content))

    def test_content_identical_after_stripping_returns_not_diverged(self):
        """Footer plan-hash is stale but content is unchanged -> diverged=False."""
        plan_content = '# Plan\n\nIdentical content\n'
        current_desc = self._mr_desc_with_edited_plan(plan_content)

        diverged, _, local_c, remote_c, meta = _detect_plan_divergence(
            current_desc, plan_content)

        self.assertFalse(diverged)
        # local_clean and remote_clean should both be populated
        self.assertTrue(local_c)
        self.assertTrue(remote_c)

    def test_content_diverged_returns_true(self):
        """Local and remote have different content -> diverged=True."""
        local_plan = '# Plan\n\nLocal version\n'
        remote_plan = '# Plan\n\nRemote version\n'
        current_desc = self._mr_desc_with_edited_plan(remote_plan)

        diverged, _, local_c, remote_c, meta = _detect_plan_divergence(
            current_desc, local_plan)

        self.assertTrue(diverged)
        self.assertNotEqual(local_c, remote_c)


# ---------------------------------------------------------------------------
#  _validate_sync_preconditions — pure branch validation
# ---------------------------------------------------------------------------

class TestValidateSyncPreconditions(unittest.TestCase):
    """Pure logic: decide whether MR sync should run based on branch name."""

    def test_master_branch_skips_gracefully(self):
        """branch='master' -> (False, None) — graceful skip, no error."""
        should_continue, error_msg = _validate_sync_preconditions('master')
        self.assertFalse(should_continue)
        self.assertIsNone(error_msg)

    def test_main_branch_skips_gracefully(self):
        """branch='main' -> (False, None) — graceful skip, no error."""
        should_continue, error_msg = _validate_sync_preconditions('main')
        self.assertFalse(should_continue)
        self.assertIsNone(error_msg)

    def test_detached_head_skips_gracefully(self):
        """branch='HEAD' -> (False, None) — detached HEAD skip."""
        should_continue, error_msg = _validate_sync_preconditions('HEAD')
        self.assertFalse(should_continue)
        self.assertIsNone(error_msg)

    def test_feature_branch_allowed(self):
        """Feature branch -> (True, None) — sync proceeds."""
        should_continue, error_msg = _validate_sync_preconditions('productname/fixes/PROJECTNAME-1_fix')
        should_continue, error_msg = _validate_sync_preconditions('productname/fixes/PROJECTNAME-1_fix')
        self.assertTrue(should_continue)
        self.assertIsNone(error_msg)

    def test_private_branch_allowed(self):
        """Private branch -> (True, None) — sync proceeds."""
        should_continue, error_msg = _validate_sync_preconditions('private/dev/my-work')
        self.assertTrue(should_continue)
        self.assertIsNone(error_msg)


# ---------------------------------------------------------------------------
#  _branch_on_remote — git ls-remote wrapper
# ---------------------------------------------------------------------------

class TestBranchOnRemote(unittest.TestCase):
    """_branch_on_remote: does <branch> exist on origin."""

    @patch('git_hooks_impl.entry_points.sync_mr.run')
    def test_branch_present_returns_true(self, mock_run):
        mock_run.return_value = (0, 'abc123\trefs/heads/feat/x\n', '')
        self.assertTrue(_branch_on_remote('feat/x'))
        mock_run.assert_called_once_with(['git', 'ls-remote', '--heads', 'origin', 'feat/x'])

    @patch('git_hooks_impl.entry_points.sync_mr.run')
    def test_branch_absent_returns_false(self, mock_run):
        mock_run.return_value = (0, '', '')
        self.assertFalse(_branch_on_remote('feat/x'))

    @patch('git_hooks_impl.entry_points.sync_mr.run')
    def test_command_failure_returns_false(self, mock_run):
        mock_run.return_value = (1, '', 'not a repository')
        self.assertFalse(_branch_on_remote('feat/x'))


# ---------------------------------------------------------------------------
#  _discover_open_mr — glab mr list JSON parsing
# ---------------------------------------------------------------------------

class TestDiscoverOpenMr(unittest.IsolatedAsyncioTestCase):
    """I/O helper: run glab mr list and return MR data or None."""

    @patch('git_hooks_impl.entry_points.sync_mr.run')
    async def test_no_open_mr_returns_none(self, mock_run):
        """Glab returns empty list -> (None, False) — will create new MR."""
        mock_run.return_value = (0, '[]', '')
        mr_data, should_skip = await _discover_open_mr('productname/fixes/PROJECTNAME-1_fix')
        mr_data, should_skip = await _discover_open_mr('productname/fixes/PROJECTNAME-1_fix')
        self.assertIsNone(mr_data)
        self.assertFalse(should_skip)

    @patch('git_hooks_impl.entry_points.sync_mr.run')
    async def test_one_mr_returns_data(self, mock_run):
        """Glab returns one MR -> (mr_data, False) — proceed to update."""
        mr_json = json.dumps([{'iid': 42, 'title': 'Fix it', 'description': '## Desc'}])
        mock_run.return_value = (0, mr_json, '')
        mr_data, should_skip = await _discover_open_mr('productname/fixes/PROJECTNAME-1_fix')
        mr_data, should_skip = await _discover_open_mr('productname/fixes/PROJECTNAME-1_fix')
        self.assertIsNotNone(mr_data)
        self.assertEqual(mr_data['iid'], 42)
        self.assertFalse(should_skip)

    @patch('git_hooks_impl.entry_points.sync_mr.run')
    async def test_multiple_mrs_returns_skip(self, mock_run):
        """Glab returns 2+ MRs -> (None, True) — skip sync, user must close duplicates."""
        two_mrs = json.dumps([
            {'iid': 42, 'title': 'MR 1'},
            {'iid': 43, 'title': 'MR 2'},
        ])
        mock_run.return_value = (0, two_mrs, '')
        mr_data, should_skip = await _discover_open_mr('productname/fixes/PROJECTNAME-1_fix')
        mr_data, should_skip = await _discover_open_mr('productname/fixes/PROJECTNAME-1_fix')
        self.assertIsNone(mr_data)
        self.assertTrue(should_skip)

    @patch('git_hooks_impl.entry_points.sync_mr.run')
    async def test_json_decode_error_returns_none(self, mock_run):
        """Glab returns invalid JSON -> (None, False) — will create new MR."""
        mock_run.return_value = (0, 'not valid json {{{', '')
        mr_data, should_skip = await _discover_open_mr('productname/fixes/PROJECTNAME-1_fix')
        mr_data, should_skip = await _discover_open_mr('productname/fixes/PROJECTNAME-1_fix')
        self.assertIsNone(mr_data)
        self.assertFalse(should_skip)

    @patch('git_hooks_impl.entry_points.sync_mr.run')
    async def test_glab_failure_returns_none(self, mock_run):
        """Glab exits with error -> (None, False) — will create new MR."""
        mock_run.return_value = (1, '', 'network error')
        mr_data, should_skip = await _discover_open_mr('productname/fixes/PROJECTNAME-1_fix')
        mr_data, should_skip = await _discover_open_mr('productname/fixes/PROJECTNAME-1_fix')
        self.assertIsNone(mr_data)
        self.assertFalse(should_skip)


# ---------------------------------------------------------------------------
#  _check_plan_uuid_mismatch — cross-branch plan protection
# ---------------------------------------------------------------------------

class TestCheckPlanUuidMismatch(unittest.TestCase):
    """Prevent overwriting MR with a plan from a different branch (UUID guard)."""

    def test_no_local_uuid_returns_false(self):
        """Local plan has no plan-uuid meta -> no mismatch (legacy plans OK)."""
        result = _check_plan_uuid_mismatch('# Plan\nNo meta\n', '## Description')
        self.assertFalse(result)

    def test_no_plan_section_in_mr_returns_false(self):
        """MR description has no PLAN section -> no mismatch possible."""
        local_plan = embed_meta('# Plan\n', **{'plan-uuid': 'abc-123'})
        result = _check_plan_uuid_mismatch(local_plan, '## Description\nNo plan here')
        self.assertFalse(result)

    def test_matching_uuids_returns_false(self):
        """Local UUID matches MR UUID -> no mismatch."""
        plan = embed_meta('# Plan\n\nContent\n', **{'plan-uuid': 'same-uuid-value'})
        mr_desc = build_mr_description(plan)

        result = _check_plan_uuid_mismatch(plan, mr_desc)

        self.assertFalse(result)

    def test_mismatched_uuids_returns_true(self):
        """Local UUID differs from MR UUID -> True (wrong plan loaded)."""
        local_plan = embed_meta('# Plan\n\nLocal\n', **{'plan-uuid': 'local-uuid'})
        mr_plan = embed_meta('# Plan\n\nRemote\n', **{'plan-uuid': 'remote-uuid'})
        mr_desc = build_mr_description(mr_plan)

        result = _check_plan_uuid_mismatch(local_plan, mr_desc)

        self.assertTrue(result)

    def test_mr_plan_has_no_uuid_returns_false(self):
        """MR plan exists but has no UUID meta -> no mismatch (old MR)."""
        local_plan = embed_meta('# Plan\n', **{'plan-uuid': 'abc-123'})
        mr_plan = '# Plan\n\nNo meta at all\n'
        mr_desc = build_mr_description(mr_plan)

        result = _check_plan_uuid_mismatch(local_plan, mr_desc)

        self.assertFalse(result)


# ---------------------------------------------------------------------------
#  _resolve_push_plan_conflict — merge/merge-fail/manual/abort dialog paths
# ---------------------------------------------------------------------------

class TestResolvePushPlanConflictDialogPaths(unittest.TestCase):
    """Conflict resolution artifact paths not covered by TestResolvePushPlanConflict.

    New behavior: no dialog, no AI. Writes .local/.remote artifacts,
    warns the user, returns (plan_content, False).
    """

    def _setup_divergence(self, remote_text):
        """MR description whose footer carries a stale plan-hash, simulating
        a manual edit to the MR body outside the tool.
        """
        desc = build_mr_description(remote_text)
        return re.sub(r'plan-hash: [0-9a-f]+', 'plan-hash: 000000000000', desc, count=1)

    @patch('git_hooks_impl.entry_points.sync_mr._write_remote')
    @patch('git_hooks_impl.entry_points.sync_mr._load_base', return_value=None)
    @patch('git_hooks_impl.entry_points.sync_mr._write_local_backup')
    @patch('git_hooks_impl.entry_points.sync_mr._print_diff')
    def test_conflict_writes_artifacts_and_returns_false(self, mock_diff, mock_backup,
                                                          mock_load, mock_write_remote):
        """Diverged MR plan -> writes .local/.remote, returns (local, False).

        No dialog, no AI call — artifacts written for manual resolution.
        """
        local_content = '# Plan\n\nLocal version\n'
        remote_text = '# Plan\n\nRemote version\n'
        current_desc = self._setup_divergence(remote_text)

        result_content, should_continue = _resolve_push_plan_conflict(
            current_desc, local_content, 'feature/branch')

        self.assertFalse(should_continue)
        self.assertEqual(result_content, local_content)
        mock_write_remote.assert_called_once()
        mock_backup.assert_called()

    @patch('git_hooks_impl.entry_points.sync_mr._show_merge_result')
    @patch('git_hooks_impl.entry_points.sync_mr._write_plan')
    @patch('git_hooks_impl.entry_points.sync_mr._try_auto_merge', return_value='merged content')
    @patch('git_hooks_impl.entry_points.sync_mr._load_base', return_value='base content')
    @patch('git_hooks_impl.entry_points.sync_mr._write_local_backup')
    @patch('git_hooks_impl.entry_points.sync_mr._print_diff')
    def test_auto_merge_succeeds_returns_true(self, mock_diff, mock_backup, mock_load,
                                               mock_auto_merge, mock_write, mock_show):
        """Base exists, auto-merge succeeds -> returns (merged, True), no dialog.

        Clean 3-way merge path via git merge-file.
        """
        local_content = '# Plan\n\nLocal version\n'
        remote_text = '# Plan\n\nRemote version\n'
        current_desc = self._setup_divergence(remote_text)

        result_content, should_continue = _resolve_push_plan_conflict(
            current_desc, local_content, 'feature/branch')

        self.assertTrue(should_continue)
        self.assertEqual(result_content, 'merged content')
        mock_show.assert_called_once()
        mock_write.assert_called_once()


if __name__ == '__main__':
    unittest.main(verbosity=2)
