#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for git_hooks_impl.entry_points.commands.plan_summary.

run()'s only direct dependency is project_root(), mocked at the plan_summary
import location per the Main Mock Rule. The plan file itself is a real
tempfile — reading a file the test itself wrote is not a project dependency.
"""

import io
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from unittest.mock import patch

from git_hooks_impl.entry_points.commands import plan_summary

_PLAN_CONTENT = (
    'plan-hash: XYZ123\n'
    '## Section One\n'
    '\n'
    '- [x] done\n'
    '- [ ] pending\n'
    '### Sub\n'
    '\n'
    '## Decisions Log\n'
    '- decision one\n'
    '- decision two\n'
)


class TestPlanSummaryMissingFile(unittest.TestCase):
    """run(): no BRANCH_PLAN.md on disk -> error message, exit 1."""

    @patch('git_hooks_impl.entry_points.commands.plan_summary.project_root')
    def test_missing_plan_returns_1(self, mock_project_root):
        """Empty project root (no .ai/BRANCH_PLAN.md) -> ERR line, returns 1."""
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        mock_project_root.return_value = root
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = plan_summary.run([])
        self.assertEqual(result, 1)
        self.assertIn('ERR:', stdout.getvalue())
        self.assertIn('not found', stdout.getvalue())


class TestPlanSummaryCounts(unittest.TestCase):
    """run(): section, checkbox, hash, and Decisions Log counts on a known plan."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        os.makedirs(os.path.join(self.root, '.ai'))
        self.plan_path = os.path.join(self.root, '.ai', 'BRANCH_PLAN.md')
        with open(self.plan_path, 'w', encoding='utf-8') as f:
            f.write(_PLAN_CONTENT)

    @patch('git_hooks_impl.entry_points.commands.plan_summary.project_root')
    def test_section_and_checkbox_counts(self, mock_project_root):
        """3 headings (## / ###), 2 checkboxes (1 done, 1 pending) -> counted correctly."""
        mock_project_root.return_value = self.root
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = plan_summary.run([])
        output = stdout.getvalue()
        self.assertIn('Sections: 3', output)
        self.assertIn('Checkboxes: 2 total (1 done, 1 pending)', output)
        self.assertEqual(result, 0)

    @patch('git_hooks_impl.entry_points.commands.plan_summary.project_root')
    def test_meta_hash_extracted_from_first_lines(self, mock_project_root):
        """plan-hash line within the first 5 lines -> its value is printed."""
        mock_project_root.return_value = self.root
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            plan_summary.run([])
        self.assertIn('Meta hash: XYZ123', stdout.getvalue())

    @patch('git_hooks_impl.entry_points.commands.plan_summary.project_root')
    def test_missing_hash_reports_none(self, mock_project_root):
        """No plan-hash line anywhere -> "Meta hash: none"."""
        with open(self.plan_path, 'w', encoding='utf-8') as f:
            f.write('## Section One\n\ncontent\n')
        mock_project_root.return_value = self.root
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            plan_summary.run([])
        self.assertIn('Meta hash: none', stdout.getvalue())

    @patch('git_hooks_impl.entry_points.commands.plan_summary.project_root')
    def test_decisions_log_entry_count(self, mock_project_root):
        """2 '- ' lines under '## Decisions Log' -> counted, heading line excluded."""
        mock_project_root.return_value = self.root
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            plan_summary.run([])
        output = stdout.getvalue()
        self.assertIn('=== Decisions Log entries ===\n2', output)

    @patch('git_hooks_impl.entry_points.commands.plan_summary.project_root')
    def test_no_decisions_log_section_reports_not_found(self, mock_project_root):
        """No '## Decisions Log' heading anywhere -> explicit not-found message."""
        with open(self.plan_path, 'w', encoding='utf-8') as f:
            f.write('## Section One\n\ncontent\n')
        mock_project_root.return_value = self.root
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            plan_summary.run([])
        self.assertIn('Decisions Log section not found', stdout.getvalue())


class TestPlanSummaryTimestamp(unittest.TestCase):
    """run(): the "Last modified" line is a sane, parseable timestamp.

    mtime is formatted as ISO with a space separator; this verifies the
    value round-trips through datetime.fromisoformat().
    """

    @patch('git_hooks_impl.entry_points.commands.plan_summary.project_root')
    def test_last_modified_line_is_parseable_isoformat(self, mock_project_root):
        """"Last modified: <ts>" -> <ts> parses back into a datetime, close to now."""
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        os.makedirs(os.path.join(root, '.ai'))
        with open(os.path.join(root, '.ai', 'BRANCH_PLAN.md'), 'w', encoding='utf-8') as f:
            f.write(_PLAN_CONTENT)
        mock_project_root.return_value = root

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            plan_summary.run([])
        lines = stdout.getvalue().splitlines()
        timestamp_line = next(line for line in lines if line.startswith('Last modified: '))
        timestamp_str = timestamp_line[len('Last modified: '):]

        parsed = datetime.fromisoformat(timestamp_str)
        self.assertLess(abs((datetime.now() - parsed).total_seconds()), 60)


if __name__ == '__main__':
    unittest.main()
