#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for hooks/extract_plan.py and git_hooks_impl/plan/cache.py —
coverage-gap cases for the cache layer: UUID-mismatch guard on save, loading
the cached push base for 3-way merges, parsing deleted branches from
reference-transaction stdin, early-return behavior when PLAN.md is missing,
OSError handling during cache restore, git-failure handling during stale
cache pruning, and the write-before-cache ordering in scaffold_or_generate.

Run:  python -m unittest discover -s .git-hooks/hooks/tests -t .git-hooks -p "test_extract_plan_cache_gaps.py" -v
"""

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
from io import StringIO

from git_hooks_impl.entry_points.extract_plan import scaffold_or_generate
from git_hooks_impl.plan.cache import (
    _load_base,
    _prune_stale_caches,
    _read_deleted_branches,
    _restore_cache,
    _sanitize_branch_name,
    _save_cache,
)
from git_hooks_impl.plan.context import PlanContext

# ---------------------------------------------------------------------------
#  plan_cache.py — UUID mismatch guard + _load_base + _read_deleted_branches
# ---------------------------------------------------------------------------

class TestSaveCacheUuidMismatch(unittest.TestCase):
    """Tests for _save_cache() UUID mismatch guard — refuses cross-branch overwrites."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.plan_file = os.path.join(self.tmp, '.ai', 'PLAN.md')
        self.cache_dir = os.path.join(self.tmp, '.ai', 'cache')
        os.makedirs(os.path.dirname(self.plan_file), exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_uuid_mismatch_realigns_cache(self):
        """Plan UUID differs from cached UUID -> cache realigned to current plan.

        Default behavior (force=False) on UUID mismatch: warn + delete the old
        cache + copy the new plan in. The current plan on disk is treated as
        authoritative; the cached UUID is replaced.
        """
        # Write plan with UUID-A
        plan_content = '<!-- meta\nplan-uuid: uuid-AAAA\n-->\n# Plan A\n'
        with open(self.plan_file, 'w') as f:
            f.write(plan_content)

        # Pre-populate cache with UUID-B
        branch_dir = os.path.join(self.cache_dir,
                                  _sanitize_branch_name('feature/test'))
        os.makedirs(branch_dir, exist_ok=True)
        cache_path = os.path.join(branch_dir, 'cached_BRANCH_PLAN.md')
        cached_content = '<!-- meta\nplan-uuid: uuid-BBBB\n-->\n# Plan B\n'
        with open(cache_path, 'w') as f:
            f.write(cached_content)

        with patch('git_hooks_impl.plan.cache.PLAN_FILE', self.plan_file), \
             patch('git_hooks_impl.plan.cache._CACHE_DIR', self.cache_dir):
            _save_cache('feature/test')

        # Cache file should now have UUID-A (realigned to current plan)
        with open(cache_path) as f:
            content = f.read()
        self.assertIn('uuid-AAAA', content)
        self.assertNotIn('uuid-BBBB', content)

    def test_force_bypasses_uuid_guard(self):
        """force=True + UUID mismatch -> UUID guard skipped; cache overwritten with plan-A.

        Intentional force-regen (mr plangen --force) must not trigger the warning
        or preserve stale cached content.

        Function under test: _save_cache(branch, force=True)
        """
        plan_content = '<!-- meta\nplan-uuid: uuid-AAAA\n-->\n# Plan A\n'
        with open(self.plan_file, 'w') as f:
            f.write(plan_content)

        branch_dir = os.path.join(self.cache_dir,
                                  _sanitize_branch_name('feature/test'))
        os.makedirs(branch_dir, exist_ok=True)
        cache_path = os.path.join(branch_dir, 'cached_BRANCH_PLAN.md')
        cached_content = '<!-- meta\nplan-uuid: uuid-BBBB\n-->\n# Plan B\n'
        with open(cache_path, 'w') as f:
            f.write(cached_content)

        with patch('git_hooks_impl.plan.cache.PLAN_FILE', self.plan_file), \
             patch('git_hooks_impl.plan.cache._CACHE_DIR', self.cache_dir):
            _save_cache('feature/test', force=True)

        # Cache must now contain plan-A's UUID (overwritten without warning)
        with open(cache_path) as f:
            content = f.read()
        self.assertIn('uuid-AAAA', content)
        self.assertNotIn('uuid-BBBB', content)


class TestLoadBase(unittest.TestCase):
    """Tests for _load_base() — loads push base for 3-way conflict detection."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cache_dir = os.path.join(self.tmp, '.ai', 'cache')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_load_base_returns_content(self):
        """base_PLAN.md exists -> returns its content.

        Function under test: _load_base()
        Dependency missed/absent: NO
        """
        branch_dir = os.path.join(self.cache_dir,
                                  _sanitize_branch_name('feature/test'))
        os.makedirs(branch_dir, exist_ok=True)
        base_path = os.path.join(branch_dir, 'base_PLAN.md')
        with open(base_path, 'w') as f:
            f.write('base content here')
        with patch('git_hooks_impl.plan.cache._CACHE_DIR', self.cache_dir):
            result = _load_base('feature/test')
        self.assertEqual(result, 'base content here')

    def test_load_base_returns_none_when_missing(self):
        """No base_PLAN.md -> returns None.

        Function under test: _load_base()
        Dependency missed/absent: NO
        """
        with patch('git_hooks_impl.plan.cache._CACHE_DIR', self.cache_dir):
            result = _load_base('nonexistent/branch')
        self.assertIsNone(result)


class TestReadDeletedBranches(unittest.TestCase):
    """Tests for _read_deleted_branches() — parses reference-transaction stdin."""

    def test_parses_branch_deletions(self):
        """Stdin lines with null new-sha + refs/heads/ prefix -> branch names extracted.

        reference-transaction hook format: '<old-sha> <new-sha> <ref-name>'
        Branch deletion: new-sha is 40 zeros, ref starts with refs/heads/.

        Function under test: _read_deleted_branches()
        Dependency missed/absent: NO
        """
        null_sha = '0' * 40
        real_sha = 'a' * 40
        stdin_lines = (
            f'{real_sha} {null_sha} refs/heads/feature/deleted\n'
            f'{real_sha} {real_sha} refs/heads/feature/updated\n'
            f'{real_sha} {null_sha} refs/tags/v1.0\n'
            f'{real_sha} {null_sha} refs/heads/bugfix/removed\n'
        )
        with patch('git_hooks_impl.plan.cache.sys.stdin', StringIO(stdin_lines)):
            result = _read_deleted_branches()
        self.assertEqual(result, ['feature/deleted', 'bugfix/removed'])

    def test_empty_stdin_returns_empty_list(self):
        """No stdin lines -> empty list.

        Function under test: _read_deleted_branches()
        Dependency missed/absent: NO
        """
        with patch('git_hooks_impl.plan.cache.sys.stdin', StringIO('')):
            result = _read_deleted_branches()
        self.assertEqual(result, [])

    def test_malformed_lines_skipped(self):
        """Lines with fewer than 3 parts -> skipped gracefully.

        Function under test: _read_deleted_branches()
        Dependency missed/absent: NO
        """
        stdin_lines = 'only_one_part\ntwo parts\n'
        with patch('git_hooks_impl.plan.cache.sys.stdin', StringIO(stdin_lines)):
            result = _read_deleted_branches()
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
#  _save_cache — early return when plan file missing
# ---------------------------------------------------------------------------

class TestSaveCacheNoPlanFile(unittest.TestCase):
    """Cover _save_cache early return when PLAN_FILE does not exist."""

    def test_no_plan_file_returns_without_creating_cache(self):
        """PLAN_FILE missing -> early return, no cache dir created.

        Line 56-57: if not os.path.isfile(PLAN_FILE): return.
        No filesystem side effects when there is nothing to cache.

        Function under test: _save_cache()
        """
        with tempfile.TemporaryDirectory() as tmp:
            fake_plan = os.path.join(tmp, 'nonexistent', 'PLAN.md')
            cache_dir = os.path.join(tmp, 'cache')
            with patch('git_hooks_impl.plan.cache.PLAN_FILE', fake_plan), \
                 patch('git_hooks_impl.plan.cache._CACHE_DIR', cache_dir):
                _save_cache('feature/my-branch')
            # Cache dir should NOT have been created
            self.assertFalse(os.path.isdir(cache_dir))


# ---------------------------------------------------------------------------
#  _restore_cache — OSError during copy
# ---------------------------------------------------------------------------

class TestRestoreCacheOSError(unittest.TestCase):
    """Cover _restore_cache OSError when shutil.copy2 fails."""

    def test_cache_exists_but_copy_fails_returns_false(self):
        """Cache file exists but copy2 raises OSError -> returns False.

        The except OSError block catches the failure and returns False
        so callers can fall back to MR fetch.

        Function under test: _restore_cache()
        """
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = os.path.join(tmp, 'cache',
                                     _sanitize_branch_name('feature/test'))
            os.makedirs(cache_dir)
            cache_file = os.path.join(cache_dir, 'cached_BRANCH_PLAN.md')
            with open(cache_file, 'w') as f:
                f.write('# Cached plan\n')
            # shutil.copy2 is patched to raise OSError — PLAN_FILE path
            # doesn't matter since copy2 never executes the real syscall.
            fake_plan = os.path.join(tmp, 'target', 'PLAN.md')
            with patch('git_hooks_impl.plan.cache.PLAN_FILE', fake_plan), \
                 patch('git_hooks_impl.plan.cache._CACHE_DIR', os.path.join(tmp, 'cache')), \
                 patch('git_hooks_impl.plan.cache.shutil.copy2',
                       side_effect=OSError('Permission denied')):
                result = _restore_cache('feature/test')
            self.assertFalse(result)


# ---------------------------------------------------------------------------
#  _prune_stale_caches — git branch list failure
# ---------------------------------------------------------------------------

class TestPruneStaleCachesGitFailure(unittest.TestCase):
    """Cover _prune_stale_caches early return when git branch --list fails."""

    def test_git_branch_failure_returns_without_pruning(self):
        """Git branch --list returns exit_code=1 -> early return, caches untouched.

        Line 165-166: if exit_code != 0: return.
        Git failure should never delete any cache dirs.

        Function under test: _prune_stale_caches()
        """
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = os.path.join(tmp, 'cache')
            os.makedirs(cache_dir)
            # Create a cache dir that would normally be pruned
            stale_dir = os.path.join(cache_dir, 'old_branch')
            os.makedirs(stale_dir)
            with open(os.path.join(stale_dir, 'cached_BRANCH_PLAN.md'), 'w') as f:
                f.write('stale')

            with patch('git_hooks_impl.plan.cache._CACHE_DIR', cache_dir), \
                 patch('git_hooks_impl.plan.cache.run',
                       return_value=(1, '', 'fatal: not a git repo')):
                _prune_stale_caches()

            # Cache dir should still exist — git failure means no pruning
            self.assertTrue(os.path.isdir(stale_dir))


# ---------------------------------------------------------------------------
#  scaffold_or_generate — _write_plan before _save_cache ordering
# ---------------------------------------------------------------------------

class TestScaffoldOrGenerateWriteOrder(unittest.IsolatedAsyncioTestCase):
    """Verify _write_plan() is called before _save_cache() in scaffold_or_generate."""

    @patch('git_hooks_impl.entry_points.extract_plan._try_ai_pipeline', new_callable=AsyncMock)
    @patch('git_hooks_impl.entry_points.extract_plan.template_skeleton',
           return_value=('', [], []))
    @patch('git_hooks_impl.entry_points.extract_plan._scaffold_plan',
           return_value=('# Scaffolded\n', ''))
    @patch('git_hooks_impl.entry_points.extract_plan._save_cache')
    @patch('git_hooks_impl.entry_points.extract_plan._write_plan')
    async def test_write_plan_before_save_cache(self, mock_write, mock_cache,
                                          mock_scaffold, mock_skeleton, mock_pipeline):
        """Plan file written to disk before cache snapshot is saved.

        _write_plan must precede _save_cache so the cache captures the
        latest content. A reversed order would cache stale/missing data.

        Function under test: scaffold_or_generate()
        """
        mock_pipeline.return_value = ('', PlanContext())
        call_order = []
        mock_write.side_effect = lambda *a, **kw: call_order.append('write_plan')
        mock_cache.side_effect = lambda *a, **kw: call_order.append('save_cache')

        await scaffold_or_generate('feature/test', None)

        self.assertIn('write_plan', call_order)
        self.assertIn('save_cache', call_order)
        write_idx = call_order.index('write_plan')
        cache_idx = call_order.index('save_cache')
        self.assertLess(write_idx, cache_idx,
                        f'_write_plan (idx {write_idx}) must be called before '
                        f'_save_cache (idx {cache_idx}); actual order: {call_order}')


if __name__ == '__main__':
    unittest.main(verbosity=2)
