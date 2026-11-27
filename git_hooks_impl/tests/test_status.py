#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for hooks/status.py — plan/MR sync state display.

Run:  python -m unittest git_hooks_impl.tests.test_status -v
"""

import io
import json
import unittest
from io import StringIO
from unittest.mock import AsyncMock, mock_open, patch

from git_hooks_impl.branch_utils import visible_body_for_reconstruction
from git_hooks_impl.entry_points.status import (
    _STATE_DIVERGED,
    _STATE_LOCAL,
    _STATE_NEW,
    _STATE_REMOTE,
    _STATE_SYNCED,
    _content_state,
    _fetch_mr,
    _format_diff,
    _local_only_state,
    _mr_display,
    cmd_status,
)
from git_hooks_impl.plan.parser import (
    compute_body_hash,
    compute_plan_hash,
    embed_meta,
    extract_footer_meta,
    reconstruct_plan_content,
)
from git_hooks_impl.tests.utils import build_full_mr_description

# ---------------------------------------------------------------------------
#  Module-level log silencing — prevent TESTS.log pollution
# ---------------------------------------------------------------------------

_log_patchers = []

def setUpModule():
    targets = [
        'git_hooks_impl.entry_points.status.warn',
    ]
    for t in targets:
        p = patch(t)
        p.start()
        _log_patchers.append(p)

def tearDownModule():
    for p in _log_patchers:
        p.stop()
    _log_patchers.clear()


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

SAMPLE_PLAN = '# [Test Plan]\n\n## Context\n\nSome context here.\n'

def _plan_with_hashes(content=SAMPLE_PLAN):
    """Embed correct plan-hash and body-hash into content."""
    plan_hash = compute_plan_hash(content)
    body_hash = compute_body_hash(content)
    return embed_meta(content, **{'plan-hash': plan_hash, 'body-hash': body_hash})


def _mr_json(iid=42, title='Test MR', draft=True, description=''):
    """Build a glab mr list JSON response for a single MR."""
    return json.dumps([{
        'iid': iid,
        'title': title,
        'draft': draft,
        'state': 'opened',
        'description': description,
    }])


def _wrap_plan_in_mr(plan_content, body_text='## Description\n\nSome body.'):
    """Wrap plan content in a full MR description with plan-meta footer and
    body-hash comment.

    Mirrors what sync_mr produces on push via update_mr()'s assembly.
    """
    return build_full_mr_description(plan_content, clean_body=body_text)


# ---------------------------------------------------------------------------
#  _content_state — direct content comparison (local vs MR)
# ---------------------------------------------------------------------------

class TestContentState(unittest.TestCase):

    def test_no_stored_hash_means_new(self):
        """No MR stored hash (never pushed) -> 'new (never pushed)'."""
        self.assertEqual(_content_state('aaa', 'bbb', None), _STATE_NEW)

    def test_matching_content_means_synced(self):
        """local_hash == mr_hash -> 'synced' regardless of mr_stored hash."""
        self.assertEqual(_content_state('abc', 'abc', 'abc'), _STATE_SYNCED)
        self.assertEqual(_content_state('abc', 'abc', 'old'), _STATE_SYNCED)

    def test_local_changed_only(self):
        """Local differs from MR, MR matches its stored -> 'modified locally'.

        Push set mr_stored='aaa', MR still has 'aaa', local edited to 'bbb'.
        """
        self.assertEqual(_content_state('bbb', 'aaa', 'aaa'), _STATE_LOCAL)

    def test_remote_changed_only(self):
        """MR differs from its stored, local matches stored -> 'modified on MR'.

        Push set mr_stored='aaa', local still has 'aaa', MR edited to 'ccc'.
        """
        self.assertEqual(_content_state('aaa', 'ccc', 'aaa'), _STATE_REMOTE)

    def test_both_changed(self):
        """Both local and MR differ from MR stored -> 'diverged'."""
        self.assertEqual(_content_state('bbb', 'ccc', 'aaa'), _STATE_DIVERGED)

    def test_re_hashed_local_still_detects_difference(self):
        """Local re-hashed but MR unchanged -> 'modified locally'.

        mr_stored='aaa' (set at push), MR still 'aaa' (untouched),
        local edited to 'bbb'. MR's stored hash is the reliable anchor.
        """
        self.assertEqual(_content_state('bbb', 'aaa', 'aaa'), _STATE_LOCAL)


# ---------------------------------------------------------------------------
#  _local_only_state — fallback when no MR available
# ---------------------------------------------------------------------------

class TestLocalOnlyState(unittest.TestCase):

    def test_no_stored_hash_means_new(self):
        """No meta block (never pushed) -> 'new (never pushed)'."""
        self.assertEqual(_local_only_state(None, 'abc123'), _STATE_NEW)

    def test_matching_hashes_means_synced(self):
        """Stored hash == computed hash -> 'synced'."""
        self.assertEqual(_local_only_state('abc123', 'abc123'), _STATE_SYNCED)

    def test_mismatched_hashes_means_local_modified(self):
        """Stored hash != computed hash -> 'modified locally'."""
        self.assertEqual(_local_only_state('abc123', 'def456'), _STATE_LOCAL)


# ---------------------------------------------------------------------------
#  _fetch_mr — glab mr list wrapper
# ---------------------------------------------------------------------------

class TestFetchMr(unittest.IsolatedAsyncioTestCase):

    @patch('git_hooks_impl.entry_points.status.run_async', new_callable=AsyncMock)
    async def test_success_single_mr(self, mock_run):
        """Single open MR -> return its data dict."""
        mock_run.return_value = (0, _mr_json(), '')
        mr_data, error = await _fetch_mr('my-branch')
        self.assertIsNone(error)
        self.assertEqual(mr_data['iid'], 42)

    @patch('git_hooks_impl.entry_points.status.run_async', new_callable=AsyncMock)
    async def test_glab_failure(self, mock_run):
        """Glab exits non-zero -> error string with exit code."""
        mock_run.return_value = (1, '', 'connection refused')
        mr_data, error = await _fetch_mr('my-branch')
        self.assertIsNone(mr_data)
        self.assertIn('glab failed', error)

    @patch('git_hooks_impl.entry_points.status.run_async', new_callable=AsyncMock)
    async def test_empty_output(self, mock_run):
        """Glab returns empty stdout -> 'none' (no MR)."""
        mock_run.return_value = (0, '', '')
        mr_data, error = await _fetch_mr('my-branch')
        self.assertIsNone(mr_data)
        self.assertEqual(error, 'none')

    @patch('git_hooks_impl.entry_points.status.run_async', new_callable=AsyncMock)
    async def test_empty_json_array(self, mock_run):
        """Glab returns '[]' -> 'none' (no open MRs)."""
        mock_run.return_value = (0, '[]', '')
        mr_data, error = await _fetch_mr('my-branch')
        self.assertIsNone(mr_data)
        self.assertEqual(error, 'none')

    @patch('git_hooks_impl.entry_points.status.run_async', new_callable=AsyncMock)
    async def test_multiple_mrs(self, mock_run):
        """Multiple open MRs -> error with count."""
        two_mrs = json.dumps([{'iid': 1}, {'iid': 2}])
        mock_run.return_value = (0, two_mrs, '')
        mr_data, error = await _fetch_mr('my-branch')
        self.assertIsNone(mr_data)
        self.assertIn('multiple MRs (2)', error)

    @patch('git_hooks_impl.entry_points.status.run_async', new_callable=AsyncMock)
    async def test_invalid_json(self, mock_run):
        """Glab returns garbage -> error about invalid JSON."""
        mock_run.return_value = (0, 'not json', '')
        mr_data, error = await _fetch_mr('my-branch')
        self.assertIsNone(mr_data)
        self.assertIn('invalid JSON', error)

    @patch('git_hooks_impl.entry_points.status.run_async', new_callable=AsyncMock)
    async def test_single_dict_not_wrapped_in_list(self, mock_run):
        """Glab returns a single dict (not a list) -> still parsed correctly."""
        mock_run.return_value = (0, json.dumps({'iid': 42, 'title': 'MR'}), '')
        mr_data, error = await _fetch_mr('my-branch')
        self.assertIsNone(error)
        self.assertEqual(mr_data['iid'], 42)


# ---------------------------------------------------------------------------
#  _mr_display — formatting MR info line
# ---------------------------------------------------------------------------

class TestMrDisplay(unittest.TestCase):

    def test_draft_mr(self):
        """Draft MR -> '!42 "title" (draft)'."""
        result = _mr_display({'iid': 42, 'title': 'Test', 'draft': True, 'state': 'opened'})
        self.assertEqual(result, '!42 "Test" (draft)')

    def test_opened_mr(self):
        """Non-draft MR -> '!42 "title" (opened)'."""
        result = _mr_display({'iid': 42, 'title': 'Test', 'draft': False, 'state': 'opened'})
        self.assertEqual(result, '!42 "Test" (opened)')

    def test_missing_fields_use_defaults(self):
        """Missing iid/title -> '?' and empty string."""
        result = _mr_display({})
        self.assertEqual(result, '!? "" (opened)')


# ---------------------------------------------------------------------------
#  Plan reconstruction — pulling plan from MR description
# ---------------------------------------------------------------------------

class TestExtractPlanContentFromMR(unittest.TestCase):
    """Tests the plan-meta footer reconstruction sequence as status.py uses it:
    extract_footer_meta + visible_body_for_reconstruction + reconstruct_plan_content.
    """

    def _extract_from_description(self, description):
        """Mimic status.py's reconstruction call site."""
        footer_meta = extract_footer_meta(description)
        body = visible_body_for_reconstruction(description)
        return reconstruct_plan_content(footer_meta, body)

    def test_extracts_plan_content(self):
        """MR description with a plan-meta footer -> plan content reconstructed."""
        plan = '# [Title]\n\n## Context\n\nText.\n'
        description = _wrap_plan_in_mr(plan)
        result = self._extract_from_description(description)
        self.assertIn('## Context', result)
        self.assertIn('Text.', result)

    def test_no_plan_section(self):
        """MR description without a plan-meta footer -> None."""
        result = self._extract_from_description('## Description\n\nJust a body.')
        self.assertIsNone(result)

    def test_empty_description(self):
        """Empty description -> None."""
        result = self._extract_from_description('')
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
#  _format_diff — colorized unified diff
# ---------------------------------------------------------------------------

class TestFormatDiff(unittest.TestCase):

    def test_identical_content_returns_empty(self):
        """Same content after strip_meta -> no diff output."""
        plan = _plan_with_hashes()
        result = _format_diff(plan, plan)
        self.assertEqual(result, '')

    def test_different_content_produces_diff(self):
        """Different plan content -> unified diff with +/- lines."""
        mr_plan = _plan_with_hashes('# [Title]\n\n## Context\n\nOld text.\n')
        local_plan = _plan_with_hashes('# [Title]\n\n## Context\n\nNew text.\n')
        result = _format_diff(mr_plan, local_plan)
        self.assertIn('Old text', result)
        self.assertIn('New text', result)

    def test_diff_contains_file_headers(self):
        """Diff includes --- MR / +++ local headers."""
        mr_plan = '# A\n'
        local_plan = '# B\n'
        result = _format_diff(mr_plan, local_plan)
        self.assertIn('MR', result)
        self.assertIn('local', result)

    def test_unicode_in_diff_no_crash(self):
        """Plan with Unicode arrows (→) in diff -> no UnicodeEncodeError on Windows.

        Windows cp1252 console can't encode U+2192 (→). The diff formatter
        must produce output that cmd_status can safely print.
        """
        mr_plan = '# Title\n\n## Context\n\nOld 65%→72%.\n'
        local_plan = '# Title\n\n## Context\n\nNew 70%→80%.\n'
        result = _format_diff(mr_plan, local_plan)
        # Diff should contain the arrow character (formatting works)
        self.assertIn('→', result)


# ---------------------------------------------------------------------------
#  cmd_status — full integration (all I/O mocked)
# ---------------------------------------------------------------------------

class TestCmdStatus(unittest.IsolatedAsyncioTestCase):

    async def _run_status(self, mock_run_async, mock_run, mock_isfile, mock_open_fn,
                          branch='feature/test', plan_content=None,
                          glab_response=None, glab_exit_code=0,
                          plan_exists=True):
        """Helper to run cmd_status with controlled mocks.

        Returns captured stdout as a string.
        """
        # run_async covers glab mr list (called by _fetch_mr)
        if glab_response is not None:
            mock_run_async.return_value = (glab_exit_code, glab_response, '')
        else:
            mock_run_async.return_value = (glab_exit_code, '', 'error')

        # run covers sync git calls (rev-parse HEAD, upstream, log)
        run_calls = [
            (0, f'  {branch}  \n', ''),
            (128, '', 'error: no upstream configured'),
            (0, 'abc1234 test commit\n', ''),
        ]
        mock_run.side_effect = run_calls
        mock_isfile.return_value = plan_exists

        if plan_content is not None:
            mock_open_fn.return_value.__enter__.return_value.read.return_value = plan_content

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            await cmd_status()
        return mock_stdout.getvalue()

    @patch('git_hooks_impl.entry_points.status.run')
    async def test_detached_head(self, mock_run):
        """Detached HEAD -> warning, no further output."""
        mock_run.return_value = (0, 'HEAD\n', '')
        with patch('sys.stderr'):
            await cmd_status()
        # No crash — just returns after warning, no further git calls
        self.assertEqual(mock_run.call_count, 1)

    @patch('git_hooks_impl.entry_points.status.run_async', new_callable=AsyncMock)
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.isfile')
    @patch('git_hooks_impl.entry_points.status.run')
    async def test_no_plan_file(self, mock_run, mock_isfile, mock_open_fn, mock_run_async):
        """No .ai/PLAN.md -> 'no plan file' message."""
        mock_run.side_effect = [
            (0, 'feature/test\n', ''),                  # git rev-parse HEAD
            (128, '', 'error: no upstream configured'),  # rev-parse upstream
            (0, 'abc1234 test commit\n', ''),            # git log master..HEAD
        ]
        mock_isfile.return_value = False
        mock_run_async.return_value = (0, '[]', '')

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            await cmd_status()
        output = mock_stdout.getvalue()
        self.assertIn('no plan file', output)
        self.assertIn('feature/test', output)

    @patch('git_hooks_impl.entry_points.status.run_async', new_callable=AsyncMock)
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.isfile')
    @patch('git_hooks_impl.entry_points.status.run')
    async def test_plan_never_pushed(self, mock_run, mock_isfile, mock_open_fn, mock_run_async):
        """Plan exists but no meta block -> 'new (never pushed)'."""
        output = await self._run_status(
            mock_run_async, mock_run, mock_isfile, mock_open_fn,
            plan_content=SAMPLE_PLAN,
            glab_response='[]',
        )
        self.assertIn('new (never pushed)', output)
        self.assertIn('none', output)

    @patch('git_hooks_impl.entry_points.status.run_async', new_callable=AsyncMock)
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.isfile')
    @patch('git_hooks_impl.entry_points.status.run')
    async def test_plan_synced_no_mr(self, mock_run, mock_isfile, mock_open_fn, mock_run_async):
        """Plan with correct hashes, no MR -> 'synced' (local check only)."""
        plan = _plan_with_hashes()
        output = await self._run_status(
            mock_run_async, mock_run, mock_isfile, mock_open_fn,
            plan_content=plan,
            glab_response='[]',
        )
        self.assertIn('synced', output)

    @patch('git_hooks_impl.entry_points.status.run_async', new_callable=AsyncMock)
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.isfile')
    @patch('git_hooks_impl.entry_points.status.run')
    async def test_plan_modified_locally_no_mr(self, mock_run, mock_isfile, mock_open_fn, mock_run_async):
        """Plan modified after push, no MR -> 'modified locally' (local check)."""
        original = '# [Title]\n\n## Context\n\nOriginal.\n'
        plan_with_old_hashes = _plan_with_hashes(original)
        modified = plan_with_old_hashes.replace('Original.', 'Modified locally.')

        output = await self._run_status(
            mock_run_async, mock_run, mock_isfile, mock_open_fn,
            plan_content=modified,
            glab_response='[]',
        )
        self.assertIn('modified locally', output)

    @patch('git_hooks_impl.entry_points.status.run_async', new_callable=AsyncMock)
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.isfile')
    @patch('git_hooks_impl.entry_points.status.run')
    async def test_glab_failure_graceful(self, mock_run, mock_isfile, mock_open_fn, mock_run_async):
        """Glab fails -> 'offline' message, local-only info still shown."""
        plan = _plan_with_hashes()
        output = await self._run_status(
            mock_run_async, mock_run, mock_isfile, mock_open_fn,
            plan_content=plan,
            glab_exit_code=1,
        )
        self.assertIn('offline', output)
        self.assertIn('synced', output)

    @patch('git_hooks_impl.entry_points.status.run_async', new_callable=AsyncMock)
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.isfile')
    @patch('git_hooks_impl.entry_points.status.run')
    async def test_mr_found_plan_synced(self, mock_run, mock_isfile, mock_open_fn, mock_run_async):
        """MR exists, same plan content on both sides -> 'synced'."""
        plan = _plan_with_hashes()
        mr_description = _wrap_plan_in_mr(plan)
        mr_json = _mr_json(description=mr_description)

        output = await self._run_status(
            mock_run_async, mock_run, mock_isfile, mock_open_fn,
            plan_content=plan,
            glab_response=mr_json,
        )
        self.assertIn('!42', output)
        self.assertIn('synced', output)
        self.assertNotIn('---', output)
        self.assertNotIn('+++', output)

    @patch('git_hooks_impl.entry_points.status.run_async', new_callable=AsyncMock)
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.isfile')
    @patch('git_hooks_impl.entry_points.status.run')
    async def test_mr_found_local_modified(self, mock_run, mock_isfile, mock_open_fn, mock_run_async):
        """Local content differs from MR -> 'modified locally' + diff.

        Local: 'Edited locally', MR: 'Original'. Stored hash matches MR (=original).
        """
        original = '# [Title]\n\n## Context\n\nOriginal.\n'
        plan_on_mr = _plan_with_hashes(original)
        mr_description = _wrap_plan_in_mr(plan_on_mr)
        mr_json = _mr_json(description=mr_description)

        local_plan = plan_on_mr.replace('Original.', 'Edited locally.')

        output = await self._run_status(
            mock_run_async, mock_run, mock_isfile, mock_open_fn,
            plan_content=local_plan,
            glab_response=mr_json,
        )
        self.assertIn('modified locally', output)
        self.assertIn('Original', output)
        self.assertIn('Edited locally', output)

    @patch('git_hooks_impl.entry_points.status.run_async', new_callable=AsyncMock)
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.isfile')
    @patch('git_hooks_impl.entry_points.status.run')
    async def test_local_edited_and_rehashed_still_detects_diff(self, mock_run, mock_isfile, mock_open_fn, mock_run_async):
        """Local plan edited + meta re-hashed, MR has old content -> 'modified locally'.

        This is the key scenario: stored hash was re-embedded locally (e.g.
        by a hook), but the actual content differs from MR. The MR's own
        stored hash is the reliable anchor — it wasn't re-embedded.
        """
        original = '# [Title]\n\n## Context\n\nOriginal.\n'
        plan_on_mr = _plan_with_hashes(original)
        mr_description = _wrap_plan_in_mr(plan_on_mr)
        mr_json = _mr_json(description=mr_description)

        # Local: content edited AND hashes re-embedded (local stored == computed)
        edited = '# [Title]\n\n## Context\n\nEdited locally.\n'
        local_plan = _plan_with_hashes(edited)

        output = await self._run_status(
            mock_run_async, mock_run, mock_isfile, mock_open_fn,
            plan_content=local_plan,
            glab_response=mr_json,
        )
        plan_line = [line for line in output.splitlines() if line.startswith('Plan:')][0]
        self.assertIn('modified locally', plan_line)

    @patch('git_hooks_impl.entry_points.status.run_async', new_callable=AsyncMock)
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.isfile')
    @patch('git_hooks_impl.entry_points.status.run')
    async def test_mr_found_remote_modified(self, mock_run, mock_isfile, mock_open_fn, mock_run_async):
        """MR plan edited on GitLab, local unchanged -> 'modified on MR'."""
        original = '# [Title]\n\n## Context\n\nOriginal.\n'
        plan_synced = _plan_with_hashes(original)

        # Tamper the visible body of the already-built description, so the
        # plan-meta footer still carries the hash of the original content.
        mr_description = _wrap_plan_in_mr(plan_synced)
        mr_description = mr_description.replace('Original.', 'Edited on GitLab.')
        mr_json = _mr_json(description=mr_description)

        output = await self._run_status(
            mock_run_async, mock_run, mock_isfile, mock_open_fn,
            plan_content=plan_synced,
            glab_response=mr_json,
        )
        self.assertIn('modified on MR', output)

    @patch('git_hooks_impl.entry_points.status.run_async', new_callable=AsyncMock)
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.isfile')
    @patch('git_hooks_impl.entry_points.status.run')
    async def test_both_sides_modified(self, mock_run, mock_isfile, mock_open_fn, mock_run_async):
        """Both local and MR edited since last push -> 'diverged'."""
        original = '# [Title]\n\n## Context\n\nOriginal.\n'
        plan_synced = _plan_with_hashes(original)

        # Tamper the visible body of the already-built description, so the
        # plan-meta footer still carries the hash of the original content.
        mr_description = _wrap_plan_in_mr(plan_synced)
        mr_description = mr_description.replace('Original.', 'Edited on GitLab.')
        mr_json = _mr_json(description=mr_description)

        local_plan = plan_synced.replace('Original.', 'Edited locally.')

        output = await self._run_status(
            mock_run_async, mock_run, mock_isfile, mock_open_fn,
            plan_content=local_plan,
            glab_response=mr_json,
        )
        self.assertIn('diverged', output)

    @patch('git_hooks_impl.entry_points.status.run_async', new_callable=AsyncMock)
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.isfile')
    @patch('git_hooks_impl.entry_points.status.run')
    async def test_mr_no_plan_section(self, mock_run, mock_isfile, mock_open_fn, mock_run_async):
        """MR exists but has no PLAN.md section -> local state shown."""
        plan = _plan_with_hashes()
        mr_json = _mr_json(description='## Description\n\nJust a body, no plan.')

        output = await self._run_status(
            mock_run_async, mock_run, mock_isfile, mock_open_fn,
            plan_content=plan,
            glab_response=mr_json,
        )
        self.assertIn('!42', output)
        self.assertIn('synced', output)

    @patch('git_hooks_impl.entry_points.status.run_async', new_callable=AsyncMock)
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.isfile')
    @patch('git_hooks_impl.entry_points.status.run')
    async def test_no_diff_when_synced(self, mock_run, mock_isfile, mock_open_fn, mock_run_async):
        """Synced plan -> no diff block in output."""
        plan = _plan_with_hashes()
        mr_description = _wrap_plan_in_mr(plan)
        mr_json = _mr_json(description=mr_description)

        output = await self._run_status(
            mock_run_async, mock_run, mock_isfile, mock_open_fn,
            plan_content=plan,
            glab_response=mr_json,
        )
        self.assertNotIn('---', output)
        self.assertNotIn('+++', output)
        self.assertNotIn('@@', output)

    @patch('git_hooks_impl.entry_points.status.run_async', new_callable=AsyncMock)
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.isfile')
    @patch('git_hooks_impl.entry_points.status.run')
    async def test_no_diff_when_no_mr(self, mock_run, mock_isfile, mock_open_fn, mock_run_async):
        """No MR -> no diff block (nothing to compare against)."""
        original = '# [Title]\n\n## Context\n\nOriginal.\n'
        plan = _plan_with_hashes(original)
        local = plan.replace('Original.', 'Modified.')

        output = await self._run_status(
            mock_run_async, mock_run, mock_isfile, mock_open_fn,
            plan_content=local,
            glab_response='[]',
        )
        self.assertNotIn('---', output)
        self.assertNotIn('+++', output)

    @patch('git_hooks_impl.entry_points.status.run_async', new_callable=AsyncMock)
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.isfile')
    @patch('git_hooks_impl.entry_points.status.run')
    async def test_body_line_always_shown(self, mock_run, mock_isfile, mock_open_fn, mock_run_async):
        """Body line always visible (not just when different from Plan)."""
        plan = _plan_with_hashes()
        output = await self._run_status(
            mock_run_async, mock_run, mock_isfile, mock_open_fn,
            plan_content=plan,
            glab_response='[]',
        )
        self.assertIn('Body:', output)

    @patch('git_hooks_impl.entry_points.status.run_async', new_callable=AsyncMock)
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.isfile')
    @patch('git_hooks_impl.entry_points.status.run')
    async def test_mr_body_edited_on_gitlab(self, mock_run, mock_isfile, mock_open_fn, mock_run_async):
        """MR body edited on GitLab (body-hash mismatch) -> Body 'modified on MR'."""
        plan = _plan_with_hashes()
        mr_description = _wrap_plan_in_mr(plan)
        # Tamper the visible plan content mapped into the description body —
        # the description has no separate body text once a plan is present.
        mr_description = mr_description.replace('Some context here.', 'Manually edited body.')
        mr_json = _mr_json(description=mr_description)

        output = await self._run_status(
            mock_run_async, mock_run, mock_isfile, mock_open_fn,
            plan_content=plan,
            glab_response=mr_json,
        )
        body_line = [line for line in output.splitlines() if line.startswith('Body:')][0]
        self.assertIn('modified on MR', body_line)

    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.isfile')
    @patch('git_hooks_impl.entry_points.status.run')
    async def test_git_rev_parse_failure(self, mock_run, mock_isfile, mock_open_fn):
        """Git rev-parse fails -> warning, no crash."""
        mock_run.return_value = (128, '', 'fatal: not a git repo')
        with patch('sys.stderr'):
            await cmd_status()
        # No crash — graceful return after warning, no further git calls
        self.assertEqual(mock_run.call_count, 1)

    @patch('git_hooks_impl.entry_points.status.run_async', new_callable=AsyncMock)
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.isfile')
    @patch('git_hooks_impl.entry_points.status.run')
    async def test_multiple_mrs_shown_as_error(self, mock_run, mock_isfile, mock_open_fn, mock_run_async):
        """Multiple open MRs -> error message (ambiguous)."""
        plan = _plan_with_hashes()
        two_mrs = json.dumps([{'iid': 1}, {'iid': 2}])

        output = await self._run_status(
            mock_run_async, mock_run, mock_isfile, mock_open_fn,
            plan_content=plan,
            glab_response=two_mrs,
        )
        self.assertIn('multiple MRs', output)

    @patch('git_hooks_impl.entry_points.status.run_async', new_callable=AsyncMock)
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.isfile')
    @patch('git_hooks_impl.entry_points.status.run')
    async def test_unicode_in_diff_no_crash_on_windows(self, mock_run, mock_isfile,
                                                  mock_open_fn, mock_run_async):
        """Plan diff with Unicode arrows (→) -> no UnicodeEncodeError.

        Windows cp1252 console can't encode U+2192. cmd_status writes diff
        as UTF-8 to stdout.buffer, preserving all characters.
        """
        local_plan = _plan_with_hashes('# Title\n\n## Context\n\nNew 70%→80%.\n')
        mr_plan = _plan_with_hashes('# Title\n\n## Context\n\nOld 65%→72%.\n')
        mr_json = _mr_json(description=_wrap_plan_in_mr(mr_plan))

        mock_run.side_effect = [
            (0, 'feature/test\n', ''),              # git rev-parse
            (128, '', 'error: no upstream'),         # rev-parse upstream
            (0, 'abc1234 test commit\n', ''),        # git log master..HEAD
        ]
        mock_run_async.return_value = (0, mr_json, '')
        mock_isfile.return_value = True
        mock_open_fn.return_value.__enter__.return_value.read.return_value = local_plan


        # Simulate cp1252 text layer with an accessible binary buffer
        binary_buffer = io.BytesIO()
        text_layer = io.TextIOWrapper(binary_buffer, encoding='cp1252', errors='strict')

        with patch('sys.stdout', text_layer):
            await cmd_status()

        # UTF-8 diff bytes written to buffer — decode to verify arrows preserved
        raw_bytes = binary_buffer.getvalue()
        output = raw_bytes.decode('utf-8', errors='replace')

        # Arrow character preserved in UTF-8 output (not replaced with ?)
        self.assertIn('→', output)
        self.assertIn('65%→72%', output)
        self.assertIn('70%→80%', output)
