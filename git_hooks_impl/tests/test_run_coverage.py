#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for git_hooks_impl.entry_points.commands.run_coverage.

run()'s direct dependencies are project_root() and subprocess.run() (called
up to 3 times: coverage run, coverage report, coverage json). Both mocked at
the run_coverage import location per the Main Mock Rule. os.makedirs()
operates on a real tempdir fixture.
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from git_hooks_impl.entry_points.commands import run_coverage


class TestRunCoverageStepFailures(unittest.TestCase):
    """run(): a failing step short-circuits the remaining steps."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    @patch('git_hooks_impl.entry_points.commands.run_coverage.subprocess.run')
    @patch('git_hooks_impl.entry_points.commands.run_coverage.project_root')
    def test_run_step_failure_skips_report_and_json(self, mock_project_root, mock_run):
        """Coverage run returncode 2 -> report/json never invoked, returns 2."""
        mock_project_root.return_value = self.root
        mock_run.return_value = MagicMock(returncode=2)
        result = run_coverage.run([])
        self.assertEqual(result, 2)
        self.assertEqual(mock_run.call_count, 1)

    @patch('git_hooks_impl.entry_points.commands.run_coverage.subprocess.run')
    @patch('git_hooks_impl.entry_points.commands.run_coverage.project_root')
    def test_report_step_failure_skips_json(self, mock_project_root, mock_run):
        """Coverage run ok, coverage report fails -> json never invoked, returns report's code."""
        mock_project_root.return_value = self.root
        mock_run.side_effect = [MagicMock(returncode=0), MagicMock(returncode=3)]
        result = run_coverage.run([])
        self.assertEqual(result, 3)
        self.assertEqual(mock_run.call_count, 2)

    @patch('git_hooks_impl.entry_points.commands.run_coverage.subprocess.run')
    @patch('git_hooks_impl.entry_points.commands.run_coverage.project_root')
    def test_json_step_failure_returns_its_code(self, mock_project_root, mock_run):
        """Coverage run and report ok, json fails -> returns json's code."""
        mock_project_root.return_value = self.root
        mock_run.side_effect = [
            MagicMock(returncode=0), MagicMock(returncode=0), MagicMock(returncode=4),
        ]
        result = run_coverage.run([])
        self.assertEqual(result, 4)
        self.assertEqual(mock_run.call_count, 3)


class TestRunCoverageSuccess(unittest.TestCase):
    """run(): all 3 steps succeed -> exact commands issued, returns 0."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    @patch('git_hooks_impl.entry_points.commands.run_coverage.subprocess.run')
    @patch('git_hooks_impl.entry_points.commands.run_coverage.project_root')
    def test_success_invokes_run_report_json_with_expected_argv(
        self, mock_project_root, mock_run
    ):
        """All 3 steps return 0 -> run/report/json argv match spec, cwd=root, returns 0."""
        mock_project_root.return_value = self.root
        mock_run.return_value = MagicMock(returncode=0)
        result = run_coverage.run([])
        run_call, report_call, json_call = mock_run.call_args_list
        self.assertEqual(
            run_call.args[0],
            ['coverage', 'run', '--branch', '-m', 'unittest', 'discover', 'git_hooks_impl/tests'],
        )
        self.assertEqual(run_call.kwargs['cwd'], self.root)
        self.assertEqual(report_call.args[0], ['coverage', 'report', '--show-missing'])
        expected_json_out = os.path.join(self.root, '.ai', 'artifacts', 'coverage.json')
        self.assertEqual(json_call.args[0], ['coverage', 'json', '-o', expected_json_out])
        self.assertEqual(result, 0)

    @patch('git_hooks_impl.entry_points.commands.run_coverage.subprocess.run')
    @patch('git_hooks_impl.entry_points.commands.run_coverage.project_root')
    def test_success_creates_artifacts_directory(self, mock_project_root, mock_run):
        """.ai/artifacts is created on disk before the coverage json step runs."""
        mock_project_root.return_value = self.root
        mock_run.return_value = MagicMock(returncode=0)
        run_coverage.run([])
        self.assertTrue(os.path.isdir(os.path.join(self.root, '.ai', 'artifacts')))


if __name__ == '__main__':
    unittest.main()
