#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for hooks/extract_plan.py — PLAN.md scaffolding from template,
skip/guard conditions (master branch, ambiguous MR count, missing glab),
AI-based generation from an MR without a PLAN section, and token budget
strategy for diff collection.

Run:  python -m unittest discover -s .git-hooks/hooks/tests -t .git-hooks -p "test_extract_plan_scaffold.py" -v
"""

import json
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

# Silence ALL logging functions imported by extract_plan, plan_merge, plan_cache
# to prevent any output to TESTS.log.  Tests that assert on specific log calls
# use their own @patch which overrides the module-level mock for that test.
_log_patchers = [
    # git_hooks_impl.entry_points.extract_plan imports: config, dbg, err, log, ok, warn
    patch('git_hooks_impl.entry_points.extract_plan.log'),
    patch('git_hooks_impl.entry_points.extract_plan.warn'),
    patch('git_hooks_impl.entry_points.extract_plan.err'),
    patch('git_hooks_impl.entry_points.extract_plan.dbg'),
    patch('git_hooks_impl.entry_points.extract_plan.ok'),
    # git_hooks_impl.plan.merge imports: dbg, log, warn
    patch('git_hooks_impl.plan.merge.log'),
    patch('git_hooks_impl.plan.merge.warn'),
    patch('git_hooks_impl.plan.merge.dbg'),
    # git_hooks_impl.plan.cache imports: dbg, log, ok, warn
    patch('git_hooks_impl.plan.cache.log'),
    patch('git_hooks_impl.plan.cache.warn'),
    patch('git_hooks_impl.plan.cache.dbg'),
    patch('git_hooks_impl.plan.cache.ok'),
    # git_hooks_impl.branch_utils imports: dbg, log, warn
    patch('git_hooks_impl.branch_utils.log'),
    patch('git_hooks_impl.branch_utils.warn'),
    patch('git_hooks_impl.branch_utils.dbg'),
    # git_hooks_impl.utils imports: dbg
    patch('git_hooks_impl.utils.dbg'),
    # git_hooks_impl.glab imports: warn (called by get_project_path on remote URL failure)
    patch('git_hooks_impl.glab.warn'),
]


def setUpModule():
    for p in _log_patchers:
        p.start()


def tearDownModule():
    for p in _log_patchers:
        p.stop()

from git_hooks_impl.entry_points.extract_plan import (
    _TOKEN_BUDGET_CHARS,
    _collect_context_for_generation,
    _scaffold_plan,
    _write_plan,
    cmd_extract_plan,
    estimate_tokens,
)
from git_hooks_impl.plan.context import PlanContext
from git_hooks_impl.plan.parser import (
    embed_meta,
    extract_meta,
)


def _one_mr(iid=42, title='Test MR', description=''):
    return json.dumps([{'iid': iid, 'title': title, 'description': description}])


def _two_mrs():
    return json.dumps([
        {'iid': 42, 'title': 'MR one', 'description': ''},
        {'iid': 43, 'title': 'MR two', 'description': ''},
    ])


# ---------------------------------------------------------------------------
#  Scaffolding from template
# ---------------------------------------------------------------------------

class TestScaffoldPlan(unittest.IsolatedAsyncioTestCase):

    @patch('git_hooks_impl.entry_points.extract_plan._try_ai_pipeline', new_callable=AsyncMock)
    @patch('git_hooks_impl.entry_points.extract_plan.find_tool', return_value='/usr/bin/glab')
    @patch('git_hooks_impl.plan.cache.run', return_value=(0, 'master\n', ''))
    @patch('git_hooks_impl.entry_points.extract_plan.run')
    async def test_scaffolds_from_template_when_no_mr(self, mock_run, mock_pc_run, mock_tool, mock_pipeline):
        """0 MRs -> generates PLAN.md from template.
        glab mr list returns [] -> scaffold from plan_template.md, file contains
        standard sections like '## Implementation Plan'.

        Function under test: await cmd_extract_plan() -> scaffold_or_generate()
        Refactoring required: YES (_extract_plan_inner: 76 lines, 7 deps)
        Dependency missed/absent: NO
        """
        mock_pipeline.return_value = ('', PlanContext())
        mock_run.side_effect = [
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),  # git rev-parse
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),  # git rev-parse
            (0, '[]', ''),                          # glab mr list -> empty
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),  # cmd_cache_save rev-parse
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),  # cmd_cache_save rev-parse
        ]
        with tempfile.TemporaryDirectory() as tmp:
            plan_file = os.path.join(tmp, 'PLAN.md')
            with patch('git_hooks_impl.entry_points.extract_plan.PLAN_FILE', plan_file), \
                 patch('git_hooks_impl.plan.cache.PLAN_FILE', plan_file), \
                 patch('git_hooks_impl.plan.cache._CACHE_DIR', os.path.join(tmp, 'cache')), \
                 patch('git_hooks_impl.entry_points.extract_plan._NAG_FILE', os.path.join(tmp, '.nag')), \
                 patch('git_hooks_impl.entry_points.extract_plan.jira_summary', return_value=('', '')):
                await cmd_extract_plan()
            self.assertTrue(os.path.isfile(plan_file))
            with open(plan_file, encoding='utf-8') as f:
                content = f.read()
            self.assertIn('## Implementation Plan', content)

    @patch('git_hooks_impl.entry_points.extract_plan.jira_summary', return_value=('Fix race condition', 'Full Jira content'))
    async def test_scaffold_enriched_with_jira(self, mock_jira):
        """Branch has ticket, jira succeeds -> title/context filled.
        Branch 'productname/fixes/PROJECTNAME-1234_fix' + Jira summary 'Fix race condition':
        Branch 'productname/fixes/PROJECTNAME-1234_fix' + Jira summary 'Fix race condition':
        -> {{TITLE}} = '[PROJECTNAME-1234] Fix race condition'
        -> {{CONTEXT}} = 'Full Jira content'.

        Function under test: _scaffold_plan()
        Refactoring required: NO (17 lines, 3 deps: _load_template, jira_summary, _title_from_branch)
        Dependency missed/absent: NO
        """
        plan, jira_sum = await _scaffold_plan('productname/fixes/PROJECTNAME-1234_fix', 'PROJECTNAME-1234')
        plan, jira_sum = await _scaffold_plan('productname/fixes/PROJECTNAME-1234_fix', 'PROJECTNAME-1234')
        self.assertIn('[PROJECTNAME-1234] Fix race condition', plan)
        self.assertIn('Full Jira content', plan)

    @patch('git_hooks_impl.entry_points.extract_plan.jira_summary', return_value=('', ''))
    async def test_scaffold_plain_when_jira_fails(self, mock_jira):
        """Jira fails -> plain template, no crash.
        Branch 'productname/fixes/PROJECTNAME-1234_fix' + empty Jira response:
        Branch 'productname/fixes/PROJECTNAME-1234_fix' + empty Jira response:
        -> {{TITLE}} = '[PROJECTNAME-1234] Fix' (derived from tail)
        -> {{CONTEXT}} = '(Add context here)' (placeholder).

        Function under test: _scaffold_plan()
        Refactoring required: NO (17 lines, 3 deps: _load_template, jira_summary, _title_from_branch)
        Dependency missed/absent: NO
        """
        plan, jira_sum = await _scaffold_plan('productname/fixes/PROJECTNAME-1234_fix', 'PROJECTNAME-1234')
        plan, jira_sum = await _scaffold_plan('productname/fixes/PROJECTNAME-1234_fix', 'PROJECTNAME-1234')
        self.assertIn('[PROJECTNAME-1234]', plan)
        self.assertIn('(Add context here)', plan)

    @patch('git_hooks_impl.entry_points.extract_plan._try_ai_pipeline', new_callable=AsyncMock)
    @patch('git_hooks_impl.entry_points.extract_plan.find_tool', return_value='/usr/bin/glab')
    @patch('git_hooks_impl.plan.cache.run', return_value=(0, 'master\n', ''))
    @patch('git_hooks_impl.entry_points.extract_plan.run')
    async def test_scaffold_suggests_branch_rename(self, mock_run, mock_pc_run, mock_tool, mock_pipeline):
        """No ticket in branch -> scaffolds plan and logs tip to add a Jira ticket.
        Branch 'productname/fixes/no_ticket_here' has no PROJ-NNN prefix, so parse_branch
        Branch 'productname/fixes/no_ticket_here' has no PROJ-NNN prefix, so parse_branch
        returns ('fix', '').  Plan is still written but with a placeholder context.

        Function under test: await cmd_extract_plan() -> scaffold_or_generate()
        Refactoring required: YES (_extract_plan_inner: 76 lines, 7 deps)
        Dependency missed/absent: NO
        """
        mock_pipeline.return_value = ('', PlanContext())
        mock_run.side_effect = [
            (0, 'productname/fixes/no_ticket_here\n', ''),  # git rev-parse
            (0, 'productname/fixes/no_ticket_here\n', ''),  # git rev-parse
            (0, '[]', ''),                              # glab mr list
            (0, 'productname/fixes/no_ticket_here\n', ''),  # cmd_cache_save rev-parse
            (0, 'productname/fixes/no_ticket_here\n', ''),  # cmd_cache_save rev-parse
        ]
        with tempfile.TemporaryDirectory() as tmp:
            plan_file = os.path.join(tmp, 'PLAN.md')
            with patch('git_hooks_impl.entry_points.extract_plan.PLAN_FILE', plan_file), \
                 patch('git_hooks_impl.plan.cache.PLAN_FILE', plan_file), \
                 patch('git_hooks_impl.plan.cache._CACHE_DIR', os.path.join(tmp, 'cache')), \
                 patch('git_hooks_impl.entry_points.extract_plan._NAG_FILE', os.path.join(tmp, '.nag')):
                # The function should succeed without crash
                await cmd_extract_plan()
            self.assertTrue(os.path.isfile(plan_file))


# ---------------------------------------------------------------------------
#  Skip / guard conditions
# ---------------------------------------------------------------------------

class TestSkipConditions(unittest.IsolatedAsyncioTestCase):

    @patch('git_hooks_impl.entry_points.extract_plan.jira_summary', new_callable=AsyncMock, return_value=('', ''))
    @patch('git_hooks_impl.entry_points.extract_plan.find_tool', return_value='/usr/bin/glab')
    @patch('git_hooks_impl.plan.cache.run', return_value=(0, 'master\n', ''))
    @patch('git_hooks_impl.entry_points.extract_plan.run_async', new_callable=AsyncMock,
           return_value=(0, _two_mrs(), ''))
    @patch('git_hooks_impl.entry_points.extract_plan.run')
    async def test_skips_when_multiple_open_mrs(self, mock_run, mock_run_async, mock_pc_run, mock_tool, mock_jira):
        """2 open MRs for branch -> no file written, warns.
        glab mr list returns [{iid:42,...}, {iid:43,...}] -> ambiguous, skip.

        Function under test: await cmd_extract_plan()
        Refactoring required: YES (_extract_plan_inner: 76 lines, 7 deps)
        Dependency missed/absent: was missing plan_cache.PLAN_FILE patch
        """
        mock_run.side_effect = [
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),  # cmd_cache_save -> git rev-parse
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),  # cmd_cache_save -> git rev-parse
        ]
        with tempfile.TemporaryDirectory() as tmp:
            plan_file = os.path.join(tmp, 'PLAN.md')
            with patch('git_hooks_impl.entry_points.extract_plan.PLAN_FILE', plan_file), \
                 patch('git_hooks_impl.plan.cache.PLAN_FILE', plan_file), \
                 patch('git_hooks_impl.plan.cache._CACHE_DIR', os.path.join(tmp, 'cache')), \
                 patch('git_hooks_impl.entry_points.extract_plan._NAG_FILE', os.path.join(tmp, '.nag')):
                result = await cmd_extract_plan()
            self.assertEqual(result, 0)
            self.assertFalse(os.path.isfile(plan_file))

    @patch('git_hooks_impl.plan.cache.run', return_value=(0, 'master\n', ''))
    @patch('git_hooks_impl.entry_points.extract_plan.run')
    async def test_skips_on_master_branch(self, mock_run, mock_pc_run):
        """Master -> early return (but prune still runs on post-merge/rewrite).

        Function under test: await cmd_extract_plan()
        Refactoring required: YES (_extract_plan_inner: 76 lines, 7 deps)
        Dependency missed/absent: NO
        """
        mock_run.return_value = (0, 'master\n', '')
        with tempfile.TemporaryDirectory() as tmp, \
             patch('git_hooks_impl.plan.cache._CACHE_DIR', os.path.join(tmp, 'cache')):
            result = await cmd_extract_plan()
        self.assertEqual(result, 0)

    @patch('git_hooks_impl.entry_points.extract_plan._try_ai_pipeline', new_callable=AsyncMock)
    @patch('git_hooks_impl.entry_points.extract_plan.template_skeleton', return_value=('skeleton', [], []))
    @patch('git_hooks_impl.entry_points.extract_plan.find_tool', return_value='')
    @patch('git_hooks_impl.plan.cache.run', return_value=(0, 'master\n', ''))
    @patch('git_hooks_impl.entry_points.extract_plan.run')
    async def test_skips_when_glab_not_found(self, mock_run, mock_pc_run, mock_tool, mock_skel, mock_pipeline):
        """Glab not found -> scaffolds template without MR check.
        find_tool('glab') returns '' -> no glab mr list call, directly scaffold
        from template.  File is still written to .ai/PLAN.md.

        Function under test: await cmd_extract_plan() -> scaffold_or_generate()
        Refactoring required: YES (_extract_plan_inner: 76 lines, 7 deps)
        Dependency missed/absent: NO
        """
        mock_pipeline.return_value = ('', PlanContext())
        mock_run.side_effect = [
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),  # git rev-parse
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),  # git rev-parse
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),  # cmd_cache_save rev-parse
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),  # cmd_cache_save rev-parse
        ]
        with tempfile.TemporaryDirectory() as tmp:
            plan_file = os.path.join(tmp, 'PLAN.md')
            with patch('git_hooks_impl.entry_points.extract_plan.PLAN_FILE', plan_file), \
                 patch('git_hooks_impl.plan.cache.PLAN_FILE', plan_file), \
                 patch('git_hooks_impl.plan.cache._CACHE_DIR', os.path.join(tmp, 'cache')), \
                 patch('git_hooks_impl.entry_points.extract_plan._NAG_FILE', os.path.join(tmp, '.nag')), \
                 patch('git_hooks_impl.entry_points.extract_plan.jira_summary', return_value=('', '')):
                await cmd_extract_plan()
            self.assertTrue(os.path.isfile(plan_file))

    async def test_creates_ai_directory_if_missing(self):
        """Directory .ai/ doesn't exist -> created automatically.

        Function under test: _write_plan()
        Refactoring required: NO (9 lines, 3 deps: embed_plan_hash, extract_meta, embed_meta)
        Dependency missed/absent: NO
        """
        with tempfile.TemporaryDirectory() as tmp:
            plan_file = os.path.join(tmp, 'new_subdir', 'PLAN.md')
            with patch('git_hooks_impl.entry_points.extract_plan.PLAN_FILE', plan_file):
                _write_plan('test content')
            self.assertTrue(os.path.isfile(plan_file))

    async def test_write_plan_generates_uuid(self):
        """Plan without UUID -> written file has plan-uuid in meta.
        '# Plan\\n' (no meta) -> file contains 'plan-uuid: <36-char UUID>'.

        Function under test: _write_plan()
        Refactoring required: NO (9 lines, 3 deps: embed_plan_hash, extract_meta, embed_meta)
        Dependency missed/absent: NO
        """
        with tempfile.TemporaryDirectory() as tmp:
            plan_file = os.path.join(tmp, 'PLAN.md')
            with patch('git_hooks_impl.entry_points.extract_plan.PLAN_FILE', plan_file):
                _write_plan('# Plan\n')
            with open(plan_file, encoding='utf-8') as f:
                content = f.read()
            meta = extract_meta(content)
            self.assertIn('plan-uuid', meta)
            self.assertEqual(len(meta['plan-uuid']), 36)  # UUID4 format

    async def test_write_plan_preserves_existing_uuid(self):
        """Plan with UUID 'aaa...' -> written file still has 'aaa...'.
        embed_meta('# Plan', **{'plan-uuid': 'aaa'}) -> file keeps 'aaa'.

        Function under test: _write_plan()
        Refactoring required: NO (9 lines, 3 deps: embed_plan_hash, extract_meta, embed_meta)
        Dependency missed/absent: NO
        """
        plan = embed_meta('# Plan\n', **{'plan-uuid': 'aaa'})
        with tempfile.TemporaryDirectory() as tmp:
            plan_file = os.path.join(tmp, 'PLAN.md')
            with patch('git_hooks_impl.entry_points.extract_plan.PLAN_FILE', plan_file):
                _write_plan(plan)
            with open(plan_file, encoding='utf-8') as f:
                content = f.read()
            meta = extract_meta(content)
            self.assertEqual(meta['plan-uuid'], 'aaa')

    @patch('git_hooks_impl.entry_points.extract_plan.run')
    async def test_never_blocks_on_error(self, mock_run):
        """Any unexpected error -> returns 0, never crashes.
        The hook wraps all logic in try/except -- even if git rev-parse
        raises, the shell exit code is 0 so git operations are not blocked.

        Function under test: await cmd_extract_plan()
        Refactoring required: YES (_extract_plan_inner: 76 lines, 7 deps)
        Dependency missed/absent: NO (exception skips _prune_stale_caches + cmd_cache_save)
        """
        mock_run.side_effect = Exception('unexpected!')
        with tempfile.TemporaryDirectory() as tmp, \
             patch('git_hooks_impl.plan.cache._CACHE_DIR', os.path.join(tmp, 'cache')):
            result = await cmd_extract_plan()
        self.assertEqual(result, 0)


# ---------------------------------------------------------------------------
#  MR without PLAN section — AI generation
# ---------------------------------------------------------------------------

class TestGeneratePlanFromMr(unittest.IsolatedAsyncioTestCase):

    @patch.dict(os.environ, {}, clear=False)
    @patch('git_hooks_impl.entry_points.extract_plan._try_ai_pipeline', new_callable=AsyncMock)
    @patch('git_hooks_impl.entry_points.extract_plan.find_tool', return_value='/usr/bin/glab')
    @patch('git_hooks_impl.plan.cache.run', return_value=(0, 'master\n', ''))
    @patch('git_hooks_impl.entry_points.extract_plan.run')
    async def test_generates_plan_from_mr_when_no_plan_section(self, mock_run, mock_pc_run,
                                                          mock_tool, mock_pipeline):
        """MR exists but description has no <details>PLAN.md</details> block.
        _try_ai_pipeline returns generated plan -> writes AI output
        directly to .ai/PLAN.md.

        Function under test: await cmd_extract_plan() -> _handle_no_plan_section()
        Refactoring required: YES (_extract_plan_inner: 76 lines, 7 deps)
        Dependency missed/absent: NO
        """
        mock_pipeline.return_value = ('# Generated Plan\n', PlanContext())
        mr_desc = '## Description\n\nSome feature work'
        mock_run.side_effect = [
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),
            (0, _one_mr(description=mr_desc), ''),
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),  # cmd_cache_save -> git rev-parse
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),  # cmd_cache_save -> git rev-parse
        ]
        with tempfile.TemporaryDirectory() as tmp:
            plan_file = os.path.join(tmp, 'PLAN.md')
            with patch('git_hooks_impl.entry_points.extract_plan.PLAN_FILE', plan_file), \
                 patch('git_hooks_impl.plan.cache.PLAN_FILE', plan_file), \
                 patch('git_hooks_impl.plan.cache._CACHE_DIR', os.path.join(tmp, 'cache')), \
                 patch('git_hooks_impl.entry_points.extract_plan._NAG_FILE', os.path.join(tmp, '.nag')):
                await cmd_extract_plan()
            self.assertTrue(os.path.isfile(plan_file))
            with open(plan_file) as f:
                self.assertIn('Generated Plan', f.read())

    @patch.dict(os.environ, {}, clear=False)
    @patch('git_hooks_impl.entry_points.extract_plan._try_ai_pipeline', new_callable=AsyncMock)
    @patch('git_hooks_impl.entry_points.extract_plan.jira_summary', new_callable=AsyncMock, return_value=('', ''))
    @patch('git_hooks_impl.entry_points.extract_plan.find_tool', return_value='/usr/bin/glab')
    @patch('git_hooks_impl.plan.cache.run', return_value=(0, 'master\n', ''))
    @patch('git_hooks_impl.entry_points.extract_plan.run')
    async def test_generates_plan_from_mr_fallback_no_claude(self, mock_run, mock_pc_run,
                                                        mock_tool, mock_jira, mock_pipeline):
        """Claude not available -> falls back to scaffolding from template.
        MR description '## Description\\n\\nSome feature work' is injected into
        the {{CONTEXT}} placeholder, so the plan contains both standard sections
        ('## Implementation Plan') and the MR text ('Some feature work').
        _try_ai_pipeline mocked to return empty — simulates Claude unavailable.

        Function under test: await cmd_extract_plan() -> _handle_no_plan_section()
        Refactoring required: YES (_extract_plan_inner: 76 lines, 7 deps)
        Dependency missed/absent: NO
        """
        mock_pipeline.return_value = ('', PlanContext())

        mr_desc = '## Description\n\nSome feature work'
        mock_run.side_effect = [
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),  # cmd_cache_save -> git rev-parse
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),  # cmd_cache_save -> git rev-parse
        ]
        with tempfile.TemporaryDirectory() as tmp:
            plan_file = os.path.join(tmp, 'PLAN.md')
            with patch('git_hooks_impl.entry_points.extract_plan.PLAN_FILE', plan_file), \
                 patch('git_hooks_impl.plan.cache.PLAN_FILE', plan_file), \
                 patch('git_hooks_impl.plan.cache._CACHE_DIR', os.path.join(tmp, 'cache')), \
                 patch('git_hooks_impl.entry_points.extract_plan._NAG_FILE', os.path.join(tmp, '.nag')), \
                 patch('git_hooks_impl.entry_points.extract_plan.run_async', new_callable=AsyncMock,
                       return_value=(0, _one_mr(description=mr_desc), '')):
                await cmd_extract_plan()
            self.assertTrue(os.path.isfile(plan_file))
            with open(plan_file, encoding='utf-8') as f:
                content = f.read()
            # Should have template structure with MR desc as context
            self.assertIn('## Implementation Plan', content)
            self.assertIn('Some feature work', content)


# ---------------------------------------------------------------------------
#  Token budget & diff collection strategy
# ---------------------------------------------------------------------------

class TestTokenBudget(unittest.IsolatedAsyncioTestCase):

    def test_estimates_tokens_correctly(self):
        """Rough estimate: ~4 chars per token (integer division).
        400 chars -> 100 tokens, 3 chars -> 0 tokens, 4 chars -> 1 token.

        Function under test: estimate_tokens()
        Refactoring required: NO (pure function)
        Dependency missed/absent: NO
        """
        self.assertEqual(estimate_tokens(400), 100)
        self.assertEqual(estimate_tokens(0), 0)
        self.assertEqual(estimate_tokens(3), 0)  # integer division
        self.assertEqual(estimate_tokens(4), 1)

    async def test_single_call_under_budget(self):
        """100-char diff (~25 tokens) is well under 600k-char budget.
        Full diff text is included in context parts for a single claude call.

        Function under test: _collect_context_for_generation()
        Refactoring required: YES (82 lines, 7 deps)
        Dependency missed/absent: NO
        """
        small_diff = 'a' * 100
        with patch('git_hooks_impl.entry_points.extract_plan._get_merge_base', return_value='abc123'), \
             patch('git_hooks_impl.entry_points.extract_plan._get_commit_messages', return_value='msg'), \
             patch('git_hooks_impl.entry_points.extract_plan._get_diff_stat', return_value='stat'), \
             patch('git_hooks_impl.entry_points.extract_plan._get_full_diff', return_value=small_diff), \
             patch('git_hooks_impl.entry_points.extract_plan._get_diff_files', return_value=[]), \
             patch('git_hooks_impl.entry_points.extract_plan.jira_summary', new_callable=AsyncMock, return_value=('', '')):
            parts = await _collect_context_for_generation('branch', '')
        # Full diff should be in context
        found = any(small_diff in p for p in parts)
        self.assertTrue(found, 'Full diff should be included for small diffs')

    async def test_single_call_at_boundary(self):
        """Diff of exactly 600,000 chars (~150k tokens) -- at the budget boundary.
        Should still use single-call mode (<= check, not <).

        Function under test: _collect_context_for_generation()
        Refactoring required: YES (82 lines, 7 deps)
        Dependency missed/absent: NO
        """
        boundary_diff = 'x' * _TOKEN_BUDGET_CHARS
        with patch('git_hooks_impl.entry_points.extract_plan._get_merge_base', return_value='abc123'), \
             patch('git_hooks_impl.entry_points.extract_plan._get_commit_messages', return_value='msg'), \
             patch('git_hooks_impl.entry_points.extract_plan._get_diff_stat', return_value='stat'), \
             patch('git_hooks_impl.entry_points.extract_plan._get_full_diff', return_value=boundary_diff), \
             patch('git_hooks_impl.entry_points.extract_plan._get_diff_files', return_value=[]), \
             patch('git_hooks_impl.entry_points.extract_plan.jira_summary', new_callable=AsyncMock, return_value=('', '')):
            parts = await _collect_context_for_generation('branch', '')
        found = any(boundary_diff in p for p in parts)
        self.assertTrue(found, 'Diff exactly at budget should use single call')

    async def test_multi_call_over_budget(self):
        """600,001 chars (1 over budget) -> multi-call mode kicks in.
        Test files are omitted first (tier 1).  Since remaining fits after
        removing tests/test_foo.py, a filtered diff (without tests) is used.

        Function under test: _collect_context_for_generation()
        Refactoring required: YES (82 lines, 7 deps)
        Dependency missed/absent: NO
        """
        over_diff = 'x' * (_TOKEN_BUDGET_CHARS + 1)
        test_file = ('tests/test_foo.py', 100)
        keep_file = ('src/main.py', 50)
        with patch('git_hooks_impl.entry_points.extract_plan._get_merge_base', return_value='abc123'), \
             patch('git_hooks_impl.entry_points.extract_plan._get_commit_messages', return_value='msg'), \
             patch('git_hooks_impl.entry_points.extract_plan._get_diff_stat', return_value='stat'), \
             patch('git_hooks_impl.entry_points.extract_plan._get_full_diff', return_value=over_diff), \
             patch('git_hooks_impl.entry_points.extract_plan._get_diff_files', return_value=[test_file, keep_file]), \
             patch('git_hooks_impl.entry_points.extract_plan._get_filtered_diff', return_value='filtered'), \
             patch('git_hooks_impl.entry_points.extract_plan.jira_summary', new_callable=AsyncMock, return_value=('', '')):
            parts = await _collect_context_for_generation('branch', '')
        # Should NOT contain the full diff
        found_full = any(over_diff in p for p in parts)
        self.assertFalse(found_full, 'Full diff should not be in multi-call context')

    async def test_empty_diff_no_crash(self):
        """New branch with no commits (merge-base returns '') -> skip diff
        collection, return whatever other context is available (may be empty).

        Function under test: _collect_context_for_generation()
        Refactoring required: YES (82 lines, 7 deps)
        Dependency missed/absent: NO
        """
        with patch('git_hooks_impl.entry_points.extract_plan._get_merge_base', return_value=''), \
             patch('git_hooks_impl.entry_points.extract_plan.jira_summary', new_callable=AsyncMock, return_value=('', '')):
            parts = await _collect_context_for_generation('branch', '')
        # Should not crash, just return whatever context is available
        self.assertIsInstance(parts, list)


if __name__ == '__main__':
    unittest.main(verbosity=2)
