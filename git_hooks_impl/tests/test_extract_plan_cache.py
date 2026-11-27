#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for hooks/extract_plan.py - PLAN.md extraction from MR with embedded
plan-hash integration, and .ai/cache save/restore/swap for PLAN.md snapshots
across branch switches.

Run:  python -m unittest discover -s .git-hooks/hooks/tests -t .git-hooks -p "test_extract_plan_cache.py" -v
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

import shutil

from git_hooks_impl.entry_points.extract_plan import (
    cmd_cache_save,
    cmd_cache_swap,
    cmd_extract_plan,
)
from git_hooks_impl.plan.cache import (
    _restore_cache,
    _save_cache,
)
from git_hooks_impl.tests.utils import build_mr_description


# Helper for building an MR description carrying the given plan content.
def _mr_with_plan(plan_content):
    return build_mr_description(plan_content)


def _one_mr(iid=42, title='Test MR', description=''):
    return json.dumps([{'iid': iid, 'title': title, 'description': description}])


def _two_mrs():
    return json.dumps([
        {'iid': 42, 'title': 'MR one', 'description': ''},
        {'iid': 43, 'title': 'MR two', 'description': ''},
    ])


# ---------------------------------------------------------------------------
#  Hash integration - extract-plan flow with embedded hashes
# ---------------------------------------------------------------------------

class TestPlanHashIntegration(unittest.IsolatedAsyncioTestCase):

    async def test_skips_when_hash_matches(self):
        """MR hash matches + local file exists -> keeps local version.
        Simulates: pushed plan, no GitLab edit, local has changes.

        Function under test: await cmd_extract_plan()
        Refactoring required: YES (_extract_plan_inner: 76 lines, 7 deps)
        Dependency missed/absent: NO
        """
        plan_text = '# Plan\n## Steps\n'
        # Local file must be >= _MIN_PLAN_SIZE (100) to not be treated as stub
        local_text = '# My local edits\n' + 'x' * 100
        with tempfile.TemporaryDirectory() as tmp:
            plan_file = os.path.join(tmp, 'PLAN.md')
            with open(plan_file, 'w') as f:
                f.write(local_text)
            with patch('git_hooks_impl.entry_points.extract_plan.PLAN_FILE', plan_file), \
                 patch('git_hooks_impl.plan.cache.PLAN_FILE', plan_file), \
                 patch('git_hooks_impl.plan.cache._CACHE_DIR', os.path.join(tmp, 'cache')), \
                 patch('git_hooks_impl.entry_points.extract_plan._NAG_FILE', os.path.join(tmp, '.nag')), \
                 patch('git_hooks_impl.entry_points.extract_plan.find_tool', return_value='/usr/bin/glab'), \
                 patch('git_hooks_impl.plan.cache.run', return_value=(0, 'master\n', '')), \
                 patch('git_hooks_impl.entry_points.extract_plan.run_async', new_callable=AsyncMock,
                       return_value=(0, _one_mr(description=_mr_with_plan(plan_text)), '')), \
                 patch('git_hooks_impl.entry_points.extract_plan.run',
                       side_effect=[(0, 'productname/fixes/PROJECTNAME-1_fix\n', ''), (0, 'productname/fixes/PROJECTNAME-1_fix\n', '')]):
                       side_effect=[(0, 'productname/fixes/PROJECTNAME-1_fix\n', ''), (0, 'productname/fixes/PROJECTNAME-1_fix\n', '')]):
                await cmd_extract_plan()
            with open(plan_file, encoding='utf-8') as f:
                content = f.read()
            self.assertIn('My local edits', content)

    async def test_pulls_when_edited_on_mr_no_local(self):
        """MR edited (hash mismatch) + no local file -> pulls MR version.

        Function under test: await cmd_extract_plan()
        Refactoring required: YES (_extract_plan_inner: 76 lines, 7 deps)
        Dependency missed/absent: NO
        """
        original = '# Original\n\n## Context\n\nOriginal text.\n'
        synced_desc = _mr_with_plan(original)
        # Tamper the visible body of the already-built description, so the
        # plan-meta footer still carries the hash of the original content.
        mr_desc = synced_desc.replace('Original text.', 'Edited remotely.')
        with tempfile.TemporaryDirectory() as tmp:
            plan_file = os.path.join(tmp, 'PLAN.md')
            # No local file
            with patch('git_hooks_impl.entry_points.extract_plan.PLAN_FILE', plan_file), \
                 patch('git_hooks_impl.plan.cache.PLAN_FILE', plan_file), \
                 patch('git_hooks_impl.plan.cache._CACHE_DIR', os.path.join(tmp, 'cache')), \
                 patch('git_hooks_impl.entry_points.extract_plan._NAG_FILE', os.path.join(tmp, '.nag')), \
                 patch('git_hooks_impl.entry_points.extract_plan.find_tool', return_value='/usr/bin/glab'), \
                 patch('git_hooks_impl.plan.cache.run', return_value=(0, 'master\n', '')), \
                 patch('git_hooks_impl.entry_points.extract_plan.run_async', new_callable=AsyncMock,
                       return_value=(0, _one_mr(description=mr_desc), '')), \
                 patch('git_hooks_impl.entry_points.extract_plan.run',
                       side_effect=[(0, 'productname/fixes/PROJECTNAME-1_fix\n', ''), (0, 'productname/fixes/PROJECTNAME-1_fix\n', '')]):
                       side_effect=[(0, 'productname/fixes/PROJECTNAME-1_fix\n', ''), (0, 'productname/fixes/PROJECTNAME-1_fix\n', '')]):
                await cmd_extract_plan()
            self.assertTrue(os.path.isfile(plan_file))
            with open(plan_file, encoding='utf-8') as f:
                content = f.read()
            self.assertIn('Edited remotely', content)


# ---------------------------------------------------------------------------
#  PLAN extraction from MR
# ---------------------------------------------------------------------------

class TestExtractPlanFromMr(unittest.IsolatedAsyncioTestCase):

    @patch('git_hooks_impl.entry_points.extract_plan.find_tool', return_value='/usr/bin/glab')
    @patch('git_hooks_impl.plan.cache.run', return_value=(0, 'master\n', ''))
    @patch('git_hooks_impl.entry_points.extract_plan.run')
    async def test_extracts_plan_from_mr_description(self, mock_run, mock_pc_run, mock_tool):
        """1 open MR with PLAN section -> writes .ai/PLAN.md.
        MR desc: '## Description...\\n<details>...# My Plan...\\n</details><!-- /PLAN.md -->'
        -> .ai/PLAN.md contains '# My Plan\\n- Step 1\\n- Step 2' (markers stripped).

        Function under test: await cmd_extract_plan()
        Refactoring required: YES (_extract_plan_inner: 76 lines, 7 deps)
        Dependency missed/absent: NO
        """
        plan_text = '# My Plan\n- Step 1\n- Step 2'
        mr_desc = _mr_with_plan(plan_text)
        mock_run.side_effect = [
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),   # git rev-parse
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),   # git rev-parse
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),   # cmd_cache_save -> git rev-parse
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),   # cmd_cache_save -> git rev-parse
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
            self.assertIn('# My Plan', content)
            self.assertIn('- Step 1', content)


class TestCacheSaveRestore(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.plan_file = os.path.join(self.tmp, '.ai', 'PLAN.md')
        self.cache_dir = os.path.join(self.tmp, '.ai', 'cache')
        os.makedirs(os.path.dirname(self.plan_file), exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_save_creates_cached_plan(self):
        """Save copies PLAN.md -> .ai/cache/<branch>/cached_BRANCH_PLAN.md.

        Function under test: _save_cache()
        Refactoring required: NO (pure filesystem, 3 deps)
        Dependency missed/absent: NO
        """
        with open(self.plan_file, 'w') as f:
            f.write('my plan')
        with patch('git_hooks_impl.plan.cache.PLAN_FILE', self.plan_file), \
             patch('git_hooks_impl.plan.cache._CACHE_DIR', self.cache_dir):
            _save_cache('productname/fixes/PROJECTNAME-1234_fix')
            _save_cache('productname/fixes/PROJECTNAME-1234_fix')
        cache_path = os.path.join(self.cache_dir, 'productname_fixes_productname_1234_fix', 'cached_BRANCH_PLAN.md')
        cache_path = os.path.join(self.cache_dir, 'productname_fixes_productname_1234_fix', 'cached_BRANCH_PLAN.md')
        self.assertTrue(os.path.isfile(cache_path))
        with open(cache_path) as f:
            self.assertEqual(f.read(), 'my plan')
        # PLAN.md should still exist (copy, not move)
        self.assertTrue(os.path.isfile(self.plan_file))

    def test_restore_copies_back(self):
        """Restore copies cached_BRANCH_PLAN.md -> .ai/PLAN.md (cache survives).

        Function under test: _restore_cache()
        Refactoring required: NO (pure filesystem, 3 deps)
        Dependency missed/absent: NO
        """
        cache_branch_dir = os.path.join(self.cache_dir, 'my_branch')
        os.makedirs(cache_branch_dir)
        cache_path = os.path.join(cache_branch_dir, 'cached_BRANCH_PLAN.md')
        with open(cache_path, 'w') as f:
            f.write('cached content')
        with patch('git_hooks_impl.plan.cache.PLAN_FILE', self.plan_file), \
             patch('git_hooks_impl.plan.cache._CACHE_DIR', self.cache_dir):
            result = _restore_cache('my/branch')
        self.assertTrue(result)
        self.assertTrue(os.path.isfile(self.plan_file))
        with open(self.plan_file) as f:
            self.assertEqual(f.read(), 'cached content')
        # Cache file should still exist (copy, not move)
        self.assertTrue(os.path.isfile(cache_path))

    def test_save_overwrites_not_accumulates(self):
        """Second save overwrites cached_BRANCH_PLAN.md, not creates a new file.

        Function under test: _save_cache() + _restore_cache()
        Refactoring required: NO (pure filesystem, 3 deps each)
        Dependency missed/absent: NO
        """
        with open(self.plan_file, 'w') as f:
            f.write('first')
        with patch('git_hooks_impl.plan.cache.PLAN_FILE', self.plan_file), \
             patch('git_hooks_impl.plan.cache._CACHE_DIR', self.cache_dir):
            _save_cache('branch/a')
        # Restore, modify, save again
        with patch('git_hooks_impl.plan.cache.PLAN_FILE', self.plan_file), \
             patch('git_hooks_impl.plan.cache._CACHE_DIR', self.cache_dir):
            _restore_cache('branch/a')
        with open(self.plan_file, 'a') as f:
            f.write(' second')
        with patch('git_hooks_impl.plan.cache.PLAN_FILE', self.plan_file), \
             patch('git_hooks_impl.plan.cache._CACHE_DIR', self.cache_dir):
            _save_cache('branch/a')
        branch_dir = os.path.join(self.cache_dir, 'branch_a')
        md_files = [f for f in os.listdir(branch_dir) if f.endswith('.md')]
        self.assertEqual(len(md_files), 1, 'Should have exactly one cached file')

    def test_no_error_when_plan_missing(self):
        """No .ai/PLAN.md -> save is a no-op.

        Function under test: _save_cache()
        Refactoring required: NO (pure filesystem, 3 deps)
        Dependency missed/absent: NO
        """
        with patch('git_hooks_impl.plan.cache.PLAN_FILE', '/nonexistent/PLAN.md'):
            _save_cache('some/branch')  # should not raise

    def test_restore_returns_false_on_cache_miss(self):
        """No cache for branch -> returns False.

        Function under test: _restore_cache()
        Refactoring required: NO (pure filesystem, 3 deps)
        Dependency missed/absent: NO
        """
        with patch('git_hooks_impl.plan.cache.PLAN_FILE', self.plan_file), \
             patch('git_hooks_impl.plan.cache._CACHE_DIR', self.cache_dir):
            result = _restore_cache('nonexistent/branch')
        self.assertFalse(result)


class TestCacheSwap(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.plan_file = os.path.join(self.tmp, '.ai', 'PLAN.md')
        self.cache_dir = os.path.join(self.tmp, '.ai', 'cache')
        os.makedirs(os.path.dirname(self.plan_file), exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    @patch('git_hooks_impl.entry_points.extract_plan._extract_plan_inner')
    @patch('git_hooks_impl.plan.cache.run')
    @patch('git_hooks_impl.entry_points.extract_plan.run')
    def test_cache_hit_skips_network(self, mock_run, mock_pc_run, mock_inner):
        """Cache exists for target branch -> no MR fetch needed.

        Function under test: cmd_cache_swap()
        Refactoring required: YES (cmd_cache_swap: 59 lines, 6 deps)
        Dependency missed/absent: NO
        """
        # Pre-populate cache
        branch_dir = os.path.join(self.cache_dir, 'feature_test')
        os.makedirs(branch_dir)
        with open(os.path.join(branch_dir, 'cached_BRANCH_PLAN.md'), 'w') as f:
            f.write('cached plan')
        mock_run.side_effect = [
            (0, 'feature/test\n', ''),  # git rev-parse (extract_plan.run)
        ]
        mock_pc_run.side_effect = [
            (0, '', ''),                # git name-rev (plan_cache.run)
        ]
        with patch('git_hooks_impl.plan.cache.PLAN_FILE', self.plan_file), \
             patch('git_hooks_impl.plan.cache._CACHE_DIR', self.cache_dir):
            result = cmd_cache_swap(prev_ref='abc123')
        self.assertEqual(result, 0)
        mock_inner.assert_not_called()  # no MR fetch
        self.assertTrue(os.path.isfile(self.plan_file))

    @patch('git_hooks_impl.entry_points.extract_plan._extract_plan_inner')
    @patch('git_hooks_impl.entry_points.extract_plan.log')
    @patch('git_hooks_impl.plan.cache.run')
    @patch('git_hooks_impl.entry_points.extract_plan.run')
    def test_cache_miss_prints_suggestion_and_exits(self, mock_run, mock_pc_run, mock_log, mock_inner):
        """No cache for target branch -> logs suggestion and returns 0; no MR fetch.

        Phase 2 removed the fallback to _extract_plan_inner on cache miss.
        Cache miss is now a silent no-op: log a hint, exit 0.

        Function under test: cmd_cache_swap()
        Refactoring required: YES (cmd_cache_swap: 59 lines, 6 deps)
        Dependency missed/absent: NO
        """
        mock_run.side_effect = [
            (0, 'feature/new\n', ''),   # git rev-parse (extract_plan.run)
        ]
        mock_pc_run.side_effect = [
            (1, '', ''),                # git name-rev fails (plan_cache.run)
        ]
        with patch('git_hooks_impl.plan.cache.PLAN_FILE', self.plan_file), \
             patch('git_hooks_impl.plan.cache._CACHE_DIR', self.cache_dir):
            result = cmd_cache_swap(prev_ref='abc123')
        self.assertEqual(result, 0)
        mock_inner.assert_not_called()
        logged_text = ' '.join(str(a) for call in mock_log.call_args_list for a in call.args)
        self.assertIn('gen_plan', logged_text)

    @patch('git_hooks_impl.plan.cache.run')
    @patch('git_hooks_impl.entry_points.extract_plan.run')
    def test_master_saves_old_plan(self, mock_run, mock_pc_run):
        """Switching to master still saves old branch's plan to cache.

        Function under test: cmd_cache_swap()
        Refactoring required: YES (cmd_cache_swap: 59 lines, 6 deps)
        Dependency missed/absent: NO
        """
        with open(self.plan_file, 'w') as f:
            f.write('feature plan')
        mock_run.side_effect = [
            (0, 'master\n', ''),                   # git rev-parse -> master (extract_plan.run)
        ]
        mock_pc_run.side_effect = [
            (0, 'feature/old\n', ''),               # git name-rev -> old branch (plan_cache.run)
        ]
        with patch('git_hooks_impl.plan.cache.PLAN_FILE', self.plan_file), \
             patch('git_hooks_impl.plan.cache._CACHE_DIR', self.cache_dir):
            result = cmd_cache_swap(prev_ref='abc123')
        self.assertEqual(result, 0)
        # Old branch plan saved in cache
        cache_path = os.path.join(self.cache_dir, 'feature_old', 'cached_BRANCH_PLAN.md')
        self.assertTrue(os.path.isfile(cache_path))


# ---------------------------------------------------------------------------
#  Post-commit cache save
# ---------------------------------------------------------------------------

class TestCacheSave(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.plan_file = os.path.join(self.tmp, '.ai', 'PLAN.md')
        self.cache_dir = os.path.join(self.tmp, '.ai', 'cache')
        os.makedirs(os.path.dirname(self.plan_file), exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    @patch('git_hooks_impl.entry_points.extract_plan.run')
    def test_cache_save_writes_to_cache(self, mock_run):
        """Feature branch + PLAN.md on disk -> cache file created.
        Branch 'feature/test' + .ai/PLAN.md -> .ai/cache/feature_test/cached_BRANCH_PLAN.md.

        Function under test: cmd_cache_save()
        Refactoring required: NO (10 lines, 2 deps: run, _save_cache)
        Dependency missed/absent: NO
        """
        with open(self.plan_file, 'w') as f:
            f.write('my plan content')
        mock_run.return_value = (0, 'feature/test\n', '')
        with patch('git_hooks_impl.plan.cache.PLAN_FILE', self.plan_file), \
             patch('git_hooks_impl.plan.cache._CACHE_DIR', self.cache_dir):
            result = cmd_cache_save()
        self.assertEqual(result, 0)
        cache_path = os.path.join(self.cache_dir, 'feature_test', 'cached_BRANCH_PLAN.md')
        self.assertTrue(os.path.isfile(cache_path))
        with open(cache_path) as f:
            self.assertEqual(f.read(), 'my plan content')
        # PLAN.md should still exist (copy, not move)
        self.assertTrue(os.path.isfile(self.plan_file))

    @patch('git_hooks_impl.entry_points.extract_plan.run')
    def test_cache_save_skips_master(self, mock_run):
        """On master -> no cache written, returns 0.
        Branch 'master' -> _save_cache never called.

        Function under test: cmd_cache_save()
        Refactoring required: NO (10 lines, 2 deps: run, _save_cache)
        Dependency missed/absent: NO
        """
        with open(self.plan_file, 'w') as f:
            f.write('stale plan')
        mock_run.return_value = (0, 'master\n', '')
        with patch('git_hooks_impl.plan.cache.PLAN_FILE', self.plan_file), \
             patch('git_hooks_impl.plan.cache._CACHE_DIR', self.cache_dir):
            result = cmd_cache_save()
        self.assertEqual(result, 0)
        self.assertFalse(os.path.isdir(self.cache_dir))

    @patch('git_hooks_impl.entry_points.extract_plan.run')
    def test_cache_save_skips_without_plan(self, mock_run):
        """No PLAN.md on disk -> no error, no cache file created.
        Branch 'feature/x' but no .ai/PLAN.md -> _save_cache is a no-op.

        Function under test: cmd_cache_save()
        Refactoring required: NO (10 lines, 2 deps: run, _save_cache)
        Dependency missed/absent: NO
        """
        mock_run.return_value = (0, 'feature/x\n', '')
        with patch('git_hooks_impl.plan.cache.PLAN_FILE', self.plan_file), \
             patch('git_hooks_impl.plan.cache._CACHE_DIR', self.cache_dir):
            result = cmd_cache_save()
        self.assertEqual(result, 0)
        self.assertFalse(os.path.isdir(self.cache_dir))


if __name__ == '__main__':
    unittest.main(verbosity=2)
