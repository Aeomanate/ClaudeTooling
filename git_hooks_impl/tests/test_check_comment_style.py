#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for check_comment_style.py (STYLE-8 mechanical checks)."""
import unittest
from unittest.mock import MagicMock, patch

from git_hooks_impl.entry_points.commands import check_comment_style


def _diff(file_path, added_lines, start_line=10):
    """Build a minimal unified diff adding `added_lines` to `file_path`."""
    header = (
        f'diff --git a/{file_path} b/{file_path}\n'
        f'--- a/{file_path}\n'
        f'+++ b/{file_path}\n'
        f'@@ -{start_line},0 +{start_line},{len(added_lines)} @@\n'
    )
    body = ''.join(f'+{line}\n' for line in added_lines)
    return header + body


class TestFindRegisterViolations(unittest.TestCase):
    def test_first_person_plural_flagged(self):
        """Comment says 'we skip this' -> flagged as banned register"""
        diff_text = _diff('module.py', ['# we skip this because it is cheap'])
        violations = check_comment_style.find_register_violations(diff_text)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0][0], 'module.py')

    def test_filler_opener_flagged(self):
        """Comment opens with 'Note that' -> flagged as filler opener"""
        diff_text = _diff('module.py', ['# Note that this branch is rare'])
        violations = check_comment_style.find_register_violations(diff_text)
        self.assertEqual(len(violations), 1)

    def test_clean_comment_not_flagged(self):
        """Plain non-obvious-constraint comment -> no violation"""
        diff_text = _diff('module.py', ['# Windows requires Developer Mode for symlinks'])
        violations = check_comment_style.find_register_violations(diff_text)
        self.assertEqual(violations, [])

    def test_non_comment_line_ignored(self):
        """Added code line (not a comment) -> never scanned for register"""
        diff_text = _diff('module.py', ['our_value = compute()'])
        violations = check_comment_style.find_register_violations(diff_text)
        self.assertEqual(violations, [])


class TestFindBudgetViolations(unittest.TestCase):
    def test_block_within_cap_not_flagged(self):
        """4-line contiguous comment block -> within cap, no violation"""
        diff_text = _diff('module.py', ['# line one', '# line two', '# line three', '# line four'])
        violations = check_comment_style.find_budget_violations(diff_text)
        self.assertEqual(violations, [])

    def test_block_over_cap_flagged(self):
        """5-line contiguous comment block -> exceeds 4-line cap"""
        diff_text = _diff('module.py', [f'# line {i}' for i in range(5)])
        violations = check_comment_style.find_budget_violations(diff_text)
        self.assertEqual(len(violations), 1)

    def test_link_directory_recursive_anti_pattern_flagged(self):
        """STYLE-8's worked anti-pattern (6-line guard comment) -> exceeds cap"""
        anti_pattern_lines = [
            'target_subdir may already be a directory-level symlink resolving',
            'into this same source subtree (e.g. a whole skill symlinked as one',
            'unit). Walking into it would compute per-file target paths that',
            'physically resolve back into source_dir: os.remove() would delete',
            'the real source file and os.symlink() would recreate it pointing',
            "at itself. Skip the whole subtree — it's already linked.",
        ]
        diff_text = _diff('setup/_link_helpers.py', [f'# {line}' for line in anti_pattern_lines])
        violations = check_comment_style.find_budget_violations(diff_text)
        self.assertEqual(len(violations), 1)


class TestMain(unittest.TestCase):
    def test_clean_diff_exits_zero(self):
        """Clean diff -> PASS, exit 0"""
        with patch.object(
            check_comment_style, 'get_diff',
            return_value=_diff('module.py', ['# fine comment']),
        ):
            self.assertEqual(check_comment_style.main([]), 0)

    def test_violation_exits_nonzero(self):
        """Diff with a banned-register comment -> exit 1"""
        with patch.object(
            check_comment_style, 'get_diff',
            return_value=_diff('module.py', ['# we handle this case']),
        ):
            self.assertEqual(check_comment_style.main([]), 1)

    def test_default_uses_staged_diff(self):
        """No argv -> git diff --cached"""
        with patch.object(
            check_comment_style.subprocess, 'run',
            return_value=MagicMock(stdout=''),
        ) as mock_run:
            check_comment_style.get_diff(None)
        mock_run.assert_called_once_with(
            ['git', 'diff', '--cached'], capture_output=True, text=True, check=True,
        )

    def test_spec_arg_uses_git_diff_spec(self):
        """'HEAD~5' argv -> git diff HEAD~5"""
        with patch.object(
            check_comment_style.subprocess, 'run',
            return_value=MagicMock(stdout=''),
        ) as mock_run:
            check_comment_style.get_diff('HEAD~5')
        mock_run.assert_called_once_with(
            ['git', 'diff', 'HEAD~5'], capture_output=True, text=True, check=True,
        )

    def test_help_flag_returns_0_without_touching_git(self):
        """--help -> exit 0, no diff ever fetched"""
        with patch.object(check_comment_style, 'get_diff') as mock_get_diff:
            self.assertEqual(check_comment_style.main(['--help']), 0)
            mock_get_diff.assert_not_called()


if __name__ == '__main__':
    unittest.main()
