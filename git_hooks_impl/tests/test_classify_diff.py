#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for git_hooks_impl.entry_points.commands.classify_diff.

run()'s direct dependencies are get_diff_text() and get_numstat() (both
wrap subprocess.run) plus has_new_construct() (pure, over diff text already
returned). Mocked at the classify_diff import location per the Main Mock
Rule; has_new_construct() and the numstat parser are exercised directly
since they're pure functions worth testing on their own.
"""

import contextlib
import io
import unittest
from unittest.mock import MagicMock, patch

from git_hooks_impl.entry_points.commands import classify_diff


def _diff(file_path, added_lines):
    """Builds a minimal unified-diff text for one file with the given added lines."""
    body = '\n'.join(f'+{added_line}' for added_line in added_lines)
    return f'+++ b/{file_path}\n@@ -0,0 +1,{len(added_lines)} @@\n{body}\n'


class TestHasNewConstruct(unittest.TestCase):

    def test_no_added_lines_is_false(self):
        result, _ = classify_diff.has_new_construct(_diff('a.py', []))
        self.assertFalse(result)

    def test_plain_added_line_is_false(self):
        result, _ = classify_diff.has_new_construct(_diff('a.py', ['x = 1']))
        self.assertFalse(result)

    def test_new_function_in_python_is_true(self):
        result, file_path = classify_diff.has_new_construct(_diff('a.py', ['def foo():']))
        self.assertTrue(result)
        self.assertEqual(file_path, 'a.py')

    def test_new_class_in_cpp_is_true(self):
        result, _ = classify_diff.has_new_construct(_diff('a.cpp', ['class Foo {']))
        self.assertTrue(result)

    def test_control_flow_keyword_is_true(self):
        result, _ = classify_diff.has_new_construct(_diff('a.py', ['    if x:']))
        self.assertTrue(result)

    def test_same_content_in_markdown_is_false(self):
        # "no new function, class, or control flow" is a code-file concern;
        # a .md file talking about "if" or "class" is prose, not a construct.
        result, _ = classify_diff.has_new_construct(_diff('README.md', ['if this works']))
        self.assertFalse(result)

    def test_removed_lines_are_ignored(self):
        diff_text = '+++ b/a.py\n@@ -1,1 +0,0 @@\n-def foo():\n'
        result, _ = classify_diff.has_new_construct(diff_text)
        self.assertFalse(result)


class TestGetNumstat(unittest.TestCase):

    @patch('git_hooks_impl.entry_points.commands.classify_diff.subprocess.run')
    def test_counts_files_and_changed_lines(self, mock_run):
        mock_run.return_value = MagicMock(stdout='5\t2\ta.py\n1\t0\tb.py\n')
        file_count, changed = classify_diff.get_numstat(None)
        self.assertEqual(file_count, 2)
        self.assertEqual(changed, 8)

    @patch('git_hooks_impl.entry_points.commands.classify_diff.subprocess.run')
    def test_binary_file_dashes_are_not_counted(self, mock_run):
        mock_run.return_value = MagicMock(stdout='-\t-\timage.png\n3\t1\ta.py\n')
        file_count, changed = classify_diff.get_numstat(None)
        self.assertEqual(file_count, 2)
        self.assertEqual(changed, 4)

    @patch('git_hooks_impl.entry_points.commands.classify_diff.subprocess.run')
    def test_empty_diff_is_zero(self, mock_run):
        mock_run.return_value = MagicMock(stdout='')
        file_count, changed = classify_diff.get_numstat(None)
        self.assertEqual(file_count, 0)
        self.assertEqual(changed, 0)


class TestRun(unittest.TestCase):

    def _run_and_capture_tag(self, argv=None):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = classify_diff.run(argv or [])
        tag = buf.getvalue().strip().splitlines()[-1]
        return result, tag

    @patch('git_hooks_impl.entry_points.commands.classify_diff.get_numstat')
    @patch('git_hooks_impl.entry_points.commands.classify_diff.get_diff_text')
    def test_small_clean_diff_is_mechanical(self, mock_diff_text, mock_numstat):
        mock_diff_text.return_value = _diff('a.py', ['x = 1'])
        mock_numstat.return_value = (1, 5)
        result, tag = self._run_and_capture_tag()
        self.assertEqual(result, 0)
        self.assertEqual(tag, 'mechanical')

    @patch('git_hooks_impl.entry_points.commands.classify_diff.get_numstat')
    @patch('git_hooks_impl.entry_points.commands.classify_diff.get_diff_text')
    def test_too_many_files_is_standard(self, mock_diff_text, mock_numstat):
        mock_diff_text.return_value = _diff('a.py', ['x = 1'])
        mock_numstat.return_value = (3, 5)
        result, tag = self._run_and_capture_tag()
        self.assertEqual(result, 0)
        self.assertEqual(tag, 'standard')

    @patch('git_hooks_impl.entry_points.commands.classify_diff.get_numstat')
    @patch('git_hooks_impl.entry_points.commands.classify_diff.get_diff_text')
    def test_too_many_changed_lines_is_standard(self, mock_diff_text, mock_numstat):
        mock_diff_text.return_value = _diff('a.py', ['x = 1'])
        mock_numstat.return_value = (1, 30)
        result, tag = self._run_and_capture_tag()
        self.assertEqual(result, 0)
        self.assertEqual(tag, 'standard')

    @patch('git_hooks_impl.entry_points.commands.classify_diff.get_numstat')
    @patch('git_hooks_impl.entry_points.commands.classify_diff.get_diff_text')
    def test_new_function_forces_standard(self, mock_diff_text, mock_numstat):
        mock_diff_text.return_value = _diff('a.py', ['def foo():'])
        mock_numstat.return_value = (1, 1)
        result, tag = self._run_and_capture_tag()
        self.assertEqual(result, 0)
        self.assertEqual(tag, 'standard')

    def test_help_flag_returns_0_without_touching_git(self):
        with patch('git_hooks_impl.entry_points.commands.classify_diff.get_diff_text') as mock_diff:
            result = classify_diff.run(['--help'])
            self.assertEqual(result, 0)
            mock_diff.assert_not_called()


if __name__ == '__main__':
    unittest.main()
