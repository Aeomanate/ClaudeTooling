#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for git_hooks_impl.entry_points.cli.

Covers argparse, context detection, and the plangen stub.
All subprocess and filesystem calls are mocked.
"""

import asyncio
import os
import signal as signal_mod
import subprocess
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from git_hooks_impl.entry_points.cli import _AI_TOOLING_SRC as SRC
from git_hooks_impl.entry_points.cli import (
    COMMANDS,
    _git_project_root,
    _is_ai_tooling_repo,
    _run_async_cmd,
    build_parser,
    cmd_off,
    cmd_on,
    cmd_plangen,
    cmd_script,
    cmd_verify,
    main,
)
from git_hooks_impl.utils import AI_TOOLING_HOOK_RECURSION_GUARD

# ===========================================================================
#  Context detection — _git_project_root / _is_ai_tooling_repo
# ===========================================================================

class TestDetectContext(unittest.TestCase):

    def test_detects_ai_tooling_when_root_matches(self):
        """project_root == _AI_TOOLING_SRC -> _is_ai_tooling_repo returns True."""
        result = _is_ai_tooling_repo(os.path.normpath(SRC))
        self.assertTrue(result)

    def test_detects_consumer_when_root_differs(self):
        """project_root != _AI_TOOLING_SRC -> _is_ai_tooling_repo returns False."""
        result = _is_ai_tooling_repo('/some/completely/different/path')
        self.assertFalse(result)

    def test_git_project_root_returns_stripped_toplevel(self):
        """check_output returns path with trailing newline -> stripped."""
        with patch('git_hooks_impl.entry_points.cli.subprocess.check_output',
                   return_value='/my/project\n'):
            result = _git_project_root()
        self.assertEqual(result, '/my/project')

    def test_git_project_root_exits_when_not_in_repo(self):
        """CalledProcessError (not a git repo) -> SystemExit(1)."""
        with patch('git_hooks_impl.entry_points.cli.subprocess.check_output',
                   side_effect=subprocess.CalledProcessError(128, 'git')), \
             self.assertRaises(SystemExit) as ctx:
            _git_project_root()
        self.assertEqual(ctx.exception.code, 1)


# ===========================================================================
#  plangen stub
# ===========================================================================

class TestPlangenWiring(unittest.TestCase):
    """cmd_plangen wiring: calls _discover_branch_and_ticket + _scaffold_or_generate."""

    @patch('git_hooks_impl.entry_points.cli._scaffold_or_generate', new_callable=AsyncMock)
    @patch('git_hooks_impl.entry_points.cli._discover_branch_and_ticket',
           return_value=('feature/TEST-1', 'default', 'TEST-1'))
    def test_plangen_calls_scaffold_or_generate_with_force_false(
            self, mock_discover, mock_scaffold):
        """args.force=False -> scaffold_or_generate called with force=False, interactive=True."""
        args = MagicMock()
        args.force = False
        result = asyncio.run(cmd_plangen(args))
        mock_scaffold.assert_called_once_with('feature/TEST-1', 'TEST-1', 'default',
                                              force=False, interactive=True)
        self.assertEqual(result, 0)

    @patch('git_hooks_impl.entry_points.cli._scaffold_or_generate', new_callable=AsyncMock)
    @patch('git_hooks_impl.entry_points.cli._discover_branch_and_ticket',
           return_value=('feature/TEST-1', 'default', 'TEST-1'))
    def test_plangen_passes_force_true(self, mock_discover, mock_scaffold):
        """args.force=True -> scaffold_or_generate called with force=True."""
        args = MagicMock()
        args.force = True
        result = asyncio.run(cmd_plangen(args))
        mock_scaffold.assert_called_once_with('feature/TEST-1', 'TEST-1', 'default',
                                              force=True, interactive=True)
        self.assertEqual(result, 0)

    @patch('git_hooks_impl.entry_points.cli._scaffold_or_generate', new_callable=AsyncMock)
    @patch('git_hooks_impl.entry_points.cli._discover_branch_and_ticket',
           return_value=(None, None, None))
    def test_plangen_returns_1_when_branch_detection_fails(
            self, mock_discover, mock_scaffold):
        """Branch detection returns None -> cmd_plangen returns 1 without calling scaffold."""
        args = MagicMock()
        result = asyncio.run(cmd_plangen(args))
        mock_scaffold.assert_not_called()
        self.assertEqual(result, 1)

    @patch('builtins.print')
    @patch('git_hooks_impl.entry_points.cli._scaffold_or_generate', new_callable=AsyncMock,
           side_effect=RuntimeError('AI unavailable'))
    @patch('git_hooks_impl.entry_points.cli._discover_branch_and_ticket',
           return_value=('feature/TEST-1', 'default', 'TEST-1'))
    def test_plangen_returns_1_on_exception(
            self, mock_discover, mock_scaffold, mock_print):
        """scaffold_or_generate raises -> cmd_plangen returns 1."""
        args = MagicMock()
        args.force = False
        result = asyncio.run(cmd_plangen(args))
        self.assertEqual(result, 1)


class TestCmdVerify(unittest.TestCase):
    """cmd_verify: runs ruff + unittest (subprocess) + leak_check (in-process
    via leak_check_cmd.run). Returns the max exit code of the three.

    leak_check_cmd.run is mocked here — it is cmd_verify's direct dependency
    for the leak gate, and it runs in-process. Its own behavior is covered
    by test_leak_check.py.

    cmd_verify also opens three real, non-isolated paths directly (not via
    a mockable helper): .ai/BRANCH_PLAN.md, .ai/tooling.log, and a
    %TEMP%/ai-tooling-backups/last-run-leak.txt marker. Each test patches
    the module's `open` to raise OSError, matching the "nothing to compare
    against" branch cmd_verify already handles for a missing file — this
    keeps the assertions independent of the running machine's real .ai/ state.
    """

    @patch('git_hooks_impl.entry_points.cli.open', side_effect=OSError, create=True)
    @patch('git_hooks_impl.entry_points.cli.leak_check_cmd.run', return_value=0)
    @patch('git_hooks_impl.entry_points.cli.subprocess.call', side_effect=[0, 0])
    def test_cmd_verify_returns_0_when_all_clean(self, mock_call, mock_leak_check, mock_open):
        """ruff=0, unittest=0, leak_check=0 -> cmd_verify returns 0."""
        args = MagicMock()
        result = cmd_verify(args)
        self.assertEqual(result, 0)
        self.assertEqual(mock_call.call_count, 2)
        mock_leak_check.assert_called_once_with([])

    @patch('git_hooks_impl.entry_points.cli.open', side_effect=OSError, create=True)
    @patch('git_hooks_impl.entry_points.cli.leak_check_cmd.run', return_value=0)
    @patch('git_hooks_impl.entry_points.cli.subprocess.call', side_effect=[1, 0])
    def test_cmd_verify_returns_nonzero_when_ruff_fails(
        self, mock_call, mock_leak_check, mock_open
    ):
        """Ruff returns 1, unittest=0, leak_check=0 -> cmd_verify returns 1."""
        args = MagicMock()
        result = cmd_verify(args)
        self.assertEqual(result, 1)

    @patch('git_hooks_impl.entry_points.cli.open', side_effect=OSError, create=True)
    @patch('git_hooks_impl.entry_points.cli.leak_check_cmd.run', return_value=0)
    @patch('git_hooks_impl.entry_points.cli.subprocess.call', side_effect=[0, 1])
    def test_cmd_verify_returns_nonzero_when_tests_fail(
        self, mock_call, mock_leak_check, mock_open
    ):
        """ruff=0, unittest returns 1, leak_check=0 -> cmd_verify returns 1."""
        args = MagicMock()
        result = cmd_verify(args)
        self.assertEqual(result, 1)

    @patch('git_hooks_impl.entry_points.cli.open', side_effect=OSError, create=True)
    @patch('git_hooks_impl.entry_points.cli.leak_check_cmd.run', return_value=1)
    @patch('git_hooks_impl.entry_points.cli.subprocess.call', side_effect=[0, 0])
    def test_cmd_verify_returns_nonzero_when_leak_check_fails(
        self, mock_call, mock_leak_check, mock_open
    ):
        """ruff=0, unittest=0, leak_check returns 1 -> cmd_verify returns 1."""
        args = MagicMock()
        result = cmd_verify(args)
        self.assertEqual(result, 1)

    @patch('git_hooks_impl.entry_points.cli.open', side_effect=OSError, create=True)
    @patch('git_hooks_impl.entry_points.cli.leak_check_cmd.run', return_value=0)
    @patch('git_hooks_impl.entry_points.cli.subprocess.call', side_effect=[1, 2])
    def test_cmd_verify_returns_larger_when_both_fail(
        self, mock_call, mock_leak_check, mock_open
    ):
        """ruff=1, unittest=2, leak_check=0 -> cmd_verify returns the larger exit code."""
        args = MagicMock()
        result = cmd_verify(args)
        self.assertEqual(result, 2)


# ===========================================================================
#  cmd_on / cmd_off — toggle_tooling_enabled result -> exit code + log call
# ===========================================================================

class TestCmdOn(unittest.TestCase):
    """cmd_on: maps toggle_tooling_enabled(True) result to exit code + log helper."""

    @patch('git_hooks_impl.entry_points.cli.err')
    @patch('git_hooks_impl.entry_points.cli.toggle_tooling_enabled', return_value='not_found')
    def test_not_found_returns_1_and_errs(self, mock_toggle, mock_err):
        """'not_found' -> returns 1, err() called."""
        result = cmd_on(None)
        self.assertEqual(result, 1)
        mock_err.assert_called_once()

    @patch('git_hooks_impl.entry_points.cli.err')
    @patch('git_hooks_impl.entry_points.cli.toggle_tooling_enabled', return_value='line_missing')
    def test_line_missing_returns_1_and_errs(self, mock_toggle, mock_err):
        """'line_missing' -> returns 1, err() called."""
        result = cmd_on(None)
        self.assertEqual(result, 1)
        mock_err.assert_called_once()

    @patch('git_hooks_impl.entry_points.cli.warn')
    @patch('git_hooks_impl.entry_points.cli.toggle_tooling_enabled', return_value='already')
    def test_already_returns_0_and_warns(self, mock_toggle, mock_warn):
        """'already' -> returns 0, warn() called."""
        result = cmd_on(None)
        self.assertEqual(result, 0)
        mock_warn.assert_called_once()

    @patch('git_hooks_impl.entry_points.cli.log')
    @patch('git_hooks_impl.entry_points.cli.toggle_tooling_enabled', return_value=None)
    def test_success_returns_0_and_logs(self, mock_toggle, mock_log):
        """None (success) -> returns 0, log() called."""
        result = cmd_on(None)
        self.assertEqual(result, 0)
        mock_log.assert_called_once()


class TestCmdOff(unittest.TestCase):
    """cmd_off: maps toggle_tooling_enabled(False) result to exit code + log helper."""

    @patch('git_hooks_impl.entry_points.cli.err')
    @patch('git_hooks_impl.entry_points.cli.toggle_tooling_enabled', return_value='not_found')
    def test_not_found_returns_1_and_errs(self, mock_toggle, mock_err):
        """'not_found' -> returns 1, err() called."""
        result = cmd_off(None)
        self.assertEqual(result, 1)
        mock_err.assert_called_once()

    @patch('git_hooks_impl.entry_points.cli.err')
    @patch('git_hooks_impl.entry_points.cli.toggle_tooling_enabled', return_value='line_missing')
    def test_line_missing_returns_1_and_errs(self, mock_toggle, mock_err):
        """'line_missing' -> returns 1, err() called."""
        result = cmd_off(None)
        self.assertEqual(result, 1)
        mock_err.assert_called_once()

    @patch('git_hooks_impl.entry_points.cli.warn')
    @patch('git_hooks_impl.entry_points.cli.toggle_tooling_enabled', return_value='already')
    def test_already_returns_0_and_warns(self, mock_toggle, mock_warn):
        """'already' -> returns 0, warn() called."""
        result = cmd_off(None)
        self.assertEqual(result, 0)
        mock_warn.assert_called_once()

    @patch('git_hooks_impl.entry_points.cli.log')
    @patch('git_hooks_impl.entry_points.cli.toggle_tooling_enabled', return_value=None)
    def test_success_returns_0_and_logs(self, mock_toggle, mock_log):
        """None (success) -> returns 0, log() called."""
        result = cmd_off(None)
        self.assertEqual(result, 0)
        mock_log.assert_called_once()


# ===========================================================================
#  Argparse smoke tests
# ===========================================================================

class TestArgparseSmokeTest(unittest.TestCase):

    def setUp(self):
        self.parser = build_parser()

    def test_sync_subcommand_parsed(self):
        args = self.parser.parse_args(['sync'])
        self.assertEqual(args.subcommand, 'sync')

    def test_planget_subcommand_parsed(self):
        args = self.parser.parse_args(['planget'])
        self.assertEqual(args.subcommand, 'planget')

    def test_plangen_with_force_flag(self):
        args = self.parser.parse_args(['plangen', '--force'])
        self.assertTrue(args.force)

    def test_plangen_force_defaults_false(self):
        args = self.parser.parse_args(['plangen'])
        self.assertFalse(args.force)

    def test_setup_link_subcommand(self):
        args = self.parser.parse_args(['setup', 'link'])
        self.assertEqual(args.subcommand, 'setup')
        self.assertEqual(args.setup_subcommand, 'link')

    def test_new_requires_branch_name(self):
        """Mr new without --branch-name -> SystemExit."""
        with self.assertRaises(SystemExit):
            self.parser.parse_args(['new'])

    def test_new_branch_name_accepted(self):
        args = self.parser.parse_args(['new', '--branch-name', 'feat/xyz'])
        self.assertEqual(args.branch_name, 'feat/xyz')

    def test_help_subcommand_parsed(self):
        args = self.parser.parse_args(['help'])
        self.assertEqual(args.subcommand, 'help')

    def test_no_subcommand_dest_is_none(self):
        args = self.parser.parse_args([])
        self.assertIsNone(args.subcommand)

    def test_unknown_subcommand_handled(self):
        """Unrecognised subcommand -> SystemExit (argparse rejects it)."""
        with self.assertRaises(SystemExit):
            self.parser.parse_args(['totally_unknown'])

    def test_script_subcommand_captures_name_and_params(self):
        """Mr script foo --bar baz -> name='foo', params=['--bar', 'baz']."""
        args = self.parser.parse_args(['script', 'foo', '--bar', 'baz'])
        self.assertEqual(args.name, 'foo')
        self.assertEqual(args.params, ['--bar', 'baz'])


# ===========================================================================
#  cmd_script — `mr script <name> [params...]` wiring
# ===========================================================================

class TestCmdScript(unittest.TestCase):
    """cmd_script: deferred-imports the registry, forwards name/params, returns its exit code."""

    @patch('git_hooks_impl.entry_points.commands.registry.run', return_value=7)
    def test_calls_registry_run_and_returns_its_exit_code(self, mock_run):
        """registry.run(name, params) returns 7 -> cmd_script returns 7."""
        args = MagicMock()
        args.name = 'lint'
        args.params = ['--fix']
        result = cmd_script(args)
        mock_run.assert_called_once_with('lint', ['--fix'])
        self.assertEqual(result, 7)


# ===========================================================================
#  COMMANDS dispatch table
# ===========================================================================

class TestCommandsDispatchTable(unittest.TestCase):
    """COMMANDS dict: 17 keys, all lambda values."""

    def test_all_expected_keys_present(self):
        """COMMANDS has exactly the 17 expected subcommand keys."""
        expected = {
            'status', 'sync', 'plangen', 'planget', 'new',
            'setup', 'on', 'off', 'verify', 'script', 'help',
            'sync-mr', 'extract-plan', 'get-plan',
            'cache-swap', 'cache-save', 'cache-prune',
        }
        self.assertEqual(set(COMMANDS.keys()), expected)

    def test_all_values_are_callable(self):
        """Every COMMANDS entry is a callable (lambda)."""
        for key, value in COMMANDS.items():
            self.assertTrue(callable(value), f'COMMANDS[{key!r}] is not callable')

    def test_async_commands_route_through_run_async_cmd(self):
        """Async subcommands call _run_async_cmd; sync subcommands call handler directly."""
        async_keys = {'status', 'sync', 'plangen', 'planget', 'new',
                      'sync-mr', 'extract-plan', 'get-plan'}
        sentinel = MagicMock(return_value=0)
        for key in async_keys:
            with patch('git_hooks_impl.entry_points.cli._run_async_cmd',
                       side_effect=sentinel) as mock_run:
                args = MagicMock()
                COMMANDS[key](args)
                mock_run.assert_called_once()


# ===========================================================================
#  SIGINT install
# ===========================================================================

class TestSigintInstall(unittest.TestCase):
    """main() installs SIGINT handler before dispatching."""

    def setUp(self):
        self.original_guard = os.environ.pop(AI_TOOLING_HOOK_RECURSION_GUARD, None)

    def tearDown(self):
        os.environ.pop(AI_TOOLING_HOOK_RECURSION_GUARD, None)
        if self.original_guard is not None:
            os.environ[AI_TOOLING_HOOK_RECURSION_GUARD] = self.original_guard

    def test_sigint_installed_before_dispatch(self):
        """main() calls signal.signal(SIGINT, _sigint_handler) before any command."""
        install_order = []

        def capture_signal(sig, handler):
            install_order.append(('signal', sig))
            return signal_mod.SIG_DFL

        def fake_dispatch(args):
            install_order.append(('dispatch',))
            return 0

        with patch('git_hooks_impl.entry_points.cli.signal.signal',
                   side_effect=capture_signal), \
             patch('git_hooks_impl.entry_points.cli.build_parser') as mock_parser, \
             patch('git_hooks_impl.entry_points.cli.COMMANDS',
                   {'status': lambda a: fake_dispatch(a)}), \
             patch('git_hooks_impl.entry_points.cli.dbg'), \
             patch('sys.exit'):
            mock_parser.return_value.parse_args.return_value = MagicMock(
                subcommand='status')
            os.environ.pop(AI_TOOLING_HOOK_RECURSION_GUARD, None)
            main()

        self.assertTrue(len(install_order) >= 2)
        self.assertEqual(install_order[0], ('signal', signal_mod.SIGINT))
        self.assertEqual(install_order[1], ('dispatch',))


# ===========================================================================
#  _run_async_cmd — Windows ProactorEventLoop transport cleanup
# ===========================================================================

class TestRunAsyncCmdTransportSuppression(unittest.TestCase):
    """_run_async_cmd installs an exception handler that suppresses
    'Event loop is closed' RuntimeError from Windows transport __del__.
    """

    def test_suppress_transport_del_error_does_not_propagate(self):
        """Event-loop-closed RuntimeError from transport cleanup -> silently dropped."""

        async def _noop(args):
            return 0

        args = MagicMock()
        result = _run_async_cmd(_noop, args)
        self.assertEqual(result, 0)

    def test_other_exceptions_from_exception_handler_propagate(self):
        """Non-transport errors are forwarded to default_exception_handler."""

        async def _trigger_non_transport_error(args):
            return 0

        with patch('git_hooks_impl.entry_points.cli.asyncio.new_event_loop') as mock_new_loop:
            mock_loop = MagicMock()
            mock_loop.run_until_complete = MagicMock(return_value=0)
            mock_loop.close = MagicMock()
            captured_handler = [None]

            def capture_handler(handler):
                captured_handler[0] = handler
            mock_loop.set_exception_handler = capture_handler
            mock_new_loop.return_value = mock_loop

            _run_async_cmd(_trigger_non_transport_error, MagicMock())

        handler = captured_handler[0]
        self.assertIsNotNone(handler)

        # Transport error context -> handler suppresses (does not call default)
        mock_loop2 = MagicMock()
        handler(mock_loop2, {'exception': RuntimeError('Event loop is closed')})
        mock_loop2.default_exception_handler.assert_not_called()

        # Non-transport error context -> handler forwards to default
        handler(mock_loop2, {'exception': ValueError('unrelated'), 'message': 'x'})
        mock_loop2.default_exception_handler.assert_called_once()


if __name__ == '__main__':
    unittest.main()
