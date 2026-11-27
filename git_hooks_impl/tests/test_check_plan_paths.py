#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for git_hooks_impl.entry_points.commands.check_plan_paths.

_is_checkable() has no external dependencies — it is a pure function over a
string, tested directly. run()'s only direct dependency is project_root(),
mocked at the check_plan_paths import location per the Main Mock Rule.
os.path.exists() and open() operate on real files inside a tempdir fixture.
"""

import io
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from git_hooks_impl.entry_points.commands import check_plan_paths


class TestIsCheckableRejectsNonPaths(unittest.TestCase):
    """_is_checkable(): URLs, placeholders, and non-project paths are excluded."""

    def test_url_is_rejected(self):
        """http(s):// path -> not checkable."""
        self.assertFalse(check_plan_paths._is_checkable('https://example.com/x'))

    def test_placeholder_braces_are_rejected(self):
        """Path containing {placeholder} -> not checkable."""
        self.assertFalse(check_plan_paths._is_checkable('docs/{name}.md'))

    def test_path_with_space_is_rejected(self):
        """Path containing a literal space -> not checkable."""
        self.assertFalse(check_plan_paths._is_checkable('docs/some file.md'))

    def test_absolute_unix_style_path_is_rejected(self):
        """Path starting with /<lowercase letter> -> not checkable."""
        self.assertFalse(check_plan_paths._is_checkable('/usr/local/bin'))

    def test_ai_cache_path_is_rejected(self):
        """Path under .ai/cache/ -> not checkable."""
        self.assertFalse(check_plan_paths._is_checkable('.ai/cache/branch/x.md'))

    def test_path_with_no_recognized_prefix_is_rejected(self):
        """Path not starting with any of the accepted prefixes -> not checkable."""
        self.assertFalse(check_plan_paths._is_checkable('random/path.md'))


class TestIsCheckableAcceptsProjectPaths(unittest.TestCase):
    """_is_checkable(): project-relative paths with accepted prefixes pass."""

    def test_dot_prefixed_path_is_accepted(self):
        """./relative/path.md -> checkable."""
        self.assertTrue(check_plan_paths._is_checkable('./scripts/run.sh'))

    def test_tools_prefixed_path_is_accepted(self):
        """tools/... -> checkable."""
        self.assertTrue(check_plan_paths._is_checkable('tools/build.py'))

    def test_tests_prefixed_path_is_accepted(self):
        """tests/... -> checkable."""
        self.assertTrue(check_plan_paths._is_checkable('tests/test_x.py'))


class TestCheckPlanPathsRun(unittest.TestCase):
    """run(): checks BRANCH_PLAN.md paths against the filesystem."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        os.makedirs(os.path.join(self.root, '.ai'))
        self.plan_path = os.path.join(self.root, '.ai', 'BRANCH_PLAN.md')

    @patch('git_hooks_impl.entry_points.commands.check_plan_paths.project_root')
    def test_missing_plan_returns_1(self, mock_project_root):
        """No .ai/BRANCH_PLAN.md -> ERR line, returns 1."""
        mock_project_root.return_value = self.root
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = check_plan_paths.run([])
        self.assertIn('ERR:', stdout.getvalue())
        self.assertEqual(result, 1)

    @patch('git_hooks_impl.entry_points.commands.check_plan_paths.project_root')
    def test_all_referenced_paths_exist_returns_0(self, mock_project_root):
        """Plan references a real file via backticks -> 0 missing, returns 0."""
        os.makedirs(os.path.join(self.root, 'tools'))
        with open(os.path.join(self.root, 'tools', 'build.py'), 'w') as f:
            f.write('# real file\n')
        with open(self.plan_path, 'w', encoding='utf-8') as f:
            f.write('See `tools/build.py` for details.\n')
        mock_project_root.return_value = self.root
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = check_plan_paths.run([])
        self.assertIn('Checked 1 paths, 0 missing', stdout.getvalue())
        self.assertEqual(result, 0)

    @patch('git_hooks_impl.entry_points.commands.check_plan_paths.project_root')
    def test_missing_referenced_path_is_flagged_and_returns_1(self, mock_project_root):
        """Plan references a nonexistent file via backticks -> MISSING line, returns 1."""
        with open(self.plan_path, 'w', encoding='utf-8') as f:
            f.write('See `tools/does_not_exist.py` for details.\n')
        mock_project_root.return_value = self.root
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = check_plan_paths.run([])
        output = stdout.getvalue()
        self.assertIn('MISSING: tools/does_not_exist.py', output)
        self.assertIn('Checked 1 paths, 1 missing', output)
        self.assertEqual(result, 1)


if __name__ == '__main__':
    unittest.main()
