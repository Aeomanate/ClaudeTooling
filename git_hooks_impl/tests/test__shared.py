#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for git_hooks_impl.entry_points.commands._shared.

Both functions' only dependency is subprocess (project_root) or
os.environ + subprocess (ai_tooling_root), mocked at the _shared import
location per the Main Mock Rule.
"""

import os
import unittest
from unittest.mock import ANY, patch

from git_hooks_impl.entry_points.commands import _shared

_MOD = 'git_hooks_impl.entry_points.commands._shared'


class TestProjectRoot(unittest.TestCase):
    """project_root(): the calling repo's own git root - depends on cwd."""

    @patch(f'{_MOD}.subprocess.check_output', return_value='/calling/repo\n')
    def test_returns_git_toplevel_of_cwd(self, mock_check_output):
        result = _shared.project_root()
        self.assertEqual(result, '/calling/repo')
        mock_check_output.assert_called_once_with(
            ['git', 'rev-parse', '--show-toplevel'],
            stderr=ANY, text=True,
        )


class TestAiToolingRoot(unittest.TestCase):
    """ai_tooling_root(): $AI_TOOLING_SRC, else this module's OWN git root.

    Never the calling repo's cwd - this is the fix for the bug where
    dump_code_quality_reference resolved claude/skills/orchestrator/
    relative to whatever repo the caller's cwd happened to be in (works
    from ai_tooling itself, silently wrong from a consumer repo like reponame).
    from ai_tooling itself, silently wrong from a consumer repo like reponame).
    """

    def test_uses_env_var_when_set(self):
        """AI_TOOLING_SRC set -> returned directly, no subprocess call."""
        with (
            patch.dict(os.environ, {'AI_TOOLING_SRC': '/fake/ai_tooling'}, clear=False),
            patch(f'{_MOD}.subprocess.check_output') as mock_check_output,
        ):
            result = _shared.ai_tooling_root()
        self.assertEqual(result, '/fake/ai_tooling')
        mock_check_output.assert_not_called()

    def test_falls_back_to_this_modules_own_git_root_when_env_unset(self):
        """No env var -> git rev-parse --show-toplevel of THIS FILE's own dir,
        not the calling process's cwd.
        """
        env = dict(os.environ)
        env.pop('AI_TOOLING_SRC', None)
        with (
            patch.dict(os.environ, env, clear=True),
            patch(
                f'{_MOD}.subprocess.check_output', return_value='/ai_tooling/root\n',
            ) as mock_check_output,
        ):
            result = _shared.ai_tooling_root()
        self.assertEqual(result, '/ai_tooling/root')
        call_args = mock_check_output.call_args
        git_cmd = call_args[0][0]
        self.assertEqual(git_cmd[0:2], ['git', '-C'])
        # The -C path must be this module's own directory, never a bare
        # cwd-relative call - that's exactly what made the original bug
        # depend on which repo the caller happened to be standing in.
        self.assertTrue(git_cmd[2].endswith('commands'))


if __name__ == '__main__':
    unittest.main()
