#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for git_hooks_impl.entry_points.commands.read_logs.

run() has two direct dependencies: project_root() and subprocess.run() (for
`git log`). Both are mocked at the read_logs import location per the Main
Mock Rule. The hook.log file itself is read directly from a tempdir rather
than mocked open() — os.path/open are stdlib, not project dependencies.
"""

import io
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

from git_hooks_impl.entry_points.commands import read_logs
from git_hooks_impl.tests._stdout_helpers import ReconfigurableStringIO


class TestReadLogsWithHookLog(unittest.TestCase):
    """run(): existing .ai/hook.log content is printed verbatim."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        os.makedirs(os.path.join(self.root, '.ai'))
        with open(os.path.join(self.root, '.ai', 'hook.log'), 'w', encoding='utf-8') as f:
            f.write('hook ran ok\n')

    @patch('git_hooks_impl.entry_points.commands.read_logs.subprocess.run')
    @patch('git_hooks_impl.entry_points.commands.read_logs.project_root')
    def test_existing_hook_log_is_printed(self, mock_project_root, mock_run):
        """hook.log present -> its content appears between the section headers."""
        mock_project_root.return_value = self.root
        mock_run.return_value = MagicMock(returncode=0)
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = read_logs.run([])
        output = stdout.getvalue()
        self.assertIn('=== hook.log ===', output)
        self.assertIn('hook ran ok', output)
        self.assertIn('=== Recent commits ===', output)
        self.assertEqual(result, 0)

    @patch('git_hooks_impl.entry_points.commands.read_logs.subprocess.run')
    @patch('git_hooks_impl.entry_points.commands.read_logs.project_root')
    def test_git_log_invoked_with_last_10_oneline(self, mock_project_root, mock_run):
        """run() -> git log invoked with --oneline -10 from the project root."""
        mock_project_root.return_value = self.root
        mock_run.return_value = MagicMock(returncode=0)
        with redirect_stdout(io.StringIO()):
            read_logs.run([])
        mock_run.assert_called_once_with(
            ['git', 'log', '--oneline', '-10'], cwd=self.root, text=True,
        )

    @patch('git_hooks_impl.entry_points.commands.read_logs.subprocess.run')
    @patch('git_hooks_impl.entry_points.commands.read_logs.project_root')
    def test_returns_git_log_exit_code(self, mock_project_root, mock_run):
        """Git log fails -> run() propagates its non-zero return code."""
        mock_project_root.return_value = self.root
        mock_run.return_value = MagicMock(returncode=7)
        with redirect_stdout(io.StringIO()):
            result = read_logs.run([])
        self.assertEqual(result, 7)

    @patch('git_hooks_impl.entry_points.commands.read_logs.subprocess.run')
    @patch('git_hooks_impl.entry_points.commands.read_logs.project_root')
    def test_reconfigures_stdout_to_utf8_when_available(self, mock_project_root, mock_run):
        """Stdout supports reconfigure() -> run() switches it to utf-8/replace."""
        mock_project_root.return_value = self.root
        mock_run.return_value = MagicMock(returncode=0)
        fake_stdout = ReconfigurableStringIO()
        with redirect_stdout(fake_stdout):
            result = read_logs.run([])
        self.assertEqual(
            fake_stdout.reconfigure_calls, [{'encoding': 'utf-8', 'errors': 'replace'}],
        )
        self.assertEqual(result, 0)

    @patch('git_hooks_impl.entry_points.commands.read_logs.subprocess.run')
    @patch('git_hooks_impl.entry_points.commands.read_logs.project_root')
    def test_non_ascii_hook_log_content_does_not_raise(self, mock_project_root, mock_run):
        """hook.log containing a non-ASCII arrow -> run() completes and returns 0."""
        with open(os.path.join(self.root, '.ai', 'hook.log'), 'w', encoding='utf-8') as f:
            f.write('build step → done\n')
        mock_project_root.return_value = self.root
        mock_run.return_value = MagicMock(returncode=0)
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = read_logs.run([])
        self.assertIn('→', stdout.getvalue())
        self.assertEqual(result, 0)


class TestReadLogsWithoutHookLog(unittest.TestCase):
    """run(): missing .ai/hook.log falls back to a placeholder line."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    @patch('git_hooks_impl.entry_points.commands.read_logs.subprocess.run')
    @patch('git_hooks_impl.entry_points.commands.read_logs.project_root')
    def test_missing_hook_log_prints_placeholder(self, mock_project_root, mock_run):
        """No .ai/hook.log on disk -> "(no hook.log)" placeholder, still exit 0."""
        mock_project_root.return_value = self.root
        mock_run.return_value = MagicMock(returncode=0)
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = read_logs.run([])
        self.assertIn('(no hook.log)', stdout.getvalue())
        self.assertEqual(result, 0)


if __name__ == '__main__':
    unittest.main()
