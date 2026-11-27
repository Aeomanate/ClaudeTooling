#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for git_hooks_impl.entry_points.commands.run_cpp_tests.

run()'s direct dependencies are project_root() and subprocess.run() (called
twice: cmake build, then ctest). Both mocked at the run_cpp_tests import
location per the Main Mock Rule.
"""

import unittest
from unittest.mock import MagicMock, patch

from git_hooks_impl.entry_points.commands import run_cpp_tests


class TestRunCppTestsUsage(unittest.TestCase):
    """run(): missing target or pattern argv -> usage error, no subprocess calls."""

    @patch('git_hooks_impl.entry_points.commands.run_cpp_tests.subprocess.run')
    def test_no_args_returns_1_without_running_anything(self, mock_run):
        """Empty argv -> returns 1, cmake/ctest never invoked."""
        result = run_cpp_tests.run([])
        self.assertEqual(result, 1)
        mock_run.assert_not_called()

    @patch('git_hooks_impl.entry_points.commands.run_cpp_tests.subprocess.run')
    def test_single_arg_returns_1_without_running_anything(self, mock_run):
        """Only a target, no pattern -> returns 1, cmake/ctest never invoked."""
        result = run_cpp_tests.run(['MyTarget'])
        self.assertEqual(result, 1)
        mock_run.assert_not_called()


class TestRunCppTestsBuildFailure(unittest.TestCase):
    """run(): a failing cmake build short-circuits before ctest runs."""

    @patch('git_hooks_impl.entry_points.commands.run_cpp_tests.subprocess.run')
    @patch('git_hooks_impl.entry_points.commands.run_cpp_tests.project_root')
    def test_build_failure_skips_ctest_and_returns_build_code(self, mock_project_root, mock_run):
        """Cmake build returncode 2 -> ctest not called, run() returns 2."""
        mock_project_root.return_value = '/repo'
        mock_run.return_value = MagicMock(returncode=2)
        result = run_cpp_tests.run(['MyTarget', 'MyPattern'])
        self.assertEqual(result, 2)
        self.assertEqual(mock_run.call_count, 1)


class TestRunCppTestsSuccess(unittest.TestCase):
    """run(): a successful build proceeds to ctest with the right arguments."""

    @patch('git_hooks_impl.entry_points.commands.run_cpp_tests.subprocess.run')
    @patch('git_hooks_impl.entry_points.commands.run_cpp_tests.project_root')
    def test_build_success_invokes_ctest_with_target_and_pattern(self, mock_project_root, mock_run):
        """Build ok -> ctest invoked with --preset windows-x64-debug -R <pattern>."""
        mock_project_root.return_value = '/repo'
        mock_run.side_effect = [MagicMock(returncode=0), MagicMock(returncode=0)]
        result = run_cpp_tests.run(['MyTarget', 'MyPattern'])
        build_call, ctest_call = mock_run.call_args_list
        self.assertEqual(
            build_call.args[0],
            ['cmake', '--build', 'build/x64', '--config', 'Debug', '--target', 'MyTarget'],
        )
        self.assertEqual(
            ctest_call.args[0],
            ['ctest', '--preset', 'windows-x64-debug', '-R', 'MyPattern', '--verbose'],
        )
        self.assertEqual(result, 0)

    @patch('git_hooks_impl.entry_points.commands.run_cpp_tests.subprocess.run')
    @patch('git_hooks_impl.entry_points.commands.run_cpp_tests.project_root')
    def test_returns_ctest_exit_code_on_test_failure(self, mock_project_root, mock_run):
        """Build ok, ctest fails -> run() propagates ctest's non-zero code."""
        mock_project_root.return_value = '/repo'
        mock_run.side_effect = [MagicMock(returncode=0), MagicMock(returncode=5)]
        result = run_cpp_tests.run(['MyTarget', 'MyPattern'])
        self.assertEqual(result, 5)


if __name__ == '__main__':
    unittest.main()
