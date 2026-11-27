#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for plan_generator.py — 5-step AI pipeline.

Run: python -m unittest discover -s .git-hooks/hooks/tests -t .git-hooks -p "test_plan_generator.py" -v
"""

import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from git_hooks_impl.ai_provider import MockProvider
from git_hooks_impl.plan.context import AvailableResources, Evidence, PlanContext
from git_hooks_impl.plan.generator import (
    PlanGenerator,
    _extract_content,
    _extract_required_resources,
    _format_evidence_block,
)

# ---------------------------------------------------------------------------
#  Module-level log silencing — prevent TESTS.log pollution
# ---------------------------------------------------------------------------

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


def _ok(content):
    """Wrap content in quality gate tags."""
    return f'<!-- PLAN_CONTENT -->\n{content}\n<!-- PLAN_STEP: OK -->'


def _ok_with_resources(content, resources_json='{}'):
    """Wrap content + REQUIRED_RESOURCES."""
    return (
        f'<!-- PLAN_CONTENT -->\n{content}\n<!-- PLAN_STEP: OK -->\n'
        f'<!-- REQUIRED_RESOURCES -->\n{resources_json}\n'
        f'<!-- /REQUIRED_RESOURCES -->'
    )



async def _async_passthrough(task, label, **kw):
    """Async passthrough for run_with_progress mock in tests."""
    return await task()


class TestExtractContent(unittest.TestCase):
    """Parse quality gate tags from AI response."""

    def test_extracts_between_markers(self):
        """Content between PLAN_CONTENT and PLAN_STEP: OK extracted."""
        self.assertEqual(_extract_content(_ok('# Plan')), '# Plan')

    def test_strips_whitespace(self):
        """Leading/trailing whitespace stripped."""
        response = '<!-- PLAN_CONTENT -->\n  # Plan  \n<!-- PLAN_STEP: OK -->'
        self.assertEqual(_extract_content(response), '# Plan')

    def test_abort_returns_empty(self):
        """PLAN_STEP: ABORT -> ''."""
        response = '<!-- PLAN_STEP: ABORT | no context -->'
        self.assertEqual(_extract_content(response), '')

    def test_no_markers_returns_empty(self):
        """No quality gate markers -> ''."""
        self.assertEqual(_extract_content('just text'), '')

    def test_fallback_without_start_marker(self):
        """No PLAN_CONTENT but has OK tag -> content before OK."""
        response = '# Plan content\n<!-- PLAN_STEP: OK -->'
        self.assertEqual(_extract_content(response), '# Plan content')


class TestExtractRequiredResources(unittest.TestCase):
    """Parse REQUIRED_RESOURCES JSON from step 1."""

    def test_parses_json(self):
        """Valid JSON between tags -> dict."""
        response = _ok_with_resources('body', '{"jira_tickets": ["PROJ-1"]}')
        result = _extract_required_resources(response)
        self.assertEqual(result['jira_tickets'], ['PROJ-1'])

    def test_no_tags_returns_empty(self):
        """No REQUIRED_RESOURCES tags -> {}."""
        self.assertEqual(_extract_required_resources(_ok('body')), {})

    def test_malformed_json_returns_empty(self):
        """Bad JSON -> {}."""
        response = '<!-- REQUIRED_RESOURCES -->\nnot json\n<!-- /REQUIRED_RESOURCES -->'
        self.assertEqual(_extract_required_resources(response), {})


class TestPlanGeneratorPipeline(unittest.IsolatedAsyncioTestCase):
    """Full pipeline with MockProvider."""

    _cache_patcher = None
    _tmpdir_obj = None

    @classmethod
    def setUpClass(cls):
        cls._tmpdir_obj = tempfile.TemporaryDirectory()
        cls._cache_patcher = patch(
            'git_hooks_impl.plan.cache._CACHE_DIR', cls._tmpdir_obj.name)
        cls._cache_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._cache_patcher.stop()
        cls._tmpdir_obj.cleanup()

    def _make_context(self):
        return PlanContext(
            jira_ticket='PROJ-100',
            jira_summary='Fix the bug',
            jira_content='Bug description from Jira',
            mr_body_template='## Bug\n(placeholder)',
            available_resources=AvailableResources(),
            plan_template='# [{{TITLE}}]\n## Context\n## Description',
            plan_rules='Fill each section with relevant content.',
        )

    @patch('git_hooks_impl.plan.generator.PlanGenerator._save_prompt_cache')
    @patch('git_hooks_impl.plan.generator.run', return_value=(0, 'feature/proj-100\n', ''))
    @patch('git_hooks_impl.plan.generator.run_with_progress', side_effect=_async_passthrough)
    @patch('git_hooks_impl.plan.generator._load_prompt', return_value='prompt text')
    @patch('git_hooks_impl.plan.generator.PlanGenerator._flush')
    async def test_4_step_pipeline(self, mock_flush, mock_load_prompt, mock_progress, mock_run,
                              mock_save_prompt_cache):
        """Full pipeline -> 4 AI calls (no evidence): steps 1, 2, 4."""
        responses = [
            _ok_with_resources('## Bug\nFilled body'),
            _ok('# Plan\n## Context\nEnhanced'),
            _ok('# Plan\n## Context\nPolished.'),
        ]
        provider = MockProvider(responses=responses)
        context = self._make_context()

        generator = PlanGenerator(context, provider)
        result = await generator.generate()

        # Steps 1, 2, 4 (step 3 skipped — no evidences)
        self.assertEqual(len(provider.calls), 3)
        self.assertIn('Polished', result)

    @patch('git_hooks_impl.plan.generator.PlanGenerator._save_prompt_cache')
    @patch('git_hooks_impl.plan.generator.run', return_value=(0, 'feature/proj-100\n', ''))
    @patch('git_hooks_impl.plan.generator.run_with_progress', side_effect=_async_passthrough)
    @patch('git_hooks_impl.plan.generator._load_prompt', return_value='prompt text')
    @patch('git_hooks_impl.plan.generator.PlanGenerator._flush')
    async def test_step3_skipped_without_evidence(self, mock_flush, mock_load_prompt,
                                             mock_progress, mock_run, mock_save_prompt_cache):
        """No evidences downloaded -> step 3 skipped."""
        responses = [
            _ok_with_resources('body'),
            _ok('enhanced plan'),
            _ok('with investigation'),
            _ok('polished'),
        ]
        provider = MockProvider(responses=responses)
        generator = PlanGenerator(self._make_context(), provider)
        await generator.generate()

        # 3 calls: step 1, 2, 4 (no step 3)
        self.assertEqual(len(provider.calls), 3)

    @patch('git_hooks_impl.plan.generator.PlanGenerator._save_prompt_cache')
    @patch('git_hooks_impl.plan.generator.run', return_value=(0, 'feature/proj-100\n', ''))
    @patch('git_hooks_impl.plan.generator.run_with_progress', side_effect=_async_passthrough)
    @patch('git_hooks_impl.plan.generator._load_prompt', return_value='prompt text')
    @patch('git_hooks_impl.plan.generator.PlanGenerator._flush')
    async def test_step3_batch_with_evidence(self, mock_flush, mock_load_prompt,
                                        mock_progress, mock_run, mock_save_prompt_cache):
        """Evidence present -> step 3 runs (4 total calls)."""
        responses = [
            _ok_with_resources('body'),
            _ok('enhanced'),
            _ok('enriched with evidence'),
            _ok('polished'),
        ]
        provider = MockProvider(responses=responses)
        generator = PlanGenerator(self._make_context(), provider)
        generator.evidences = [
            Evidence(source_type='jira_ticket', source_id='PROJ-123',
                     title='Linked', relation='clones',
                     mentioned_in='PROJ-100', content='linked content'),
        ]
        result = await generator.generate()

        # 4 calls: step 1, 2, 3, 4
        self.assertEqual(len(provider.calls), 4)
        self.assertIn('polished', result)

    @patch('git_hooks_impl.plan.generator.PlanGenerator._save_prompt_cache')
    @patch('git_hooks_impl.plan.generator.run', return_value=(0, 'feature/proj-100\n', ''))
    @patch('git_hooks_impl.plan.generator.run_with_progress', side_effect=_async_passthrough)
    @patch('git_hooks_impl.plan.generator._load_prompt', return_value='prompt text')
    @patch('git_hooks_impl.plan.generator.PlanGenerator._flush')
    async def test_step1_failure_aborts(self, mock_flush, mock_load_prompt,
                                   mock_progress, mock_run, mock_save_prompt_cache):
        """Step 1 fails -> empty result, no further steps."""
        provider = MockProvider(responses=['<!-- PLAN_STEP: ABORT | no data -->'])
        generator = PlanGenerator(self._make_context(), provider)
        result = await generator.generate()

        self.assertEqual(result, '')
        self.assertEqual(len(provider.calls), 1)

    @patch('git_hooks_impl.plan.generator.PlanGenerator._save_prompt_cache')
    @patch('git_hooks_impl.plan.generator.run', return_value=(0, 'feature/proj-100\n', ''))
    @patch('git_hooks_impl.plan.generator.run_with_progress', side_effect=_async_passthrough)
    @patch('git_hooks_impl.plan.generator._load_prompt', return_value='prompt text')
    @patch('git_hooks_impl.plan.generator.PlanGenerator._flush')
    async def test_step2_failure_aborts_pipeline(self, mock_flush, mock_load_prompt,
                                            mock_progress, mock_run, mock_save_prompt_cache):
        """Step 2 fails -> pipeline aborts, generate() returns ''."""
        responses = [
            _ok_with_resources('good body'),
            '',  # step 2 fails (empty)
        ]
        provider = MockProvider(responses=responses)
        generator = PlanGenerator(self._make_context(), provider)
        result = await generator.generate()

        self.assertEqual(result, '')

    @patch('git_hooks_impl.plan.generator.PlanGenerator._save_prompt_cache')
    @patch('git_hooks_impl.plan.generator.PlanGenerator._flush')
    async def test_provider_unavailable_returns_empty(self, mock_flush, mock_save_prompt_cache):
        """Provider not available -> '' immediately."""
        provider = MockProvider()
        provider.is_available = lambda: False
        generator = PlanGenerator(self._make_context(), provider)
        result = await generator.generate()
        self.assertEqual(result, '')

    @patch('git_hooks_impl.plan.generator.PlanGenerator._save_prompt_cache')
    @patch('git_hooks_impl.plan.generator.run', return_value=(0, 'feature/proj-100\n', ''))
    @patch('git_hooks_impl.plan.generator.run_with_progress', side_effect=_async_passthrough)
    @patch('git_hooks_impl.plan.generator._load_prompt', return_value='prompt text')
    @patch('git_hooks_impl.plan.generator.PlanGenerator._flush')
    async def test_flush_called_after_each_step(self, mock_flush, mock_load_prompt,
                                           mock_progress, mock_run, mock_save_prompt_cache):
        """Each step flushes to disk."""
        responses = [
            _ok_with_resources('body'),
            _ok('enhanced'),
            _ok('investigated'),
            _ok('polished'),
        ]
        provider = MockProvider(responses=responses)
        generator = PlanGenerator(self._make_context(), provider)
        await generator.generate()

        # Steps 1, 2, 4 (no step 3 = no evidence)
        step_numbers = [call.args[1] for call in mock_flush.call_args_list]
        self.assertEqual(step_numbers, [1, 2, 4])


class TestFormatEvidenceBlock(unittest.TestCase):
    """_format_evidence_block — three branches: content, image, header-only."""

    def test_content_branch(self):
        """Evidence with content -> header + Content section."""
        ev = Evidence(
            source_type='jira_ticket', source_id='PROJ-1',
            title='Bug fix', relation='clones',
            mentioned_in='PROJ-2', content='Some text content',
        )
        result = _format_evidence_block(ev)
        self.assertIn('Source: jira_ticket PROJ-1', result)
        self.assertIn('Content:\nSome text content', result)

    def test_image_branch(self):
        """Evidence with image_bytes but no content -> image placeholder."""
        ev = Evidence(
            source_type='image', source_id='screenshot.png',
            title='Screenshot', relation='attachment',
            mentioned_in='PROJ-2',
            image_bytes=b'\x89PNG\r\n', mime_type='image/png',
        )
        result = _format_evidence_block(ev)
        self.assertIn('Source: image screenshot.png', result)
        self.assertIn('[Image — passed separately via multimodal]', result)
        self.assertNotIn('Content:', result)

    def test_header_only_fallback(self):
        """Evidence with neither content nor image -> header only."""
        ev = Evidence(
            source_type='gitlab_mr', source_id='!456',
            title='MR title', relation='mentioned',
            mentioned_in='PROJ-3',
        )
        result = _format_evidence_block(ev)
        self.assertIn('Source: gitlab_mr !456', result)
        self.assertIn('Title: MR title', result)
        self.assertNotIn('Content:', result)
        self.assertNotIn('[Image', result)


class TestStep3Loop(unittest.IsolatedAsyncioTestCase):
    """_step3_loop — evidence-by-evidence enrichment when over batch threshold."""

    def _make_context(self):
        return PlanContext(
            jira_ticket='PROJ-100',
            jira_summary='Fix the bug',
            jira_content='Bug description from Jira',
            mr_body_template='## Bug\n(placeholder)',
            available_resources=AvailableResources(),
            plan_template='# Plan',
            plan_rules='rules',
        )

    @patch('git_hooks_impl.plan.generator.PlanGenerator._save_prompt_cache')
    @patch('git_hooks_impl.plan.generator.run_with_progress', side_effect=_async_passthrough)
    @patch('git_hooks_impl.plan.generator._load_prompt', return_value='prompt {{PLAN}} {{EVIDENCE_BLOCKS}} {{AVAILABLE_EVIDENCE}}')
    async def test_loop_iterates_each_text_evidence(self, mock_load_prompt, mock_progress,
                                               mock_save_prompt_cache):
        """Two text evidences -> two AI calls, plan updated on each success."""
        provider = MockProvider(responses=[
            _ok('plan after evidence 1'),
            _ok('plan after evidence 2'),
        ])
        generator = PlanGenerator(self._make_context(), provider)

        text_evidences = [
            Evidence(source_type='jira_ticket', source_id='PROJ-1',
                     title='E1', relation='clones',
                     mentioned_in='PROJ-100', content='content 1'),
            Evidence(source_type='jira_ticket', source_id='PROJ-2',
                     title='E2', relation='blocks',
                     mentioned_in='PROJ-100', content='content 2'),
        ]
        result = await generator._step3_loop('initial plan', text_evidences, [])

        self.assertEqual(len(provider.calls), 2)
        self.assertEqual(result, 'plan after evidence 2')
        # Both calls should be text calls
        self.assertTrue(all(c['type'] == 'text' for c in provider.calls))

    @patch('git_hooks_impl.plan.generator.PlanGenerator._save_prompt_cache')
    @patch('git_hooks_impl.plan.generator.run_with_progress', side_effect=_async_passthrough)
    @patch('git_hooks_impl.plan.generator._load_prompt', return_value='prompt {{PLAN}} {{EVIDENCE_BLOCKS}} {{AVAILABLE_EVIDENCE}}')
    async def test_loop_uses_vision_for_image_evidence(self, mock_load_prompt, mock_progress,
                                                   mock_save_prompt_cache):
        """Image evidence -> vision call with image data."""
        provider = MockProvider(responses=[_ok('plan with image')])
        generator = PlanGenerator(self._make_context(), provider)

        image_evidences = [
            Evidence(source_type='image', source_id='shot.png',
                     title='Screenshot', relation='attachment',
                     mentioned_in='PROJ-100',
                     image_bytes=b'\x89PNG', mime_type='image/png'),
        ]
        result = await generator._step3_loop('initial plan', [], image_evidences)

        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(provider.calls[0]['type'], 'vision')
        self.assertEqual(result, 'plan with image')

    @patch('git_hooks_impl.plan.generator.PlanGenerator._save_prompt_cache')
    @patch('git_hooks_impl.plan.generator.run_with_progress', side_effect=_async_passthrough)
    @patch('git_hooks_impl.plan.generator._load_prompt', return_value='prompt {{PLAN}} {{EVIDENCE_BLOCKS}} {{AVAILABLE_EVIDENCE}}')
    async def test_loop_aborts_on_failed_evidence(self, mock_load_prompt, mock_progress,
                                             mock_save_prompt_cache):
        """Evidence producing empty result -> loop aborts, returns ''."""
        provider = MockProvider(responses=[
            '',                         # first evidence fails
            _ok('plan after second'),   # never reached
        ])
        generator = PlanGenerator(self._make_context(), provider)

        text_evidences = [
            Evidence(source_type='jira_ticket', source_id='PROJ-1',
                     title='E1', relation='clones',
                     mentioned_in='PROJ-100', content='c1'),
            Evidence(source_type='jira_ticket', source_id='PROJ-2',
                     title='E2', relation='blocks',
                     mentioned_in='PROJ-100', content='c2'),
        ]
        result = await generator._step3_loop('original plan', text_evidences, [])

        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(result, '')

    @patch('git_hooks_impl.plan.generator.PlanGenerator._save_prompt_cache')
    @patch('git_hooks_impl.plan.generator.run_with_progress', side_effect=_async_passthrough)
    @patch('git_hooks_impl.plan.generator._load_prompt', return_value='prompt {{PLAN}} {{EVIDENCE_BLOCKS}} {{AVAILABLE_EVIDENCE}}')
    async def test_loop_mixed_text_and_image(self, mock_load_prompt, mock_progress,
                                        mock_save_prompt_cache):
        """Text + image evidences -> text call then vision call."""
        provider = MockProvider(responses=[
            _ok('after text'),
            _ok('after image'),
        ])
        generator = PlanGenerator(self._make_context(), provider)

        text_ev = [Evidence(source_type='jira_ticket', source_id='T-1',
                            title='T', relation='r', mentioned_in='X',
                            content='text')]
        image_ev = [Evidence(source_type='image', source_id='img.png',
                             title='I', relation='r', mentioned_in='X',
                             image_bytes=b'\x89PNG', mime_type='image/png')]

        result = await generator._step3_loop('plan', text_ev, image_ev)

        self.assertEqual(provider.calls[0]['type'], 'text')
        self.assertEqual(provider.calls[1]['type'], 'vision')
        self.assertEqual(result, 'after image')


class TestDownloadInBackground(unittest.IsolatedAsyncioTestCase):
    """_wait_for_download — async polling wrapper that delegates to _download_worker_async."""

    def _make_context(self):
        return PlanContext(
            jira_ticket='PROJ-100',
            jira_summary='Fix the bug',
            jira_content='Bug description',
            mr_body_template='template',
            available_resources=AvailableResources(),
            plan_template='# Plan',
            plan_rules='rules',
        )

    @patch('git_hooks_impl.plan.generator.PlanGenerator._download_worker_async',
           new_callable=AsyncMock, return_value=None)
    async def test_populates_evidences_from_extractor(self, mock_worker):
        """Extractor provided -> _download_worker_async called once."""
        mock_extractor = MagicMock()
        mock_extractor.parse_required_resources.return_value = [
            ('jira_ticket', 'PROJ-1'),
        ]

        provider = MockProvider()
        generator = PlanGenerator(self._make_context(), provider,
                                  extractor=mock_extractor)

        required = {'jira_tickets': ['PROJ-1']}
        await generator._wait_for_download(required)

        mock_worker.assert_called_once()

    @patch('git_hooks_impl.plan.generator.PlanGenerator._download_worker_async',
           new_callable=AsyncMock, return_value=None)
    async def test_no_extractor_skips_worker(self, mock_worker):
        """No extractor -> _download_worker_async still called (guard is inside worker)."""
        provider = MockProvider()
        generator = PlanGenerator(self._make_context(), provider, extractor=None)
        required = {'jira_tickets': ['X-1']}
        await generator._wait_for_download(required)
        mock_worker.assert_called_once()


class TestFlush(unittest.TestCase):
    """_flush — writes plan to disk + gen_cache."""

    def _make_context(self):
        return PlanContext(
            jira_ticket='PROJ-100',
            jira_summary='Fix the bug',
            jira_content='Bug description',
            mr_body_template='template',
            available_resources=AvailableResources(),
            plan_template='# Plan',
            plan_rules='rules',
        )

    @patch('git_hooks_impl.plan.generator.run', return_value=(0, 'feature/my-branch\n', ''))
    def test_writes_plan_and_cache(self, mock_run):
        """Flush writes PLAN.md and gen_cache/stepN.md."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_file = os.path.join(tmpdir, '.ai', 'PLAN.md')

            provider = MockProvider()
            generator = PlanGenerator(self._make_context(), provider,
                                      plan_file=plan_file)

            with patch('git_hooks_impl.plan.generator._CACHE_DIR', tmpdir):
                generator._flush('# My Plan', 2)

            # PLAN.md written
            self.assertTrue(os.path.isfile(plan_file))
            with open(plan_file, encoding='utf-8') as f:
                self.assertIn('# My Plan', f.read())

            # gen_cache written
            # _sanitize_branch_name: '/' -> '_', lowercase, strip non-alnum/_
            sanitized = 'feature_mybranch'
            cache_step = os.path.join(tmpdir, sanitized, 'gen_cache', 'step2.md')
            self.assertTrue(os.path.isfile(cache_step))
            with open(cache_step, encoding='utf-8') as f:
                self.assertIn('# My Plan', f.read())

    @patch('git_hooks_impl.plan.generator.run', return_value=(0, 'feature/my-branch\n', ''))
    def test_preserves_existing_meta(self, mock_run):
        """Flush preserves meta block from existing PLAN.md on disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_file = os.path.join(tmpdir, '.ai', 'PLAN.md')
            os.makedirs(os.path.dirname(plan_file), exist_ok=True)

            # Write existing plan with meta block
            with open(plan_file, 'w', encoding='utf-8') as f:
                f.write('<!-- meta\nplan-hash: abc123\n-->\n# Old Plan\n')

            provider = MockProvider()
            generator = PlanGenerator(self._make_context(), provider,
                                      plan_file=plan_file)

            with patch('git_hooks_impl.plan.generator._CACHE_DIR', tmpdir):
                generator._flush('# New Plan', 3)

            with open(plan_file, encoding='utf-8') as f:
                content = f.read()
            # Meta block should be preserved in the output
            self.assertIn('plan-hash', content)
            self.assertIn('# New Plan', content)

    @patch('git_hooks_impl.plan.generator.run', return_value=(1, '', 'not a git repo'))
    def test_cache_skipped_on_git_failure(self, mock_run):
        """Git rev-parse fails -> cache not written, PLAN.md still written."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_file = os.path.join(tmpdir, '.ai', 'PLAN.md')

            provider = MockProvider()
            generator = PlanGenerator(self._make_context(), provider,
                                      plan_file=plan_file)

            with patch('git_hooks_impl.plan.generator._CACHE_DIR', tmpdir):
                generator._flush('# Plan', 1)

            # PLAN.md still written
            self.assertTrue(os.path.isfile(plan_file))
            # No gen_cache subdirectories created
            entries = [e for e in os.listdir(tmpdir)
                       if os.path.isdir(os.path.join(tmpdir, e))
                       and e != '.ai']
            self.assertEqual(entries, [])


class TestSavePromptCache(unittest.TestCase):
    """_save_prompt_cache — writes the exact prompt sent to the model to gen_cache/."""

    def _make_context(self):
        return PlanContext(
            jira_ticket='PROJ-100',
            jira_summary='Fix the bug',
            jira_content='Bug description',
            mr_body_template='template',
            available_resources=AvailableResources(),
            plan_template='# Plan',
            plan_rules='rules',
        )

    @patch('git_hooks_impl.plan.generator.run', return_value=(0, 'feature/my-branch\n', ''))
    def test_writes_prompt_to_step_file(self, mock_run):
        """Label with 'Step N/' -> writes gen_cache/stepN_prompt.md with prompt text."""
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = MockProvider()
            generator = PlanGenerator(self._make_context(), provider)

            with patch('git_hooks_impl.plan.generator._CACHE_DIR', tmpdir):
                generator._save_prompt_cache('Step 2/4: Enhancing plan...', 'some prompt text')

            sanitized = 'feature_mybranch'
            cache_path = os.path.join(tmpdir, sanitized, 'gen_cache', 'step2_prompt.md')
            self.assertTrue(os.path.isfile(cache_path))
            with open(cache_path, encoding='utf-8') as f:
                self.assertEqual(f.read(), 'some prompt text')

    @patch('git_hooks_impl.plan.generator.run', return_value=(0, 'feature/my-branch\n', ''))
    def test_image_count_adds_header(self, mock_run):
        """image_count set -> file content starts with images-attached header."""
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = MockProvider()
            generator = PlanGenerator(self._make_context(), provider)

            with patch('git_hooks_impl.plan.generator._CACHE_DIR', tmpdir):
                generator._save_prompt_cache(
                    'Step 3/4: Enriching (batch)...', 'prompt text', image_count=2)

            sanitized = 'feature_mybranch'
            cache_path = os.path.join(tmpdir, sanitized, 'gen_cache', 'step3_prompt.md')
            with open(cache_path, encoding='utf-8') as f:
                content = f.read()
            self.assertTrue(content.startswith('<!-- 2 images attached -->\n'))

    @patch('git_hooks_impl.plan.generator.run', return_value=(0, 'feature/my-branch\n', ''))
    def test_label_without_step_pattern_is_noop(self, mock_run):
        """Label with no 'Step N/' pattern -> no file written, no exception."""
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = MockProvider()
            generator = PlanGenerator(self._make_context(), provider)

            with patch('git_hooks_impl.plan.generator._CACHE_DIR', tmpdir):
                generator._save_prompt_cache('Some label without step marker', 'prompt text')

            entries = os.listdir(tmpdir)
            self.assertEqual(entries, [])

    @patch('git_hooks_impl.plan.generator.run', return_value=(1, '', 'not a git repo'))
    def test_git_failure_is_noop(self, mock_run):
        """Git rev-parse failure -> no file written, no exception."""
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = MockProvider()
            generator = PlanGenerator(self._make_context(), provider)

            with patch('git_hooks_impl.plan.generator._CACHE_DIR', tmpdir):
                generator._save_prompt_cache('Step 1/4: Filling MR body...', 'prompt text')

            entries = os.listdir(tmpdir)
            self.assertEqual(entries, [])

    @patch('git_hooks_impl.plan.generator.run', return_value=(0, 'feature/my-branch\n', ''))
    def test_oserror_on_write_is_swallowed(self, mock_run):
        """OSError while writing the prompt file -> swallowed, no exception propagates."""
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = MockProvider()
            generator = PlanGenerator(self._make_context(), provider)

            with patch('git_hooks_impl.plan.generator._CACHE_DIR', tmpdir), \
                 patch('builtins.open', side_effect=OSError('disk full')):
                generator._save_prompt_cache('Step 1/4: Filling MR body...', 'prompt text')
            # No exception raised — test passes by reaching this point.
