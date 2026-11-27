#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for git_hooks_impl.entry_points.commands.check_stale_refs.

run()'s only direct dependency is project_root(), mocked at the
check_stale_refs import location per the Main Mock Rule. open() operates on
a real file inside a tempdir fixture.
"""

import io
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from git_hooks_impl.entry_points.commands import check_stale_refs


class TestCheckStaleRefsRun(unittest.TestCase):
    """run(): plan lint over BRANCH_PLAN.md for bare links, cross-dir refs,
    and optional custom patterns.
    """

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        os.makedirs(os.path.join(self.root, '.ai'))
        self.plan_path = os.path.join(self.root, '.ai', 'BRANCH_PLAN.md')

    def _write_plan(self, text):
        with open(self.plan_path, 'w', encoding='utf-8') as f:
            f.write(text)

    @patch('git_hooks_impl.entry_points.commands.check_stale_refs.project_root')
    def test_missing_plan_returns_1(self, mock_project_root):
        """No .ai/BRANCH_PLAN.md -> ERR line, returns 1."""
        mock_project_root.return_value = self.root
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = check_stale_refs.run([])
        self.assertIn('ERR:', stdout.getvalue())
        self.assertEqual(result, 1)

    @patch('git_hooks_impl.entry_points.commands.check_stale_refs.project_root')
    def test_no_issues_reports_all_clean_and_returns_0(self, mock_project_root):
        """No bare links, no cross-dir refs -> ALL CLEAN, returns 0."""
        self._write_plan('## Plan\nNormal text with [a link](./file.md).\n')
        mock_project_root.return_value = self.root
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = check_stale_refs.run([])
        self.assertIn('=== ALL CLEAN ===', stdout.getvalue())
        self.assertEqual(result, 0)

    @patch('git_hooks_impl.entry_points.commands.check_stale_refs.project_root')
    def test_bare_filename_link_is_flagged_and_returns_1(self, mock_project_root):
        """[file.md](...) bare link text -> flagged under its section, returns 1."""
        self._write_plan('## Plan\nSee [notes.md](path/to/notes.md).\n')
        mock_project_root.return_value = self.root
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = check_stale_refs.run([])
        output = stdout.getvalue()
        self.assertIn('Bare filename link texts', output)
        self.assertIn('notes.md', output)
        self.assertEqual(result, 1)

    @patch('git_hooks_impl.entry_points.commands.check_stale_refs.project_root')
    def test_cross_directory_reference_is_flagged_and_returns_1(self, mock_project_root):
        """](../ cross-directory reference -> flagged, returns 1."""
        self._write_plan('## Plan\nSee [name](../other/file.md).\n')
        mock_project_root.return_value = self.root
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = check_stale_refs.run([])
        output = stdout.getvalue()
        self.assertIn('Cross-directory ../ references', output)
        self.assertIn('../other/file.md', output)
        self.assertEqual(result, 1)

    @patch('git_hooks_impl.entry_points.commands.check_stale_refs.project_root')
    def test_decisions_log_section_is_excluded_from_structural_checks(
        self, mock_project_root
    ):
        """A bare link placed after '## Decisions Log' is append-only history
        and is not scanned.
        """
        self._write_plan(
            '## Plan\nActive text.\n## Decisions Log\nSee [old.md](x/old.md).\n'
        )
        mock_project_root.return_value = self.root
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = check_stale_refs.run([])
        self.assertIn('=== ALL CLEAN ===', stdout.getvalue())
        self.assertEqual(result, 0)

    @patch('git_hooks_impl.entry_points.commands.check_stale_refs.project_root')
    def test_custom_pattern_matches_via_regex_character_class_not_substring(
        self, mock_project_root
    ):
        """Custom pattern 'to[o0]ling-old' matches a line containing
        'TOOLING-OLD' case-insensitively. A plain substring search for the
        literal pattern text (with brackets) would never match this line —
        only compiling it as a regex character class does.
        """
        self._write_plan('## Plan\nSee the TOOLING-OLD subsystem docs.\n')
        mock_project_root.return_value = self.root
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = check_stale_refs.run(['to[o0]ling-old'])
        output = stdout.getvalue()
        self.assertIn("Custom: 'to[o0]ling-old'", output)
        self.assertIn('TOOLING-OLD subsystem docs', output)
        self.assertEqual(result, 1)

    @patch('git_hooks_impl.entry_points.commands.check_stale_refs.project_root')
    def test_custom_pattern_with_no_match_reports_clean(self, mock_project_root):
        """Custom pattern absent from the active plan text -> CLEAN for that check."""
        self._write_plan('## Plan\nNothing relevant here.\n')
        mock_project_root.return_value = self.root
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = check_stale_refs.run(['unrelated-pattern'])
        self.assertIn('=== ALL CLEAN ===', stdout.getvalue())
        self.assertEqual(result, 0)


if __name__ == '__main__':
    unittest.main()
