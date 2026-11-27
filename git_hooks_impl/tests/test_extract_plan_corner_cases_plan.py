#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Corner-case tests for extract-plan: local-vs-MR plan overwrite decisions, the
nag-file touch helper, branch-title edge cases, module path resolution, and
the force=True existing-plan overwrite prompt gate.

Run:  python -m unittest discover -s .git-hooks/hooks/tests -t .git-hooks -p "test_*.py" -v
"""

import os
import tempfile
import unittest
from unittest.mock import patch

from git_hooks_impl.entry_points.extract_plan import (
    _MODULE_DIR,
    _TEMPLATE_PATH,
    _handle_existing_plan,
    _should_overwrite_plan,
    _title_from_branch,
    _touch_nag,
)
from git_hooks_impl.plan.generator import _PROMPTS_DIR

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
#  _should_overwrite_plan — pure decision logic
# ---------------------------------------------------------------------------

class TestShouldOverwritePlan(unittest.TestCase):
    """Verify _should_overwrite_plan() returns correct decision strings."""

    def test_no_local_file_returns_no_local(self):
        """PLAN.md doesn't exist on disk -> 'no_local'.

        Function under test: _should_overwrite_plan()
        """
        with patch('git_hooks_impl.entry_points.extract_plan.PLAN_FILE', '/nonexistent/PLAN.md'):
            result = _should_overwrite_plan('# MR plan content\n')
        self.assertEqual(result, 'no_local')

    def test_stub_file_returns_no_local(self):
        """Local PLAN.md < 100 chars (stub) -> 'no_local'.

        Files under _MIN_PLAN_SIZE are treated as empty stubs.

        Function under test: _should_overwrite_plan()
        """
        with tempfile.TemporaryDirectory() as tmp:
            plan_file = os.path.join(tmp, 'PLAN.md')
            with open(plan_file, 'w') as f:
                f.write('# stub\n')  # 8 chars, well under 100
            with patch('git_hooks_impl.entry_points.extract_plan.PLAN_FILE', plan_file):
                result = _should_overwrite_plan('# MR content\n')
        self.assertEqual(result, 'no_local')

    @patch('git_hooks_impl.entry_points.extract_plan.plan_was_edited_on_mr', return_value=False)
    def test_hash_match_returns_hash_match(self, mock_edited):
        """MR hash unchanged since push + local has real content -> 'hash_match'.

        plan_was_edited_on_mr returns False -> no MR edit detected.

        Function under test: _should_overwrite_plan()
        """
        local_content = '# Plan\nReal content here\n' + 'x' * 100
        with tempfile.TemporaryDirectory() as tmp:
            plan_file = os.path.join(tmp, 'PLAN.md')
            with open(plan_file, 'w') as f:
                f.write(local_content)
            with patch('git_hooks_impl.entry_points.extract_plan.PLAN_FILE', plan_file):
                result = _should_overwrite_plan('# MR content\n')
        self.assertEqual(result, 'hash_match')

    @patch('git_hooks_impl.entry_points.extract_plan.plan_was_edited_on_mr', return_value=True)
    def test_identical_content_returns_identical(self, mock_edited):
        """MR edited (hash mismatch) but content identical -> 'identical'.

        strip_meta(local) == strip_meta(remote) despite different hashes.

        Function under test: _should_overwrite_plan()
        """
        content = '# Plan\nSame content\n' + 'x' * 100
        with tempfile.TemporaryDirectory() as tmp:
            plan_file = os.path.join(tmp, 'PLAN.md')
            with open(plan_file, 'w') as f:
                f.write(content)
            with patch('git_hooks_impl.entry_points.extract_plan.PLAN_FILE', plan_file):
                result = _should_overwrite_plan(content)
        self.assertEqual(result, 'identical')

    @patch('git_hooks_impl.entry_points.extract_plan.plan_was_edited_on_mr', return_value=True)
    def test_different_content_returns_conflict(self, mock_edited):
        """MR edited + local differs from remote -> 'conflict'.

        Both sides have real content but they differ.

        Function under test: _should_overwrite_plan()
        """
        local_content = '# Plan\nLocal version\n' + 'x' * 100
        remote_content = '# Plan\nRemote version\n' + 'y' * 100
        with tempfile.TemporaryDirectory() as tmp:
            plan_file = os.path.join(tmp, 'PLAN.md')
            with open(plan_file, 'w') as f:
                f.write(local_content)
            with patch('git_hooks_impl.entry_points.extract_plan.PLAN_FILE', plan_file):
                result = _should_overwrite_plan(remote_content)
        self.assertEqual(result, 'conflict')


# ---------------------------------------------------------------------------
#  _touch_nag — creates/updates the nag cooldown file
# ---------------------------------------------------------------------------

class TestTouchNag(unittest.TestCase):
    """Cover _touch_nag: creates the nag cooldown file in .ai/."""

    def test_creates_nag_file(self):
        """No nag file exists -> creates it with empty content.

        Lines 89-94: makedirs + open(..., 'w') + write('').
        After calling _touch_nag, the file should exist on disk.

        Function under test: _touch_nag()
        """
        with tempfile.TemporaryDirectory() as tmp:
            nag_path = os.path.join(tmp, 'tool_hint_setup_suppressor')
            with patch('git_hooks_impl.entry_points.extract_plan._NAG_FILE', nag_path):
                _touch_nag()
            self.assertTrue(os.path.isfile(nag_path))
            with open(nag_path) as f:
                content = f.read()
            self.assertEqual(content, '')

    def test_updates_existing_nag_file(self):
        """Nag file already exists -> overwrites it (resets mtime).

        Re-calling _touch_nag on an existing file should succeed and
        update the file modification time.

        Function under test: _touch_nag()
        """
        with tempfile.TemporaryDirectory() as tmp:
            nag_path = os.path.join(tmp, 'tool_hint_setup_suppressor')
            # Create initial file
            with open(nag_path, 'w') as f:
                f.write('old')
            with patch('git_hooks_impl.entry_points.extract_plan._NAG_FILE', nag_path):
                _touch_nag()
            with open(nag_path) as f:
                content = f.read()
            # Content should be empty (overwritten)
            self.assertEqual(content, '')

    def test_oserror_silenced(self):
        """OSError during file creation -> silently caught, no crash.

        Lines 93-94: except OSError: pass.
        Best-effort nag file should never break the main flow.

        Function under test: _touch_nag()
        """
        with patch('git_hooks_impl.entry_points.extract_plan.os.makedirs', side_effect=OSError('disk full')):
            _touch_nag()  # should not raise


# ---------------------------------------------------------------------------
#  _title_from_branch — edge case: empty title after stripping
# ---------------------------------------------------------------------------

class TestTitleFromBranchEdgeCases(unittest.TestCase):
    """Cover _title_from_branch edge cases: empty title fallback to tail."""

    def test_ticket_prefix_only_branch_returns_tail(self):
        """Branch tail is ONLY a ticket prefix (e.g. 'PROJECTNAME-1234') -> stripped to empty.

        Line 185: if not title: return tail.
        When the regex strips the entire tail, fall back to the raw tail.

        Function under test: _title_from_branch()
        """
        # 'PROJECTNAME-1234_' would be stripped to '' by the regex
        result = _title_from_branch('productname/fixes/PROJECTNAME-1234_', '', '')
        result = _title_from_branch('productname/fixes/PROJECTNAME-1234_', '', '')
        # Should return the tail as-is since title becomes empty
        self.assertEqual(result, 'PROJECTNAME-1234_')

    def test_single_segment_branch(self):
        """Branch with no slashes (e.g. 'mybranch') -> rsplit gives same string.

        tail = 'mybranch', no ticket prefix -> title = 'Mybranch'.

        Function under test: _title_from_branch()
        """
        result = _title_from_branch('mybranch', '', '')
        self.assertEqual(result, 'Mybranch')

    def test_ticket_no_summary_no_tail_content(self):
        """Ticket present but tail is only ticket prefix -> '[PROJECTNAME-1] PROJECTNAME-1_'.

        Line 183: jira_ticket present but title stripped to empty
        -> f'[{jira_ticket}]' (no trailing title).

        Function under test: _title_from_branch()
        """
        result = _title_from_branch('productname/fixes/PROJECTNAME-1_', 'PROJECTNAME-1', '')
        result = _title_from_branch('productname/fixes/PROJECTNAME-1_', 'PROJECTNAME-1', '')
        # Title is empty after stripping -> returns '[PROJECTNAME-1]'
        self.assertEqual(result, '[PROJECTNAME-1]')


# ---------------------------------------------------------------------------
#  Path resolution — regression for commit 4953f9f0c8
# ---------------------------------------------------------------------------

class TestPathResolution(unittest.TestCase):
    """Regression: _MODULE_DIR must go 2 levels up from entry_points/ to git_hooks_impl/.

    Before the fix, _MODULE_DIR pointed to entry_points/ instead of git_hooks_impl/,
    causing _TEMPLATE_PATH and _PROMPTS_DIR to resolve to non-existent paths.
    """

    def test_module_dir_points_to_git_hooks_impl_directory(self):
        """_MODULE_DIR ends with 'git_hooks_impl' (not 'entry_points').

        extract_plan.py lives in git_hooks_impl/entry_points/ so dirname(dirname(__file__))
        must land on git_hooks_impl/.

        Function under test: _MODULE_DIR constant (module-level)
        """
        self.assertTrue(
            _MODULE_DIR.replace('\\', '/').endswith('/git_hooks_impl')
            or os.path.basename(_MODULE_DIR) == 'git_hooks_impl',
            f"_MODULE_DIR should end with 'git_hooks_impl', got: {_MODULE_DIR}")

    def test_template_path_exists(self):
        """_TEMPLATE_PATH resolves to an existing file.

        Function under test: _TEMPLATE_PATH constant (module-level)
        """
        self.assertTrue(
            os.path.isfile(_TEMPLATE_PATH),
            f'_TEMPLATE_PATH should be an existing file, got: {_TEMPLATE_PATH}')

    def test_prompts_dir_exists(self):
        """_PROMPTS_DIR resolves to an existing directory.

        Function under test: _PROMPTS_DIR constant in git_hooks_impl.plan.generator
        """
        self.assertTrue(
            os.path.isdir(_PROMPTS_DIR),
            f'_PROMPTS_DIR should be an existing directory, got: {_PROMPTS_DIR}')

    def test_module_dir_is_not_entry_points(self):
        """_MODULE_DIR must NOT be entry_points/ (the pre-fix bug).

        Before the fix, only one dirname() was applied, landing on
        entry_points/ instead of hooks/.

        Function under test: _MODULE_DIR constant (module-level)
        """
        self.assertNotEqual(
            os.path.basename(_MODULE_DIR), 'entry_points',
            '_MODULE_DIR should not point to entry_points/ directory')

    def test_prompts_dir_contains_plan_gen_rules(self):
        """_PROMPTS_DIR should contain plan_generation_rules.md.

        Function under test: _PROMPTS_DIR constant in git_hooks_impl.plan.generator
        """
        rules_file = os.path.join(_PROMPTS_DIR, 'plan_generation_rules.md')
        self.assertTrue(
            os.path.isfile(rules_file),
            f'plan_generation_rules.md should exist in _PROMPTS_DIR: {_PROMPTS_DIR}')


# ---------------------------------------------------------------------------
#  _handle_existing_plan — force=True branch with user approval prompt
# ---------------------------------------------------------------------------


class TestHandleExistingPlanForce(unittest.TestCase):
    """Tests for _handle_existing_plan() force=True path with the prompt gate.

    force=True bypasses hash check but now asks the user before overwriting
    when the content actually differs.
    """

    def test_force_content_differs_user_accepts_overwrites(self):
        """force=True, content differs, user answers yes -> plan is overwritten.

        prompt_yn returns True (user accepts), so _write_plan is called with
        the MR content.

        Function under test: _handle_existing_plan()
        """
        local_text = '# Local Plan\n' + 'a' * 200
        remote_text = '# Remote Plan\n' + 'b' * 200
        with tempfile.TemporaryDirectory() as tmp:
            plan_file = os.path.join(tmp, 'PLAN.md')
            with open(plan_file, 'w') as f:
                f.write(local_text)
            with patch('git_hooks_impl.entry_points.extract_plan.PLAN_FILE', plan_file), \
                 patch('git_hooks_impl.entry_points.extract_plan._print_diff'), \
                 patch('git_hooks_impl.entry_points.extract_plan.prompt_yn', return_value=True), \
                 patch('git_hooks_impl.entry_points.extract_plan.sys.stdin') as mock_stdin, \
                 patch('git_hooks_impl.entry_points.extract_plan._write_plan') as mock_write:
                mock_stdin.isatty.return_value = True
                result = _handle_existing_plan(remote_text, 99, 'feature/x', force=True)
        self.assertEqual(result, 0)
        mock_write.assert_called_once_with(remote_text)

    def test_force_content_differs_user_declines_keeps_local(self):
        """force=True, content differs, user answers no -> plan is NOT overwritten.

        prompt_yn returns False (user declines), so _write_plan is NOT called
        and the function returns 0 early.

        Function under test: _handle_existing_plan()
        """
        local_text = '# Local Plan\n' + 'a' * 200
        remote_text = '# Remote Plan\n' + 'b' * 200
        with tempfile.TemporaryDirectory() as tmp:
            plan_file = os.path.join(tmp, 'PLAN.md')
            with open(plan_file, 'w') as f:
                f.write(local_text)
            with patch('git_hooks_impl.entry_points.extract_plan.PLAN_FILE', plan_file), \
                 patch('git_hooks_impl.entry_points.extract_plan._print_diff'), \
                 patch('git_hooks_impl.entry_points.extract_plan.prompt_yn', return_value=False), \
                 patch('git_hooks_impl.entry_points.extract_plan.sys.stdin') as mock_stdin, \
                 patch('git_hooks_impl.entry_points.extract_plan._write_plan') as mock_write:
                mock_stdin.isatty.return_value = True
                result = _handle_existing_plan(remote_text, 99, 'feature/x', force=True)
        self.assertEqual(result, 0)
        mock_write.assert_not_called()

    def test_force_content_differs_non_interactive_skips_prompt_and_overwrites(self):
        """force=True, non-interactive (isatty=False), content differs -> overwrites without prompt.

        In CI or non-interactive shells, prompt_yn is never called and
        the plan is written unconditionally.

        Function under test: _handle_existing_plan()
        """
        local_text = '# Local Plan\n' + 'a' * 200
        remote_text = '# Remote Plan\n' + 'b' * 200
        with tempfile.TemporaryDirectory() as tmp:
            plan_file = os.path.join(tmp, 'PLAN.md')
            with open(plan_file, 'w') as f:
                f.write(local_text)
            with patch('git_hooks_impl.entry_points.extract_plan.PLAN_FILE', plan_file), \
                 patch('git_hooks_impl.entry_points.extract_plan._print_diff'), \
                 patch('git_hooks_impl.entry_points.extract_plan.prompt_yn') as mock_prompt, \
                 patch('git_hooks_impl.entry_points.extract_plan.sys.stdin') as mock_stdin, \
                 patch('git_hooks_impl.entry_points.extract_plan._write_plan') as mock_write:
                mock_stdin.isatty.return_value = False
                result = _handle_existing_plan(remote_text, 99, 'feature/x', force=True)
        self.assertEqual(result, 0)
        mock_prompt.assert_not_called()
        mock_write.assert_called_once_with(remote_text)

    def test_force_content_identical_skips_prompt_and_overwrites(self):
        """force=True, metadata-only diff (same content body) -> no prompt, writes plan.

        When strip_meta(local) == strip_meta(remote), the diff branch is not
        entered, so prompt_yn is never called and _write_plan is still called.

        Function under test: _handle_existing_plan()
        """
        content = '# Plan\nSame content\n' + 'x' * 200
        with tempfile.TemporaryDirectory() as tmp:
            plan_file = os.path.join(tmp, 'PLAN.md')
            with open(plan_file, 'w') as f:
                f.write(content)
            with patch('git_hooks_impl.entry_points.extract_plan.PLAN_FILE', plan_file), \
                 patch('git_hooks_impl.entry_points.extract_plan.prompt_yn') as mock_prompt, \
                 patch('git_hooks_impl.entry_points.extract_plan.sys.stdin') as mock_stdin, \
                 patch('git_hooks_impl.entry_points.extract_plan._write_plan') as mock_write:
                mock_stdin.isatty.return_value = True
                result = _handle_existing_plan(content, 99, 'feature/x', force=True)
        self.assertEqual(result, 0)
        mock_prompt.assert_not_called()
        mock_write.assert_called_once()

    def test_force_no_local_file_overwrites_without_prompt(self):
        """force=True, no local PLAN.md -> no comparison, no prompt, write plan.

        When PLAN.md doesn't exist, the if-block reading local content is
        skipped entirely so prompt_yn is never reached.

        Function under test: _handle_existing_plan()
        """
        remote_text = '# Remote Plan\n' + 'b' * 200
        with patch('git_hooks_impl.entry_points.extract_plan.PLAN_FILE', '/nonexistent/PLAN.md'), \
             patch('git_hooks_impl.entry_points.extract_plan.prompt_yn') as mock_prompt, \
             patch('git_hooks_impl.entry_points.extract_plan.sys.stdin') as mock_stdin, \
             patch('git_hooks_impl.entry_points.extract_plan._write_plan') as mock_write:
            mock_stdin.isatty.return_value = True
            result = _handle_existing_plan(remote_text, 99, 'feature/x', force=True)
        self.assertEqual(result, 0)
        mock_prompt.assert_not_called()
        mock_write.assert_called_once_with(remote_text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
