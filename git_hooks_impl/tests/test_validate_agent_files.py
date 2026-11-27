#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for git_hooks_impl.entry_points.commands.validate_agent_files.

run()'s only direct dependency is project_root(), mocked at the
validate_agent_files import location per the Main Mock Rule. glob.glob()
and open() operate on real files inside a tempdir fixture tree.
"""

import io
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from git_hooks_impl.entry_points.commands import validate_agent_files

_VALID_ONE_SHOT = 'kind: agent\nmodel: sonnet\n'
_VALID_PERSISTENT = (
    'kind: agent\nmodel: sonnet\nself_role_dir: roles/tester\n'
    '\nMANDATORY pre-work\n'
)


def _write_agent_file(root, name, content):
    agents_dir = os.path.join(root, 'claude', 'agents')
    os.makedirs(agents_dir, exist_ok=True)
    with open(os.path.join(agents_dir, name), 'w', encoding='utf-8') as f:
        f.write(content)


class TestValidateAgentFilesRun(unittest.TestCase):
    """run(): lists incomplete orchestrator-*.md agent files and a summary."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    @patch('git_hooks_impl.entry_points.commands.validate_agent_files.project_root')
    def test_no_files_reports_clean_with_zero_total(self, mock_project_root):
        """No orchestrator-*.md files -> CLEAN: All 0 ..., returns 0."""
        mock_project_root.return_value = self.root
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = validate_agent_files.run([])
        self.assertIn('CLEAN: All 0 agent files', stdout.getvalue())
        self.assertEqual(result, 0)

    @patch('git_hooks_impl.entry_points.commands.validate_agent_files.project_root')
    def test_valid_one_shot_agent_reports_clean(self, mock_project_root):
        """One-shot agent with kind + model, no self_role_dir required -> CLEAN."""
        _write_agent_file(self.root, 'orchestrator-agent-thing.md', _VALID_ONE_SHOT)
        mock_project_root.return_value = self.root
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = validate_agent_files.run([])
        self.assertIn('CLEAN: All 1 agent files', stdout.getvalue())
        self.assertEqual(result, 0)

    @patch('git_hooks_impl.entry_points.commands.validate_agent_files.project_root')
    def test_persistent_agent_missing_self_role_dir_is_flagged(self, mock_project_root):
        """Persistent agent with kind + model but no self_role_dir/pre-work -> flagged."""
        _write_agent_file(
            self.root, 'orchestrator-persistent-thing.md', _VALID_ONE_SHOT
        )
        mock_project_root.return_value = self.root
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = validate_agent_files.run([])
        output = stdout.getvalue()
        self.assertIn('missing self_role_dir:', output)
        self.assertIn('missing MANDATORY pre-work section', output)
        self.assertEqual(result, 1)

    @patch('git_hooks_impl.entry_points.commands.validate_agent_files.project_root')
    def test_valid_persistent_agent_reports_clean(self, mock_project_root):
        """Persistent agent with all required fields present -> CLEAN."""
        _write_agent_file(
            self.root, 'orchestrator-persistent-thing.md', _VALID_PERSISTENT
        )
        mock_project_root.return_value = self.root
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = validate_agent_files.run([])
        self.assertIn('CLEAN: All 1 agent files', stdout.getvalue())
        self.assertEqual(result, 0)

    @patch('git_hooks_impl.entry_points.commands.validate_agent_files.project_root')
    def test_forbidden_claude_skill_dir_reference_is_flagged(self, mock_project_root):
        """CLAUDE_SKILL_DIR present in the file -> flagged as forbidden."""
        _write_agent_file(
            self.root, 'orchestrator-agent-thing.md', _VALID_ONE_SHOT + 'CLAUDE_SKILL_DIR\n'
        )
        mock_project_root.return_value = self.root
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = validate_agent_files.run([])
        self.assertIn('forbidden CLAUDE_SKILL_DIR ref', stdout.getvalue())
        self.assertEqual(result, 1)

    @patch('git_hooks_impl.entry_points.commands.validate_agent_files.project_root')
    def test_multiple_issues_all_listed_and_run_returns_1(self, mock_project_root):
        """A file failing every check gets every issue listed, and run()
        returns 1.
        """
        _write_agent_file(self.root, 'orchestrator-agent-broken.md', 'not frontmatter\n')
        mock_project_root.return_value = self.root
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = validate_agent_files.run([])
        output = stdout.getvalue()
        self.assertIn('missing kind: agent', output)
        self.assertIn('model not a current Claude 4.x declaration', output)
        self.assertIn('1 of 1 agent files have issues', output)
        self.assertEqual(result, 1)


if __name__ == '__main__':
    unittest.main()
