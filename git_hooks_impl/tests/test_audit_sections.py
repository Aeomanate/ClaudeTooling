#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for git_hooks_impl.entry_points.commands.audit_sections.

_find_empty_sections() has no external dependencies — it is a pure function
over a list of lines, tested directly. run()'s only direct dependency is
project_root(), mocked at the audit_sections import location per the Main
Mock Rule.
"""

import io
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from git_hooks_impl.entry_points.commands import audit_sections


class TestFindEmptySectionsHeadingFollowedByHeading(unittest.TestCase):
    """A heading immediately followed by another heading has no content -> EMPTY."""

    def test_two_consecutive_headings_are_both_flagged_empty(self):
        """'## A' then '## B' with nothing else -> both flagged (B empty at EOF too)."""
        lines = ['## A\n', '## B\n']
        result = audit_sections._find_empty_sections(lines)
        self.assertEqual(result, ['1: EMPTY — ## A', '2: EMPTY — ## B'])


class TestFindEmptySectionsHeadingFollowedByContent(unittest.TestCase):
    """A heading followed by blank lines then real content is NOT empty."""

    def test_heading_blank_then_content_is_not_flagged(self):
        """'## A', blank line, 'content here' -> no EMPTY entry for A."""
        lines = ['## A\n', '\n', 'content here\n']
        result = audit_sections._find_empty_sections(lines)
        self.assertEqual(result, [])

    def test_heading_direct_content_is_not_flagged(self):
        """'## A' immediately followed by content, no blank line -> not empty."""
        lines = ['## A\n', 'content here\n']
        result = audit_sections._find_empty_sections(lines)
        self.assertEqual(result, [])


class TestFindEmptySectionsBlankOnlyBetweenHeadings(unittest.TestCase):
    """Blank lines alone do not count as section content.

    _CONTENT_RE (r'^[^ \\t#]') never matches an empty string, and a blank
    line strips down to "", so it never clears prev_heading.
    """

    def test_blank_line_between_two_headings_flags_both(self):
        """'## A', blank line, '## B' -> both are flagged empty."""
        lines = ['## A\n', '\n', '## B\n']
        result = audit_sections._find_empty_sections(lines)
        self.assertEqual(result, ['2: EMPTY — ## A', '3: EMPTY — ## B'])


class TestAuditSectionsRun(unittest.TestCase):
    """run(): end-to-end section listing, count, and empty-section report."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        os.makedirs(os.path.join(self.root, '.ai'))
        self.plan_path = os.path.join(self.root, '.ai', 'BRANCH_PLAN.md')

    @patch('git_hooks_impl.entry_points.commands.audit_sections.project_root')
    def test_missing_plan_returns_1(self, mock_project_root):
        """No .ai/BRANCH_PLAN.md -> ERR line, returns 1."""
        mock_project_root.return_value = self.root
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = audit_sections.run([])
        self.assertEqual(result, 1)
        self.assertIn('ERR:', stdout.getvalue())

    @patch('git_hooks_impl.entry_points.commands.audit_sections.project_root')
    def test_lists_headings_with_line_numbers_and_count(self, mock_project_root):
        """Two headings -> both listed with line numbers, count printed as 2."""
        with open(self.plan_path, 'w', encoding='utf-8') as f:
            f.write('## Section One\n\ncontent\n\n### Sub\n\nmore content\n')
        mock_project_root.return_value = self.root
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = audit_sections.run([])
        output = stdout.getvalue()
        self.assertIn('1:## Section One', output)
        self.assertIn('5:### Sub', output)
        self.assertIn('=== Section count ===\n2', output)
        self.assertEqual(result, 0)


if __name__ == '__main__':
    unittest.main()
