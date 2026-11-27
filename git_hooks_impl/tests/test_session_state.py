#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for git_hooks_impl.entry_points.commands.session_state.

run()'s direct dependencies are project_root() and run_capture() (for the
branch name). Both mocked at the session_state import location per the Main
Mock Rule. Filesystem effects use a real tempfile directory as project_root
rather than mocking open()/os.makedirs - the schema (field names, whether
Step: appears) is exactly what other code parses, so a real round trip is
the meaningful test.
"""

import os
import tempfile
import unittest
from unittest.mock import patch

from git_hooks_impl.entry_points.commands import session_state


class TestSessionStateHelp(unittest.TestCase):

    @patch('git_hooks_impl.entry_points.commands.session_state.project_root')
    @patch('git_hooks_impl.entry_points.commands.session_state.run_capture')
    def test_help_flag_returns_0_without_touching_git(self, mock_run_capture, mock_project_root):
        result = session_state.run(['--help'])
        self.assertEqual(result, 0)
        mock_run_capture.assert_not_called()
        mock_project_root.assert_not_called()

    @patch('git_hooks_impl.entry_points.commands.session_state.project_root')
    @patch('git_hooks_impl.entry_points.commands.session_state.run_capture')
    def test_no_args_prints_help_returns_0(self, mock_run_capture, mock_project_root):
        result = session_state.run([])
        self.assertEqual(result, 0)
        mock_run_capture.assert_not_called()


class TestSessionStateGet(unittest.TestCase):

    @patch('git_hooks_impl.entry_points.commands.session_state.project_root')
    @patch('git_hooks_impl.entry_points.commands.session_state.run_capture')
    def test_get_with_no_state_file_prints_none(self, mock_run_capture, mock_project_root):
        with tempfile.TemporaryDirectory() as d:
            mock_project_root.return_value = d
            mock_run_capture.return_value = (0, 'my_branch\n', '')
            result = session_state.run(['get'])
            self.assertEqual(result, 0)

    @patch('git_hooks_impl.entry_points.commands.session_state.project_root')
    @patch('git_hooks_impl.entry_points.commands.session_state.run_capture')
    def test_get_reads_back_what_set_wrote(self, mock_run_capture, mock_project_root):
        with tempfile.TemporaryDirectory() as d:
            mock_project_root.return_value = d
            mock_run_capture.return_value = (0, 'my_branch\n', '')

            set_result = session_state.run(['set', 'refactorer', 'convergence', '4', '4.2'])
            self.assertEqual(set_result, 0)

            path = os.path.join(d, '.ai', 'cache', 'my_branch', 'session_state.md')
            self.assertTrue(os.path.isfile(path))
            with open(path, encoding='utf-8') as f:
                content = f.read()
            self.assertIn('Role: refactorer', content)
            self.assertIn('Workflow: convergence', content)
            self.assertIn('Phase: 4', content)
            self.assertIn('Step: 4.2', content)


class TestSessionStateSet(unittest.TestCase):

    @patch('git_hooks_impl.entry_points.commands.session_state.project_root')
    @patch('git_hooks_impl.entry_points.commands.session_state.run_capture')
    def test_set_without_step_omits_step_line(self, mock_run_capture, mock_project_root):
        with tempfile.TemporaryDirectory() as d:
            mock_project_root.return_value = d
            mock_run_capture.return_value = (0, 'my_branch\n', '')
            session_state.run(['set', 'gitter', 'precommit', '3'])
            path = os.path.join(d, '.ai', 'cache', 'my_branch', 'session_state.md')
            with open(path, encoding='utf-8') as f:
                content = f.read()
            self.assertNotIn('Step:', content)

    @patch('git_hooks_impl.entry_points.commands.session_state.project_root')
    @patch('git_hooks_impl.entry_points.commands.session_state.run_capture')
    def test_set_missing_args_returns_1(self, mock_run_capture, mock_project_root):
        with tempfile.TemporaryDirectory() as d:
            mock_project_root.return_value = d
            mock_run_capture.return_value = (0, 'my_branch\n', '')
            result = session_state.run(['set', 'gitter'])
            self.assertEqual(result, 1)

    @patch('git_hooks_impl.entry_points.commands.session_state.project_root')
    @patch('git_hooks_impl.entry_points.commands.session_state.run_capture')
    def test_unknown_branch_returns_1(self, mock_run_capture, mock_project_root):
        mock_project_root.return_value = '/repo'
        mock_run_capture.return_value = (1, '', 'fatal: not a git repository')
        result = session_state.run(['get'])
        self.assertEqual(result, 1)

    @patch('git_hooks_impl.entry_points.commands.session_state.project_root')
    @patch('git_hooks_impl.entry_points.commands.session_state.run_capture')
    def test_unknown_subcommand_returns_1(self, mock_run_capture, mock_project_root):
        mock_project_root.return_value = '/repo'
        mock_run_capture.return_value = (0, 'my_branch\n', '')
        result = session_state.run(['bogus'])
        self.assertEqual(result, 1)


if __name__ == '__main__':
    unittest.main()
