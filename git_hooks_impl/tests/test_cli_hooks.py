#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for cli.py hook dispatch (hook side of unified main()).

Run:  python -m unittest git_hooks_impl.tests.test_cli_hooks -v
"""

import os
import unittest
from unittest.mock import MagicMock, patch

from git_hooks_impl.entry_points.cli import COMMANDS, build_parser, main
from git_hooks_impl.utils import AI_TOOLING_HOOK_RECURSION_GUARD

# ---------------------------------------------------------------------------
#  Module-level log silencing — prevent TESTS.log pollution
# ---------------------------------------------------------------------------

_log_patchers = []

def setUpModule():
    targets = [
        'git_hooks_impl.entry_points.cli.dbg',
        'git_hooks_impl.entry_points.cli.err',
    ]
    for t in targets:
        p = patch(t)
        p.start()
        _log_patchers.append(p)

def tearDownModule():
    for p in _log_patchers:
        p.stop()
    _log_patchers.clear()


# ---------------------------------------------------------------------------
#  build_parser — argument structure
# ---------------------------------------------------------------------------

class TestBuildParser(unittest.TestCase):
    """Argument parsing: no-args default, known subcommands, flags."""

    def test_no_args_subcommand_is_none(self):
        """No args -> subcommand is None (help printed by main, no default dispatch)."""
        parser = build_parser()
        args = parser.parse_args([])
        self.assertIsNone(args.subcommand)

    def test_all_commands_accepted(self):
        """Every key in COMMANDS is a registered subparser choice.

        Verifies parser has a subparser for each COMMANDS key without
        invoking subparsers that require additional flags (e.g. 'new').
        """
        parser = build_parser()
        subparsers_action = next(
            a for a in parser._actions
            if hasattr(a, 'choices') and a.choices is not None
        )
        for command_name in COMMANDS:
            self.assertIn(command_name, subparsers_action.choices)

    def test_cache_swap_prev_ref(self):
        """'cache-swap --prev-ref abc123' -> args.prev_ref='abc123'."""
        parser = build_parser()
        args = parser.parse_args(['cache-swap', '--prev-ref', 'abc123'])
        self.assertEqual(args.prev_ref, 'abc123')


# ---------------------------------------------------------------------------
#  main() — dispatch, re-entry guard, exception catch
# ---------------------------------------------------------------------------

class TestHookMain(unittest.TestCase):
    """main() orchestrator: guard, dispatch, error handling."""

    def setUp(self):
        self.original_guard = os.environ.pop(AI_TOOLING_HOOK_RECURSION_GUARD, None)

    def tearDown(self):
        os.environ.pop(AI_TOOLING_HOOK_RECURSION_GUARD, None)
        if self.original_guard is not None:
            os.environ[AI_TOOLING_HOOK_RECURSION_GUARD] = self.original_guard

    def test_dispatches_to_correct_command(self):
        """'sync-mr' arg -> COMMANDS['sync-mr']() called.

        Default command dispatches through COMMANDS dict.
        """
        mock_sync = MagicMock(return_value=0)
        with patch('sys.argv', ['prog', 'sync-mr']), \
             patch('git_hooks_impl.entry_points.cli.signal.signal'), \
             patch.dict('git_hooks_impl.entry_points.cli.COMMANDS',
                        {'sync-mr': lambda a: mock_sync()}):
            result = main()
        mock_sync.assert_called_once_with()
        self.assertEqual(result, 0)

    def test_reentry_guard_skips_execution(self):
        """AI_TOOLING_HOOK_RECURSION_GUARD already set -> main() returns 0 (graceful skip).

        Prevents recursive hook invocation when our commands run git internally.
        """
        os.environ[AI_TOOLING_HOOK_RECURSION_GUARD] = '1'
        result = main()
        self.assertEqual(result, 0)

    def test_exception_caught_exits_nonzero(self):
        """Command raises unexpected exception -> caught and logged, exits with 1.

        A crashed command is a failed command. Returning 0 would let a broken
        gate such as `mr verify` report success.
        """
        mock_extract = MagicMock(side_effect=RuntimeError('boom'))
        with patch('sys.argv', ['prog', 'extract-plan']), \
             patch('git_hooks_impl.entry_points.cli.signal.signal'), \
             patch.dict('git_hooks_impl.entry_points.cli.COMMANDS',
                        {'extract-plan': lambda a: mock_extract()}):
            result = main()
        self.assertEqual(result, 1)


# ---------------------------------------------------------------------------
#  Run all
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    unittest.main(verbosity=2)
