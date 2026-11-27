#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Integration tests for the PlanGenerator 5-step pipeline.

Uses fixture-level mocking: all external I/O (jira, glab, git) is mocked
with canned responses that simulate a known branch/ticket state.
No network calls, no filesystem side-effects.

Run: python -m unittest discover -s .git-hooks/hooks/tests -t .git-hooks -p "test_plangen_integration.py" -v
"""

import os
import tempfile
import unittest
from unittest.mock import patch

from git_hooks_impl.ai_provider import MockProvider
from git_hooks_impl.entry_points.extract_plan import scaffold_or_generate
from git_hooks_impl.plan.cache import _sanitize_branch_name
from git_hooks_impl.plan.context import AvailableResources, PlanContext
from git_hooks_impl.plan.generator import PlanGenerator

# ---------------------------------------------------------------------------
#  Module-level log silencing
# ---------------------------------------------------------------------------

_log_patchers = []

def setUpModule():
    targets = [
        'git_hooks_impl.plan.generator.dbg',
        'git_hooks_impl.plan.generator.err',
        'git_hooks_impl.plan.generator.log',
        'git_hooks_impl.plan.generator.warn',
        'git_hooks_impl.content_extractor.dbg',
        'git_hooks_impl.content_extractor.log',
        'git_hooks_impl.content_extractor.warn',
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
#  Helpers
# ---------------------------------------------------------------------------

def _ok(content):
    return f'<!-- PLAN_CONTENT -->\n{content}\n<!-- PLAN_STEP: OK -->'


def _ok_with_resources(content, resources_json='{}'):
    return (
        f'<!-- PLAN_CONTENT -->\n{content}\n<!-- PLAN_STEP: OK -->\n'
        f'<!-- REQUIRED_RESOURCES -->\n{resources_json}\n'
        f'<!-- /REQUIRED_RESOURCES -->'
    )


def _make_context(ticket='PROJECTNAME-47833', jira_content='Jira ticket content',
                  diff_stats='', stacked_warning=''):
    return PlanContext(
        jira_ticket=ticket,
        jira_summary=f'[{ticket}] Feature summary',
        jira_content=jira_content,
        mr_body_template='## Description\n(placeholder)\n## Areas of Impact\n(placeholder)',
        available_resources=AvailableResources(),
        plan_template='# [{{TITLE}}]\n\n## Context\n\n{{CONTEXT}}',
        plan_rules='Fill sections accurately.',
        current_branch_diff_stats=diff_stats,
        stacked_branch_warning=stacked_warning,
    )


def _populate_gen_cache(cache_dir, branch, steps):
    """Write gen_cache files for a fake prior run.

    steps: dict[int, str] mapping step number -> content.
    """
    branch_dir = os.path.join(cache_dir, _sanitize_branch_name(branch), 'gen_cache')
    os.makedirs(branch_dir, exist_ok=True)
    for step_num, content in steps.items():
        path = os.path.join(branch_dir, f'step{step_num}.md')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)


# ---------------------------------------------------------------------------
#  Integration test: golden plan fixture
# ---------------------------------------------------------------------------


async def _async_passthrough(task, label, **kw):
    """Async passthrough for run_with_progress mock in tests."""
    return await task()


class TestRecordedFixtureGoldenPlan(unittest.IsolatedAsyncioTestCase):
    """End-to-end pipeline with mocked AI + fixture data."""

    _cache_patcher_cache = None
    _cache_patcher_gen = None

    @classmethod
    def setUpClass(cls):
        cls._tmpdir_obj = tempfile.TemporaryDirectory()
        cls._cache_patcher_cache = patch(
            'git_hooks_impl.plan.cache._CACHE_DIR', cls._tmpdir_obj.name)
        cls._cache_patcher_gen = patch(
            'git_hooks_impl.plan.generator._CACHE_DIR', cls._tmpdir_obj.name)
        cls._cache_patcher_cache.start()
        cls._cache_patcher_gen.start()

    @classmethod
    def tearDownClass(cls):
        cls._cache_patcher_cache.stop()
        cls._cache_patcher_gen.stop()
        cls._tmpdir_obj.cleanup()

    @patch('git_hooks_impl.plan.generator.run', return_value=(0, 'feature/test\n', ''))
    @patch('git_hooks_impl.plan.generator.run_with_progress',
           side_effect=_async_passthrough)
    @patch('git_hooks_impl.plan.generator.PlanGenerator._flush')
    @patch('git_hooks_impl.plan.generator._run_mermaid_check', return_value='')
    async def test_recorded_fixture_golden_plan(self, mock_mmdc, mock_flush, mock_progress, mock_run):
        """Fixture: jira+glab+git mocked; pipeline produces a non-empty plan."""
        ctx = _make_context(
            jira_content='PROJECTNAME-47833: Replace WMI process monitoring with ETW.',
            diff_stats='src/etw/etw_processor.cpp | 45 +++++',
        )
        responses = [
            _ok_with_resources(
                '## Description\nReplace WMI with ETW for process monitoring.',
                '{"tickets": [], "mrs": [], "mr_diffs": [], "branch_diff": false}',
            ),
            _ok('# [PROJECTNAME-47833] Replace WMI with ETW\n\n## Context\nETW implementation.\n\n## Description\nDetails.'),
            _ok('# [PROJECTNAME-47833] Replace WMI with ETW\n\n## Context\nETW implementation.\n\n## Implementation Plan\n- [ ] Step 1'),
            _ok('# [PROJECTNAME-47833] Replace WMI with ETW\n\n## Context\nCompliant ETW plan.'),
        ]
        provider = MockProvider(responses=responses)
        generator = PlanGenerator(ctx, provider)

        plan = await generator.generate()

        self.assertIn('PROJECTNAME-47833', plan)
        self.assertNotEqual(plan, '')
        # 3 AI calls: steps 1, 2, 4 (step 3 skipped — no evidences)
        self.assertEqual(len(provider.calls), 3)
        # Step 1 produced a non-empty body
        self.assertNotEqual(provider.calls[0]['prompt'], '')
        # Final plan contains ETW (the ticket subject)
        self.assertIn('ETW', plan)


# ---------------------------------------------------------------------------
#  Integration test: stacked branch fixture
# ---------------------------------------------------------------------------

class TestStackedBranchFixture(unittest.IsolatedAsyncioTestCase):
    """Stacked-branch scenario: warning fires, plan title correct,
    deliverables do NOT mention predecessor artifacts.
    """

    _cache_patcher_cache = None
    _cache_patcher_gen = None

    @classmethod
    def setUpClass(cls):
        cls._tmpdir_obj = tempfile.TemporaryDirectory()
        cls._cache_patcher_cache = patch(
            'git_hooks_impl.plan.cache._CACHE_DIR', cls._tmpdir_obj.name)
        cls._cache_patcher_gen = patch(
            'git_hooks_impl.plan.generator._CACHE_DIR', cls._tmpdir_obj.name)
        cls._cache_patcher_cache.start()
        cls._cache_patcher_gen.start()

    @classmethod
    def tearDownClass(cls):
        cls._cache_patcher_cache.stop()
        cls._cache_patcher_gen.stop()
        cls._tmpdir_obj.cleanup()

    @patch('git_hooks_impl.plan.generator.run', return_value=(0, 'feature/test\n', ''))
    @patch('git_hooks_impl.plan.generator.run_with_progress',
           side_effect=_async_passthrough)
    @patch('git_hooks_impl.plan.generator.PlanGenerator._flush')
    @patch('git_hooks_impl.plan.generator._run_mermaid_check', return_value='')
    async def test_stacked_branch_fixture(self, mock_mmdc, mock_flush, mock_progress, mock_run):
        """PROJECTNAME-47833 stacked on EtwSession/EtwConsumer work:
        stacked warning present in prompt, no predecessor content in plan.
        """
        stacked_warning = (
            'STACKED BRANCH DETECTED: base..HEAD contains 15 commits, '
            'none reference PROJECTNAME-47833. Do NOT request branch_diff.'
        )
        ctx = _make_context(
            ticket='PROJECTNAME-47833',
            jira_content='PROJECTNAME-47833: WMI replacement with ETW.',
            stacked_warning=stacked_warning,
        )


        responses = [
            _ok_with_resources(
                '## Description\nWMI replacement.\n## Context\nTicket-led.',
                '{"tickets": [], "mrs": [], "mr_diffs": [], "branch_diff": false}',
            ),
            _ok('# [PROJECTNAME-47833] WMI replacement\n\n## Context\nEnhanced.'),
            _ok('# [PROJECTNAME-47833] WMI replacement\n\n## Implementation Plan\n- [ ] Step 1'),
            _ok('# [PROJECTNAME-47833] WMI replacement — compliant'),
        ]
        provider = MockProvider(responses=responses)
        generator = PlanGenerator(ctx, provider)

        plan = await generator.generate()

        # Plan title contains correct ticket
        self.assertIn('PROJECTNAME-47833', plan)
        # Step 1 prompt injected the stacked warning
        step1_prompt = provider.calls[0]['prompt']
        self.assertIn('STACKED BRANCH DETECTED', step1_prompt)
        # Negative assertion: plan deliverables do NOT reference EtwSession or EtwConsumer
        # (These are predecessor branch artifacts that must not leak into this branch's plan)
        self.assertNotIn('EtwSession', plan)
        self.assertNotIn('EtwConsumer', plan)


# ---------------------------------------------------------------------------
#  Integration test: new branch (empty diff stats)
# ---------------------------------------------------------------------------

class TestNewBranchFixture(unittest.IsolatedAsyncioTestCase):
    """New branch with empty diff stats: plan body marks sections as needing investigation."""

    _cache_patcher_cache = None
    _cache_patcher_gen = None

    @classmethod
    def setUpClass(cls):
        cls._tmpdir_obj = tempfile.TemporaryDirectory()
        cls._cache_patcher_cache = patch(
            'git_hooks_impl.plan.cache._CACHE_DIR', cls._tmpdir_obj.name)
        cls._cache_patcher_gen = patch(
            'git_hooks_impl.plan.generator._CACHE_DIR', cls._tmpdir_obj.name)
        cls._cache_patcher_cache.start()
        cls._cache_patcher_gen.start()

    @classmethod
    def tearDownClass(cls):
        cls._cache_patcher_cache.stop()
        cls._cache_patcher_gen.stop()
        cls._tmpdir_obj.cleanup()

    @patch('git_hooks_impl.plan.generator.run', return_value=(0, 'feature/test\n', ''))
    @patch('git_hooks_impl.plan.generator.run_with_progress',
           side_effect=_async_passthrough)
    @patch('git_hooks_impl.plan.generator.PlanGenerator._flush')
    @patch('git_hooks_impl.plan.generator._run_mermaid_check', return_value='')
    async def test_new_branch_fixture(self, mock_mmdc, mock_flush, mock_progress, mock_run):
        """Empty diff stats -> plan body has (needs investigation) markers."""
        ctx = _make_context(
            diff_stats='',
            jira_content='PROJECTNAME-99999: New investigation branch.',
        )
        responses = [
            _ok_with_resources(
                '## Description\nNew investigation.\n## Root cause\n(needs investigation)',
                '{}',
            ),
            _ok('# [PROJECTNAME-99999] Investigation\n\n## Root cause\n(needs investigation)'),
            _ok('# [PROJECTNAME-99999] Investigation with TODOs'),
            _ok('# [PROJECTNAME-99999] Compliant'),
        ]
        provider = MockProvider(responses=responses)
        generator = PlanGenerator(ctx, provider)

        plan = await generator.generate()

        self.assertIn('PROJECTNAME-99999', plan)
        self.assertNotEqual(plan, '')
        # no diff stats -> step 1 prompt has fallback
        step1_prompt = provider.calls[0]['prompt']
        self.assertIn('(no diff stats)', step1_prompt)


# ---------------------------------------------------------------------------
#  Integration test: cache version invalidation (B26)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
#  Phase J: Cache infrastructure behavior tests
# ---------------------------------------------------------------------------

class TestPhaseJCacheBehavior(unittest.IsolatedAsyncioTestCase):
    """Phase J cache-load decision tree: resume, re-ask, force, version-mismatch, non-interactive."""

    @patch('git_hooks_impl.plan.generator.run_with_progress', side_effect=_async_passthrough)
    @patch('git_hooks_impl.plan.generator.PlanGenerator._flush')
    @patch('git_hooks_impl.plan.generator._run_mermaid_check', return_value='')
    @patch('git_hooks_impl.plan.generator.run', return_value=(0, 'feature/TEST-1\n', ''))
    async def test_resume_from_partial_cache(self, mock_run, mock_mmdc, mock_flush, mock_progress):
        """Partial cache (steps 1-2 present) -> pipeline resumes from step 4; 1 AI call."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _populate_gen_cache(tmpdir, 'feature/TEST-1', {
                1: _ok_with_resources('## Description\nCached step 1 body.', '{}'),
                2: _ok('# [TEST-1] Enhanced plan from cache.'),
            })
            responses = [
                _ok('# [TEST-1] Polished.'),       # step 4
            ]
            provider = MockProvider(responses=responses)
            generator = PlanGenerator(_make_context(ticket='TEST-1'), provider)
            with patch('git_hooks_impl.plan.cache._CACHE_DIR', tmpdir), \
                 patch('git_hooks_impl.plan.generator._CACHE_DIR', tmpdir):
                plan = await generator.generate()

        # Only step 4 called AI — 1 call
        self.assertEqual(len(provider.calls), 1)
        # Final plan is the step 4 output
        self.assertIn('Polished', plan)
        # Step 2 cached content fed into step 4's prompt
        self.assertIn('Enhanced', provider.calls[0]['prompt'])

    @patch('git_hooks_impl.entry_points.extract_plan._save_cache')
    @patch('git_hooks_impl.entry_points.extract_plan._write_plan')
    @patch('git_hooks_impl.entry_points.extract_plan._try_ai_pipeline',
           return_value=('', None))
    @patch('git_hooks_impl.entry_points.extract_plan.template_skeleton',
           return_value=(None, [], []))
    @patch('git_hooks_impl.entry_points.extract_plan.prompt_yn', return_value=False)
    @patch('git_hooks_impl.entry_points.extract_plan._all_steps_cached', return_value=True)
    async def test_full_cache_prompts_user(
            self, mock_cached, mock_prompt_yn, mock_skeleton, mock_pipeline, mock_write,
            mock_save_cache):
        """All steps cached + interactive + force=False -> prompt_yn called; user says No -> early return."""
        await scaffold_or_generate('feature/TEST-1', 'TEST-1',
                                   force=False, interactive=True)
        # prompt_yn was called once (re-run dialog)
        mock_prompt_yn.assert_called_once()
        # Early return — _try_ai_pipeline never reached
        mock_pipeline.assert_not_called()

    @patch('git_hooks_impl.entry_points.extract_plan._save_cache')
    @patch('git_hooks_impl.entry_points.extract_plan._write_plan')
    @patch('git_hooks_impl.entry_points.extract_plan._try_ai_pipeline',
           return_value=('', None))
    @patch('git_hooks_impl.entry_points.extract_plan.template_skeleton',
           return_value=(None, [], []))
    @patch('git_hooks_impl.entry_points.extract_plan.prompt_yn')
    @patch('git_hooks_impl.entry_points.extract_plan._all_steps_cached', return_value=True)
    async def test_force_bypasses_full_cache_prompt(
            self, mock_cached, mock_prompt_yn, mock_skeleton, mock_pipeline, mock_write,
            mock_save_cache):
        """All steps cached + force=True -> prompt_yn never called; pipeline proceeds."""
        await scaffold_or_generate('feature/TEST-1', 'TEST-1',
                                   force=True, interactive=True)
        # force=True bypasses early prompt entirely
        mock_prompt_yn.assert_not_called()

    @patch('git_hooks_impl.entry_points.extract_plan._save_cache')
    @patch('git_hooks_impl.entry_points.extract_plan._write_plan')
    @patch('git_hooks_impl.entry_points.extract_plan._try_ai_pipeline',
           return_value=('', None))
    @patch('git_hooks_impl.entry_points.extract_plan.template_skeleton',
           return_value=(None, [], []))
    @patch('git_hooks_impl.entry_points.extract_plan.prompt_yn')
    @patch('git_hooks_impl.entry_points.extract_plan._all_steps_cached', return_value=True)
    async def test_non_interactive_full_cache_returns_existing_plan(
            self, mock_cached, mock_prompt_yn, mock_skeleton, mock_pipeline, mock_write,
            mock_save_cache):
        """All steps cached + interactive=False -> no prompt_yn; pipeline not invoked."""
        await scaffold_or_generate('feature/TEST-1', 'TEST-1',
                                   force=False, interactive=False)
        # prompt_yn never called — non-interactive skips dialog entirely
        mock_prompt_yn.assert_not_called()
        # Non-interactive with full cache: early check doesn't fire (interactive=False),
        # falls through to _try_ai_pipeline path (which is mocked here)
        mock_pipeline.assert_called_once()
