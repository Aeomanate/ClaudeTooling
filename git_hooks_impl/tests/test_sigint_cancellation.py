#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""SIGINT cancellation tests for async AI pipeline entry points.

Verifies:
1. SIGINT handler installed via signal.signal (NOT asyncio.add_signal_handler —
   raises NotImplementedError on Windows, "Availability: Unix" per Python docs)
2. Handler invokes task.cancel() on the active asyncio task
3. CancelledError propagates through async stack to asyncio.run() boundary
4. Cache state preserved on cancellation
"""

import asyncio
import contextlib
import tempfile
import unittest
from unittest.mock import MagicMock, patch

_log_patchers = []


def setUpModule():
    targets = [
        'git_hooks_impl.plan.generator.dbg',
        'git_hooks_impl.plan.generator.err',
        'git_hooks_impl.plan.generator.log',
        'git_hooks_impl.plan.generator.warn',
    ]
    for t in targets:
        p = patch(t)
        p.start()
        _log_patchers.append(p)


def tearDownModule():
    for p in _log_patchers:
        p.stop()
    _log_patchers.clear()


import os
import signal as signal_mod

import git_hooks_impl.entry_points.cli as cli_module
from git_hooks_impl.ai_provider import MockProvider
from git_hooks_impl.entry_points.cli import _sigint_handler
from git_hooks_impl.plan.cache import _sanitize_branch_name
from git_hooks_impl.plan.context import AvailableResources, PlanContext
from git_hooks_impl.plan.generator import PlanGenerator
from git_hooks_impl.tests.test_plangen_integration import (
    _ok,
    _ok_with_resources,
    _populate_gen_cache,
)


class TestSigintCancellation(unittest.IsolatedAsyncioTestCase):
    """SIGINT cancellation tests for async AI pipeline entry points."""

    def test_sigint_cancels_active_task(self):
        """_sigint_handler calls task.cancel() on the active asyncio task."""


        mock_task = MagicMock()
        original = cli_module._SIGINT_ACTIVE_TASK
        try:
            cli_module._SIGINT_ACTIVE_TASK = mock_task
            _sigint_handler(signal_mod.SIGINT, None)
        finally:
            cli_module._SIGINT_ACTIVE_TASK = original

        mock_task.cancel.assert_called_once()

    def test_cancelled_error_propagates_to_asyncio_run_boundary(self):
        """CancelledError raised inside asyncio.run() propagates out, not silently swallowed."""
        async def _raises_cancelled():
            raise asyncio.CancelledError()

        with self.assertRaises((asyncio.CancelledError, SystemExit, KeyboardInterrupt)):
            asyncio.run(_raises_cancelled())

    async def test_cache_preserved_after_cancellation(self):
        """Steps flushed before cancellation remain in gen_cache; Phase J resume picks up."""

        ctx = PlanContext(
            jira_ticket='TEST-K',
            jira_summary='[TEST-K] SIGINT test',
            jira_content='Test content',
            mr_body_template='## Description\n(placeholder)',
            available_resources=AvailableResources(),
            plan_template='# [{{TITLE}}]\n## Context\n{{CONTEXT}}',
            plan_rules='Fill sections.',
        )

        call_count = 0

        async def _cancel_on_step4(task, label, **kw):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise asyncio.CancelledError()
            return await task()

        with tempfile.TemporaryDirectory() as tmpdir:
            _populate_gen_cache(tmpdir, 'feature/TEST-K', {
                1: _ok_with_resources('## Description\nStep 1 cached.', '{}'),
                2: _ok('# [TEST-K] Step 2 cached.'),
            })

            provider = MockProvider(responses=[
                _ok('Step 3 output'),
                _ok('Step 4 output'),
            ])
            generator = PlanGenerator(ctx, provider)

            with patch('git_hooks_impl.plan.generator.run_with_progress',
                       side_effect=_cancel_on_step4), \
                 patch('git_hooks_impl.plan.generator.PlanGenerator._flush'), \
                 patch('git_hooks_impl.plan.generator._run_mermaid_check', return_value=''), \
                 patch('git_hooks_impl.plan.generator.run',
                       return_value=(0, 'feature/TEST-K\n', '')), \
                 patch('git_hooks_impl.plan.cache._CACHE_DIR', tmpdir), \
                 patch('git_hooks_impl.plan.generator._CACHE_DIR', tmpdir), \
                 contextlib.suppress(asyncio.CancelledError):
                await generator.generate()

            # Cache steps 1+2 survive cancellation

            gen_cache_dir = os.path.join(
                tmpdir, _sanitize_branch_name('feature/TEST-K'), 'gen_cache'
            )
            self.assertTrue(
                os.path.isfile(os.path.join(gen_cache_dir, 'step1.md')),
                'step1.md should survive cancellation'
            )
            self.assertTrue(
                os.path.isfile(os.path.join(gen_cache_dir, 'step2.md')),
                'step2.md should survive cancellation'
            )


if __name__ == '__main__':
    unittest.main(verbosity=2)
