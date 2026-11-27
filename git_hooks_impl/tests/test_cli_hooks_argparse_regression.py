#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Regression tests for cli.py hook-side argparse contract.

Covers the bug where 5 git-hook stubs forwarded "$@" to a Python entrypoint
whose argparse rejects unknown positionals — checkout/merge/rewrite/commit/push
emitted "ai-tooling-hooks.py: error: unrecognized arguments: ...". The fix
strips "$@" from the stubs; these tests guard against regressions in the
argparse contract that the stubs now depend on.

In-process — invokes main() with patched sys.argv and patched COMMANDS dict.
No subprocess, no real git/glab/Anthropic calls.

Run:  python -m unittest git_hooks_impl.tests.test_cli_hooks_argparse_regression -v
"""

import contextlib
import io
import os
import unittest
from unittest.mock import MagicMock, patch

from git_hooks_impl.entry_points.cli import main
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
    for target in targets:
        p = patch(target)
        p.start()
        _log_patchers.append(p)


def tearDownModule():
    for p in _log_patchers:
        p.stop()
    _log_patchers.clear()


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _run_main_capturing_io(argv):
    """Invoke main() with sys.argv patched, capturing stderr+stdout.

    Returns (return_value, stderr_text, stdout_text, exception_or_none).
    SystemExit is captured into the tuple rather than propagating, so
    callers can assert on exit code without try/except boilerplate.
    """
    captured_err = io.StringIO()
    captured_out = io.StringIO()
    exc = None
    result = None
    with patch('sys.argv', argv), \
         contextlib.redirect_stderr(captured_err), \
         contextlib.redirect_stdout(captured_out):
        try:
            result = main()
        except SystemExit as e:
            exc = e
    return result, captured_err.getvalue(), captured_out.getvalue(), exc


# ---------------------------------------------------------------------------
#  Happy-path dispatch — argparse accepts, COMMANDS dispatch fires
# ---------------------------------------------------------------------------

class TestArgparseAcceptedDispatch(unittest.TestCase):
    """Valid argv -> COMMANDS callback invoked with parsed kwargs."""

    def setUp(self):
        self.original_guard = os.environ.pop(AI_TOOLING_HOOK_RECURSION_GUARD, None)

    def tearDown(self):
        os.environ.pop(AI_TOOLING_HOOK_RECURSION_GUARD, None)
        if self.original_guard is not None:
            os.environ[AI_TOOLING_HOOK_RECURSION_GUARD] = self.original_guard

    def test_cache_prune_no_extra_args_dispatches(self):
        """'cache-prune' alone -> cmd_cache_prune() invoked, returns 0.

        reference-transaction stub no longer forwards "$@" — bare command
        must dispatch cleanly without argparse complaint.
        """
        mock_cmd = MagicMock(return_value=0)
        with patch('sys.argv', ['prog', 'cache-prune']), \
             patch('git_hooks_impl.entry_points.cli.signal.signal'), \
             patch.dict('git_hooks_impl.entry_points.cli.COMMANDS',
                        {'cache-prune': lambda a: mock_cmd()}):
            result = main()
        mock_cmd.assert_called_once_with()
        self.assertEqual(result, 0)

    def test_extract_plan_no_extra_args_dispatches(self):
        """'extract-plan' alone -> cmd_extract_plan(force=False) invoked.

        post-merge / post-rewrite stubs no longer forward "$@" — bare
        command must dispatch with force defaulted to False.
        """
        mock_cmd = MagicMock(return_value=0)
        with patch('sys.argv', ['prog', 'extract-plan']), \
             patch('git_hooks_impl.entry_points.cli.signal.signal'), \
             patch.dict('git_hooks_impl.entry_points.cli.COMMANDS',
                        {'extract-plan': lambda a: mock_cmd(force=a.force)}):
            result = main()
        mock_cmd.assert_called_once_with(force=False)
        self.assertEqual(result, 0)

    def test_extract_plan_force_flag_dispatches_with_force_true(self):
        """'extract-plan --force' -> cmd_extract_plan(force=True) invoked.

        --force is a real flag ('mr plangen --force');
        argparse must keep accepting it after the stub-cleanup MR.
        """
        mock_cmd = MagicMock(return_value=0)
        with patch('sys.argv', ['prog', 'extract-plan', '--force']), \
             patch('git_hooks_impl.entry_points.cli.signal.signal'), \
             patch.dict('git_hooks_impl.entry_points.cli.COMMANDS',
                        {'extract-plan': lambda a: mock_cmd(force=a.force)}):
            result = main()
        mock_cmd.assert_called_once_with(force=True)
        self.assertEqual(result, 0)

    def test_cache_swap_prev_ref_flag_dispatches_with_prev_ref(self):
        """'cache-swap --prev-ref refs/heads/main' -> cmd_cache_swap(prev_ref=...).

        post-checkout still forwards prev-ref via the named flag (kept,
        unlike "$@"). Argparse must keep accepting --prev-ref VALUE form.
        """
        mock_cmd = MagicMock(return_value=0)
        with patch('sys.argv', ['prog', 'cache-swap', '--prev-ref', 'refs/heads/main']), \
             patch('git_hooks_impl.entry_points.cli.signal.signal'), \
             patch.dict('git_hooks_impl.entry_points.cli.COMMANDS',
                        {'cache-swap': lambda a: mock_cmd(prev_ref=a.prev_ref)}):
            result = main()
        mock_cmd.assert_called_once_with(prev_ref='refs/heads/main')
        self.assertEqual(result, 0)


# ---------------------------------------------------------------------------
#  Argparse rejection — extra positionals blow up with SystemExit(2)
# ---------------------------------------------------------------------------

class TestArgparseRejectsExtraPositionals(unittest.TestCase):
    """Extra positional after a known command -> argparse exits 2.

    These tests pin the exact behavior the 5-stub fix relied on: argparse
    is strict about positional choices, so any stub that forwards extra
    git-hook args via "$@" produces 'unrecognized arguments' and a non-zero
    exit. Locking that in prevents future code from loosening argparse
    (e.g. nargs='*' on the command arg) and silently re-enabling the bug.
    """

    def setUp(self):
        self.original_guard = os.environ.pop(AI_TOOLING_HOOK_RECURSION_GUARD, None)

    def tearDown(self):
        os.environ.pop(AI_TOOLING_HOOK_RECURSION_GUARD, None)
        if self.original_guard is not None:
            os.environ[AI_TOOLING_HOOK_RECURSION_GUARD] = self.original_guard

    def test_cache_prune_extra_arg_raises_systemexit(self):
        """'cache-prune committed' -> SystemExit(2), 'unrecognized arguments' on stderr.

        Replicates the post-checkout regression: reference-transaction
        receives 'committed' on its third arg; forwarding it to argparse
        is the bug.
        """
        _, stderr_text, _, exc = _run_main_capturing_io(
            ['prog', 'cache-prune', 'committed'])
        self.assertIsNotNone(exc)
        self.assertEqual(exc.code, 2)
        self.assertIn('unrecognized arguments', stderr_text)

    def test_extract_plan_extra_arg_raises_systemexit(self):
        """'extract-plan rebase' -> SystemExit(2), 'unrecognized arguments'.

        Replicates the post-rewrite regression: post-rewrite hook receives
        'rebase' or 'amend' as $1; forwarding it to argparse is the bug.
        """
        _, stderr_text, _, exc = _run_main_capturing_io(
            ['prog', 'extract-plan', 'rebase'])
        self.assertIsNotNone(exc)
        self.assertEqual(exc.code, 2)
        self.assertIn('unrecognized arguments', stderr_text)

    def test_sync_mr_with_remote_args_raises_systemexit(self):
        """'sync-mr remote_name remote_url' -> SystemExit(2), 'unrecognized arguments'.

        Replicates the pre-push regression: pre-push receives the remote
        name and URL as positional args from git; forwarding them to
        argparse is the bug.
        """
        _, stderr_text, _, exc = _run_main_capturing_io(
            ['prog', 'sync-mr', 'remote_name', 'remote_url'])
        self.assertIsNotNone(exc)
        self.assertEqual(exc.code, 2)
        self.assertIn('unrecognized arguments', stderr_text)


# ---------------------------------------------------------------------------
#  Run all
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    unittest.main(verbosity=2)
