#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for git_hooks_impl/entry_points/cli.py: argparse building
(build_parser) and the cmd_new command flow.

All tests are fast (<1s each): no network, no real filesystem writes outside tempfile.
"""

import os
import subprocess as _sp
import unittest
from unittest.mock import AsyncMock, patch

from git_hooks_impl.entry_points.cli import (
    _AI_TOOLING_SRC,
    _git_project_root,
    _is_ai_tooling_repo,
    build_parser,
    cmd_new,
)
from git_hooks_impl.plan.context import PlanContext

# ---------------------------------------------------------------------------
#  Module-level log silencing
# ---------------------------------------------------------------------------

_log_patchers = []

def setUpModule():
    targets = []
    for t in targets:
        p = patch(t)
        p.start()
        _log_patchers.append(p)

def tearDownModule():
    for p in _log_patchers:
        p.stop()
    _log_patchers.clear()


# ===========================================================================
#  git_hooks_impl/entry_points/cli.py — argparse + context detection
# ===========================================================================

class TestBuildParser(unittest.TestCase):
    """build_parser: subcommand parsing."""

    def setUp(self):
        self.parser = build_parser()

    def test_sync_subcommand(self):
        args = self.parser.parse_args(['sync'])
        self.assertEqual(args.subcommand, 'sync')

    def test_planget_subcommand(self):
        args = self.parser.parse_args(['planget'])
        self.assertEqual(args.subcommand, 'planget')

    def test_plangen_force_flag(self):
        args = self.parser.parse_args(['plangen', '--force'])
        self.assertEqual(args.subcommand, 'plangen')
        self.assertTrue(args.force)

    def test_plangen_no_force_default(self):
        args = self.parser.parse_args(['plangen'])
        self.assertFalse(args.force)

    def test_status_subcommand(self):
        args = self.parser.parse_args(['status'])
        self.assertEqual(args.subcommand, 'status')

    def test_setup_subcommand(self):
        args = self.parser.parse_args(['setup'])
        self.assertEqual(args.subcommand, 'setup')

    def test_setup_link_subcommand(self):
        args = self.parser.parse_args(['setup', 'link'])
        self.assertEqual(args.subcommand, 'setup')
        self.assertEqual(args.setup_subcommand, 'link')

    def test_new_requires_branch_name(self):
        with self.assertRaises(SystemExit):
            self.parser.parse_args(['new'])

    def test_new_branch_name(self):
        args = self.parser.parse_args(['new', '--branch-name', 'feat/x'])
        self.assertEqual(args.branch_name, 'feat/x')

    def test_help_subcommand(self):
        args = self.parser.parse_args(['help'])
        self.assertEqual(args.subcommand, 'help')

    def test_no_subcommand_dest_is_none(self):
        args = self.parser.parse_args([])
        self.assertIsNone(args.subcommand)


class _Args:
    """Minimal stand-in for argparse.Namespace with a branch_name attribute."""

    def __init__(self, branch_name):
        self.branch_name = branch_name


class TestCmdNew(unittest.IsolatedAsyncioTestCase):
    """cmd_new: branch creation + plan generation only. No push, no MR."""

    def setUp(self):
        self.args = _Args('feat/PROJECTNAME-1234-thing')
        self.plan_context = PlanContext(
            jira_summary='Fix the thing', labels=['bug'], assignees=['dev1'])

    @patch('git_hooks_impl.entry_points.cli._scaffold_or_generate', new_callable=AsyncMock)
    @patch('git_hooks_impl.entry_points.cli.parse_branch', return_value=('feat', 'PROJECTNAME-1234'))
    @patch('git_hooks_impl.entry_points.cli.run', return_value=(0, '', ''))
    @patch('git_hooks_impl.entry_points.cli._git_project_root', return_value='/repo')
    async def test_happy_path_creates_branch_and_plan_only(
            self, _mock_root, mock_run, mock_parse_branch, mock_scaffold):
        mock_scaffold.return_value = self.plan_context

        rc = await cmd_new(self.args)

        self.assertEqual(rc, 0)
        mock_run.assert_called_once_with(['git', 'checkout', '-b', self.args.branch_name])
        mock_scaffold.assert_awaited_once()

    @patch('git_hooks_impl.entry_points.cli._scaffold_or_generate', new_callable=AsyncMock)
    @patch('git_hooks_impl.entry_points.cli.run', return_value=(1, '', 'checkout failed'))
    @patch('git_hooks_impl.entry_points.cli._git_project_root', return_value='/repo')
    async def test_checkout_failure_returns_early(
            self, _mock_root, mock_run, mock_scaffold):
        rc = await cmd_new(self.args)

        self.assertEqual(rc, 1)
        mock_scaffold.assert_not_awaited()

    @patch('git_hooks_impl.entry_points.cli._scaffold_or_generate', new_callable=AsyncMock)
    @patch('git_hooks_impl.entry_points.cli.parse_branch', return_value=('feat', 'PROJECTNAME-1234'))
    @patch('git_hooks_impl.entry_points.cli.run', return_value=(0, '', ''))
    @patch('git_hooks_impl.entry_points.cli._git_project_root', return_value='/repo')
    async def test_scaffold_called_with_interactive_false(
            self, _mock_root, mock_run, mock_parse_branch, mock_scaffold):
        mock_scaffold.return_value = self.plan_context

        await cmd_new(self.args)

        mock_scaffold.assert_awaited_once_with(
            self.args.branch_name, 'PROJECTNAME-1234', 'feat', interactive=False)


class TestIsAiToolingRepo(unittest.TestCase):
    """_is_ai_tooling_repo: path comparison."""

    def test_returns_true_when_same_path(self):
        result = _is_ai_tooling_repo(os.path.normpath(_AI_TOOLING_SRC))
        self.assertTrue(result)

    def test_returns_false_for_other_path(self):
        result = _is_ai_tooling_repo('/some/other/project')
        self.assertFalse(result)


class TestGitProjectRoot(unittest.TestCase):
    """_git_project_root: subprocess wrapper, exits on failure."""

    def test_returns_toplevel_on_success(self):
        """Git rev-parse succeeds -> stripped toplevel path returned."""
        with patch('git_hooks_impl.entry_points.cli.subprocess.check_output',
                   return_value='/my/project\n'):
            result = _git_project_root()
        self.assertEqual(result, '/my/project')

    def test_sys_exit_on_failure(self):
        """CalledProcessError -> SystemExit(1)."""
        with patch('git_hooks_impl.entry_points.cli.subprocess.check_output',
                   side_effect=_sp.CalledProcessError(128, 'git')), \
             self.assertRaises(SystemExit) as ctx:
            _git_project_root()
        self.assertEqual(ctx.exception.code, 1)


if __name__ == '__main__':
    unittest.main()
