#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for hooks/progress.py — run_with_progress spinner.
"""

import unittest
from unittest.mock import patch

from git_hooks_impl.progress import run_with_progress


def _acoro(val):
    """Wrap a value in a coroutine for async run_with_progress tasks."""
    async def _inner():
        return val
    return _inner


def _araise(exc):
    """Wrap an exception raise in a coroutine."""
    async def _inner():
        raise exc
    return _inner


# ---------------------------------------------------------------------------
#  run_with_progress
# ---------------------------------------------------------------------------

class TestRunWithProgressCallable(unittest.IsolatedAsyncioTestCase):
    """Verify callable task execution and result handling."""

    async def test_callable_returns_result(self):
        """Callable task -> returns whatever the callable returns."""
        with patch('git_hooks_impl.progress.time.time', return_value=100.0), \
             patch('git_hooks_impl.progress.sys.stderr'):
            result = await run_with_progress(_acoro('hello'), 'Test callable')
        self.assertEqual(result, 'hello')

    async def test_callable_exception_propagates(self):
        """Callable raises exception -> exception re-raised after cleanup."""
        with patch('git_hooks_impl.progress.time.time', return_value=100.0), \
             patch('git_hooks_impl.progress.sys.stderr'), \
             self.assertRaises(ValueError) as ctx:
            await run_with_progress(_araise(ValueError('task failed')), 'Failing task')
        self.assertIn('task failed', str(ctx.exception))


# ---------------------------------------------------------------------------
#  Run all
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    unittest.main(verbosity=2)
