#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for git_hooks_impl.entry_points.commands.verify_commit_builds.

Each function is tested with its own direct dependencies mocked, per the
Main Mock Rule: run() dispatches to _run_build/_verify_at_sha (mocked at
that level); _verify_at_sha's own direct deps (_current_branch,
_working_tree_dirty, subprocess.run, _run_build, _restore, project_root)
are mocked when testing it in isolation; _restore and _run_build are
tested standalone against subprocess.run/project_root directly.
"""

import unittest
from unittest.mock import MagicMock, call, patch

from git_hooks_impl.entry_points.commands import verify_commit_builds


class TestRunUsage(unittest.TestCase):
    """run(): --help and missing-argv paths never touch a dependency."""

    @patch('git_hooks_impl.entry_points.commands.verify_commit_builds._run_build')
    @patch('git_hooks_impl.entry_points.commands.verify_commit_builds._verify_at_sha')
    def test_help_flag_returns_zero_without_running_anything(self, mock_verify, mock_build):
        result = verify_commit_builds.run(['--help'])
        self.assertEqual(result, 0)
        mock_build.assert_not_called()
        mock_verify.assert_not_called()

    @patch('git_hooks_impl.entry_points.commands.verify_commit_builds._run_build')
    @patch('git_hooks_impl.entry_points.commands.verify_commit_builds._verify_at_sha')
    def test_missing_args_returns_one_without_running_anything(self, mock_verify, mock_build):
        result = verify_commit_builds.run(['build/x64'])
        self.assertEqual(result, 1)
        mock_build.assert_not_called()
        mock_verify.assert_not_called()


class TestRunDispatch(unittest.TestCase):
    """run(): with no sha, builds cwd; with a sha, delegates to _verify_at_sha."""

    @patch('git_hooks_impl.entry_points.commands.verify_commit_builds._verify_at_sha')
    @patch('git_hooks_impl.entry_points.commands.verify_commit_builds._run_build', return_value=0)
    def test_no_sha_builds_working_tree(self, mock_build, mock_verify):
        """No sha argument -> _run_build called directly, _verify_at_sha never invoked."""
        result = verify_commit_builds.run(['build/x64', 'Debug'])
        mock_build.assert_called_once_with('build/x64', 'Debug')
        mock_verify.assert_not_called()
        self.assertEqual(result, 0)

    @patch('git_hooks_impl.entry_points.commands.verify_commit_builds._verify_at_sha', return_value=3)
    @patch('git_hooks_impl.entry_points.commands.verify_commit_builds._run_build')
    def test_sha_delegates_to_verify_at_sha(self, mock_build, mock_verify):
        """A sha argument -> _verify_at_sha called with it, _run_build never called directly."""
        result = verify_commit_builds.run(['build/x64', 'Debug', 'abc123'])
        mock_verify.assert_called_once_with('build/x64', 'Debug', 'abc123')
        mock_build.assert_not_called()
        self.assertEqual(result, 3)


class TestRunBuild(unittest.TestCase):
    """_run_build()'s direct dependencies are project_root() and subprocess.run()."""

    @patch('git_hooks_impl.entry_points.commands.verify_commit_builds.subprocess.run')
    @patch('git_hooks_impl.entry_points.commands.verify_commit_builds.project_root', return_value='/repo')
    def test_invokes_cmake_build_from_project_root(self, mock_root, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        result = verify_commit_builds._run_build('build/x64', 'Debug')
        mock_run.assert_called_once_with(
            ['cmake', '--build', 'build/x64', '--config', 'Debug'], cwd='/repo',
        )
        self.assertEqual(result, 0)

    @patch('git_hooks_impl.entry_points.commands.verify_commit_builds.subprocess.run')
    @patch('git_hooks_impl.entry_points.commands.verify_commit_builds.project_root', return_value='/repo')
    def test_returns_build_failure_code(self, mock_root, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        result = verify_commit_builds._run_build('build/x64', 'Debug')
        self.assertEqual(result, 1)


class TestRestore(unittest.TestCase):
    """_restore()'s direct dependencies are project_root() and subprocess.run()."""

    @patch('git_hooks_impl.entry_points.commands.verify_commit_builds.subprocess.run')
    @patch('git_hooks_impl.entry_points.commands.verify_commit_builds.project_root', return_value='/repo')
    def test_stashed_true_checks_out_then_pops_stash(self, mock_root, mock_run):
        """stashed=True -> checkout runs, then a stash pop, in that order."""
        verify_commit_builds._restore('main', stashed=True)
        self.assertEqual(
            mock_run.call_args_list,
            [
                call(['git', 'checkout', '--force', 'main'], cwd='/repo'),
                call(['git', 'stash', 'pop'], cwd='/repo'),
            ],
        )

    @patch('git_hooks_impl.entry_points.commands.verify_commit_builds.subprocess.run')
    @patch('git_hooks_impl.entry_points.commands.verify_commit_builds.project_root', return_value='/repo')
    def test_stashed_false_only_checks_out_no_stash_pop(self, mock_root, mock_run):
        """stashed=False -> only the checkout call, no stash pop attempted."""
        verify_commit_builds._restore('main', stashed=False)
        mock_run.assert_called_once_with(['git', 'checkout', '--force', 'main'], cwd='/repo')


class TestVerifyAtSha(unittest.TestCase):
    """_verify_at_sha()'s direct deps: _current_branch, _working_tree_dirty,
    subprocess.run (stash push + checkout), _run_build, _restore, project_root.
    """

    @patch('git_hooks_impl.entry_points.commands.verify_commit_builds._restore')
    @patch('git_hooks_impl.entry_points.commands.verify_commit_builds._run_build')
    @patch('git_hooks_impl.entry_points.commands.verify_commit_builds.subprocess.run')
    @patch(
        'git_hooks_impl.entry_points.commands.verify_commit_builds._working_tree_dirty',
        return_value=False,
    )
    @patch(
        'git_hooks_impl.entry_points.commands.verify_commit_builds._current_branch',
        return_value='feature-branch',
    )
    @patch('git_hooks_impl.entry_points.commands.verify_commit_builds.project_root', return_value='/repo')
    def test_clean_tree_checks_out_builds_restores_in_order(
        self, mock_root, mock_branch, mock_dirty, mock_run, mock_build, mock_restore
    ):
        """Clean tree -> no stash push; checkout, then build, then restore, in order."""
        order = []
        mock_run.side_effect = lambda *a, **kw: order.append('checkout')
        mock_build.side_effect = lambda *a, **kw: order.append('build') or 0
        mock_restore.side_effect = lambda *a, **kw: order.append('restore')

        result = verify_commit_builds._verify_at_sha('build/x64', 'Debug', 'abc123')

        self.assertEqual(order, ['checkout', 'build', 'restore'])
        self.assertEqual(result, 0)
        mock_run.assert_called_once_with(
            ['git', 'checkout', '--force', '--detach', 'abc123'], cwd='/repo', check=True,
        )
        mock_restore.assert_called_once_with('feature-branch', False)

    @patch('git_hooks_impl.entry_points.commands.verify_commit_builds._restore')
    @patch('git_hooks_impl.entry_points.commands.verify_commit_builds._run_build', return_value=0)
    @patch('git_hooks_impl.entry_points.commands.verify_commit_builds.subprocess.run')
    @patch(
        'git_hooks_impl.entry_points.commands.verify_commit_builds._working_tree_dirty',
        return_value=True,
    )
    @patch(
        'git_hooks_impl.entry_points.commands.verify_commit_builds._current_branch',
        return_value='feature-branch',
    )
    @patch('git_hooks_impl.entry_points.commands.verify_commit_builds.project_root', return_value='/repo')
    def test_dirty_tree_stashes_before_checkout_and_restore_pops_it(
        self, mock_root, mock_branch, mock_dirty, mock_run, mock_build, mock_restore
    ):
        """Dirty tree -> stash push before checkout, and _restore told stashed=True."""
        verify_commit_builds._verify_at_sha('build/x64', 'Debug', 'abc123')
        self.assertEqual(
            mock_run.call_args_list,
            [
                call(['git', 'stash', 'push'], cwd='/repo', check=True),
                call(['git', 'checkout', '--force', '--detach', 'abc123'], cwd='/repo', check=True),
            ],
        )
        mock_restore.assert_called_once_with('feature-branch', True)

    @patch('git_hooks_impl.entry_points.commands.verify_commit_builds._restore')
    @patch('git_hooks_impl.entry_points.commands.verify_commit_builds._run_build', return_value=1)
    @patch('git_hooks_impl.entry_points.commands.verify_commit_builds.subprocess.run')
    @patch(
        'git_hooks_impl.entry_points.commands.verify_commit_builds._working_tree_dirty',
        return_value=False,
    )
    @patch(
        'git_hooks_impl.entry_points.commands.verify_commit_builds._current_branch',
        return_value='feature-branch',
    )
    @patch('git_hooks_impl.entry_points.commands.verify_commit_builds.project_root', return_value='/repo')
    def test_restore_runs_even_when_build_fails(
        self, mock_root, mock_branch, mock_dirty, mock_run, mock_build, mock_restore
    ):
        """Build returns nonzero -> _restore still runs, and the build's code is returned."""
        result = verify_commit_builds._verify_at_sha('build/x64', 'Debug', 'abc123')
        self.assertEqual(result, 1)
        mock_restore.assert_called_once_with('feature-branch', False)

    @patch('git_hooks_impl.entry_points.commands.verify_commit_builds._restore')
    @patch(
        'git_hooks_impl.entry_points.commands.verify_commit_builds._run_build',
        side_effect=RuntimeError('unexpected'),
    )
    @patch('git_hooks_impl.entry_points.commands.verify_commit_builds.subprocess.run')
    @patch(
        'git_hooks_impl.entry_points.commands.verify_commit_builds._working_tree_dirty',
        return_value=False,
    )
    @patch(
        'git_hooks_impl.entry_points.commands.verify_commit_builds._current_branch',
        return_value='feature-branch',
    )
    @patch('git_hooks_impl.entry_points.commands.verify_commit_builds.project_root', return_value='/repo')
    def test_restore_runs_even_on_unexpected_exception(
        self, mock_root, mock_branch, mock_dirty, mock_run, mock_build, mock_restore
    ):
        """An unexpected exception during build -> _restore still runs, exception propagates."""
        with self.assertRaises(RuntimeError):
            verify_commit_builds._verify_at_sha('build/x64', 'Debug', 'abc123')
        mock_restore.assert_called_once_with('feature-branch', False)


if __name__ == '__main__':
    unittest.main()
