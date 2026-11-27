#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for git_hooks_impl.entry_points.commands.leak_check.

Each function is tested in isolation per the Main Mock Rule. Git-backed
helpers mock subprocess.run. Filesystem-only helpers operate on real files
inside tempdir fixtures. Env-var reads use os.environ patching, not a mock.

_check_plan_integrity has three branches: a PLAN_HASH_BEFORE hash check, a
BRANCH_PLAN_COPY.md diff, and a heuristic fallback. The first two are
unreachable in the current codebase — no caller sets PLAN_HASH_BEFORE or
writes BRANCH_PLAN_COPY.md — so their tests are defensive (confirm no
crash), not meaningful regression coverage. The heuristic fallback is the
branch `mr verify` actually exercises and gets full behavioral coverage.

cli.py's cmd_verify calls leak_check.run([]) directly (the verify gate
itself), so run()'s aggregation logic gets its own test class.
"""

import hashlib
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from git_hooks_impl.entry_points.commands import leak_check

_MOD = 'git_hooks_impl.entry_points.commands.leak_check'


def _git_result(stdout='', returncode=0):
    return MagicMock(returncode=returncode, stdout=stdout, stderr='')


class TestAiToolingRoot(unittest.TestCase):
    """_ai_tooling_root(): AI_TOOLING_SRC env var, else git root of this file."""

    def test_uses_env_var_when_set(self):
        """AI_TOOLING_SRC set -> returned directly, no subprocess call."""
        with (
            patch.dict(os.environ, {'AI_TOOLING_SRC': '/fake/root'}, clear=False),
            patch(f'{_MOD}.subprocess.run') as mock_run,
        ):
            result = leak_check._ai_tooling_root()
        self.assertEqual(result, Path('/fake/root'))
        mock_run.assert_not_called()

    def test_falls_back_to_git_root_when_env_unset(self):
        """No env var -> git rev-parse --show-toplevel of the script's own dir."""
        env = dict(os.environ)
        env.pop('AI_TOOLING_SRC', None)
        with (
            patch.dict(os.environ, env, clear=True),
            patch(f'{_MOD}.subprocess.run',
                  return_value=_git_result(stdout='/repo/root\n')) as mock_run,
        ):
            result = leak_check._ai_tooling_root()
        self.assertEqual(result, Path('/repo/root'))
        mock_run.assert_called_once()


class TestGitToplevel(unittest.TestCase):
    """_git_toplevel(): git root of the cwd, or None outside a repo."""

    @patch(f'{_MOD}.subprocess.run')
    def test_returns_path_when_in_repo(self, mock_run):
        """Git rev-parse succeeds -> Path of the printed root."""
        mock_run.return_value = _git_result(stdout='/some/repo\n')
        self.assertEqual(leak_check._git_toplevel(), Path('/some/repo'))

    @patch(f'{_MOD}.subprocess.run')
    def test_returns_none_outside_repo(self, mock_run):
        """Git rev-parse fails (nonzero rc) -> None."""
        mock_run.return_value = _git_result(returncode=128)
        self.assertIsNone(leak_check._git_toplevel())


class TestGitTracked(unittest.TestCase):
    """_git_tracked(): whether a path is a tracked file in the given repo."""

    @patch(f'{_MOD}.subprocess.run')
    def test_tracked_file_returns_true(self, mock_run):
        """Git ls-files --error-unmatch succeeds -> True."""
        mock_run.return_value = _git_result(returncode=0)
        self.assertTrue(leak_check._git_tracked(Path('/repo'), '.ai/BRANCH_PLAN.md'))

    @patch(f'{_MOD}.subprocess.run')
    def test_untracked_file_returns_false(self, mock_run):
        """Git ls-files --error-unmatch fails -> False."""
        mock_run.return_value = _git_result(returncode=1)
        self.assertFalse(leak_check._git_tracked(Path('/repo'), '.ai/BRANCH_PLAN.md'))


class TestCheckHookLog(unittest.TestCase):
    """_check_hook_log(): hook.log must not exist (sentinel check)."""

    def setUp(self):
        self.ai_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.ai_dir, ignore_errors=True)

    def test_no_hook_log_is_clean(self):
        """No hook.log present -> False (no leak)."""
        self.assertFalse(leak_check._check_hook_log(self.ai_dir))

    def test_hook_log_present_is_leak(self):
        """hook.log exists -> True (leak) regardless of content."""
        (self.ai_dir / 'hook.log').write_text('stale line\n', encoding='utf-8')
        self.assertTrue(leak_check._check_hook_log(self.ai_dir))


class TestCheckTestsLog(unittest.TestCase):
    """_check_tests_log(): no TESTS.log should land under .ai/."""

    def setUp(self):
        self.ai_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.ai_dir, ignore_errors=True)

    def test_no_tests_log_is_clean(self):
        """No TESTS.log under .ai/ -> False (no leak)."""
        self.assertFalse(leak_check._check_tests_log(self.ai_dir))

    def test_tests_log_present_is_leak(self):
        """TESTS.log exists under .ai/ -> True (the temp-dir redirect failed)."""
        (self.ai_dir / 'TESTS.log').write_text('ERR: something\n', encoding='utf-8')
        self.assertTrue(leak_check._check_tests_log(self.ai_dir))


class TestRestore(unittest.TestCase):
    """_restore(): overwrites plan_file with the backup copy's bytes."""

    def test_restore_copies_backup_bytes(self):
        """plan_file content after _restore matches plan_copy's bytes exactly."""
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        plan_file = tmp / 'BRANCH_PLAN.md'
        plan_copy = tmp / 'BRANCH_PLAN_COPY.md'
        plan_copy.write_text('# Original Plan\n', encoding='utf-8')
        plan_file.write_text('# Corrupted\n', encoding='utf-8')
        leak_check._restore(plan_copy, plan_file)
        self.assertEqual(plan_file.read_bytes(), plan_copy.read_bytes())


class TestCheckPlanIntegrity(unittest.TestCase):
    """_check_plan_integrity(): a hash check, a backup-diff, a heuristic
    fallback, plus the plan-deleted branch.

    The hash-check and backup-diff paths are dead in the current codebase —
    no caller sets PLAN_HASH_BEFORE or writes BRANCH_PLAN_COPY.md. Their
    tests are defensive: they confirm the branch doesn't crash, not that it
    matters in production. The heuristic fallback is the ACTIVE path
    `mr verify` actually exercises and gets full behavioral coverage.
    """

    def setUp(self):
        self.ai_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.ai_dir, ignore_errors=True)
        self.ai_tooling_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.ai_tooling_root, ignore_errors=True)
        self.plan_file = self.ai_dir / 'BRANCH_PLAN.md'
        self.plan_copy = self.ai_dir / 'BRANCH_PLAN_COPY.md'
        self._clear_env = patch.dict(os.environ, {}, clear=False)
        self._clear_env.start()
        os.environ.pop('PLAN_HASH_BEFORE', None)
        os.environ.pop('LEAK_CHECK_AUTO_DELETE_FIXTURE', None)
        self.addCleanup(self._clear_env.stop)

    # -- plan missing branch --

    def test_no_plan_no_baseline_is_clean(self):
        """ACTIVE PATH: plan absent, no hash/backup baseline -> False (first run)."""
        result = leak_check._check_plan_integrity(self.ai_dir, self.ai_tooling_root)
        self.assertFalse(result)

    def test_no_plan_with_backup_copy_is_leak_and_restores(self):
        """Plan deleted but a backup copy exists -> True, restored from backup."""
        self.plan_copy.write_text('# Restored Plan\n', encoding='utf-8')
        result = leak_check._check_plan_integrity(self.ai_dir, self.ai_tooling_root)
        self.assertTrue(result)
        self.assertEqual(self.plan_file.read_text(encoding='utf-8'), '# Restored Plan\n')

    def test_no_plan_with_hash_before_env_is_leak(self):
        """Plan deleted with a hash baseline set -> True."""
        os.environ['PLAN_HASH_BEFORE'] = 'deadbeef'
        result = leak_check._check_plan_integrity(self.ai_dir, self.ai_tooling_root)
        self.assertTrue(result)

    # -- plan present, PLAN_HASH_BEFORE branch (dead path) --

    def test_plan_present_hash_before_matches_is_clean(self):
        """Hash baseline set and matches the current file -> False."""
        self.plan_file.write_text('# Plan\n', encoding='utf-8')
        os.environ['PLAN_HASH_BEFORE'] = hashlib.md5(self.plan_file.read_bytes()).hexdigest()
        result = leak_check._check_plan_integrity(self.ai_dir, self.ai_tooling_root)
        self.assertFalse(result)

    def test_plan_present_hash_before_differs_is_leak_and_restores(self):
        """Hash baseline set and differs -> True, restored from backup when
        one exists.
        """
        self.plan_file.write_text('# Corrupted\n', encoding='utf-8')
        self.plan_copy.write_text('# Original\n', encoding='utf-8')
        os.environ['PLAN_HASH_BEFORE'] = 'not-the-real-hash'
        result = leak_check._check_plan_integrity(self.ai_dir, self.ai_tooling_root)
        self.assertTrue(result)
        self.assertEqual(self.plan_file.read_text(encoding='utf-8'), '# Original\n')

    # -- plan present, BRANCH_PLAN_COPY.md branch (dead path) --

    def test_plan_present_copy_matches_is_clean(self):
        """Plan matches its backup copy -> False."""
        self.plan_file.write_text('# Plan\n', encoding='utf-8')
        self.plan_copy.write_text('# Plan\n', encoding='utf-8')
        result = leak_check._check_plan_integrity(self.ai_dir, self.ai_tooling_root)
        self.assertFalse(result)

    def test_plan_present_copy_differs_is_leak_and_restores(self):
        """Plan differs from its backup copy -> True, restored."""
        self.plan_file.write_text('# Corrupted\n', encoding='utf-8')
        self.plan_copy.write_text('# Original\n', encoding='utf-8')
        result = leak_check._check_plan_integrity(self.ai_dir, self.ai_tooling_root)
        self.assertTrue(result)
        self.assertEqual(self.plan_file.read_text(encoding='utf-8'), '# Original\n')

    # -- plan present, no baseline: the ACTIVE heuristic fallback --

    @patch(f'{_MOD}._git_tracked', return_value=True)
    def test_plan_present_no_baseline_normal_content_is_clean(self, mock_tracked):
        """ACTIVE PATH: real-looking plan content, no baseline files -> False."""
        self.plan_file.write_text(
            '## Plan\nSome real branch plan content well over two hundred bytes '
            'so the size heuristic alone would not classify it as a fixture. ' * 3,
            encoding='utf-8',
        )
        result = leak_check._check_plan_integrity(self.ai_dir, self.ai_tooling_root)
        self.assertFalse(result)

    @patch(f'{_MOD}._git_tracked', return_value=False)
    def test_plan_present_no_baseline_fixture_kept_by_default(self, mock_tracked):
        """ACTIVE PATH: small test-fixture-shaped content, no baseline, env var
        unset -> False, file kept (not deleted).
        """
        self.plan_file.write_text('# Local Plan\nfixture\n', encoding='utf-8')
        result = leak_check._check_plan_integrity(self.ai_dir, self.ai_tooling_root)
        self.assertFalse(result)
        self.assertTrue(self.plan_file.is_file())

    @patch(f'{_MOD}._git_tracked', return_value=False)
    def test_plan_present_no_baseline_fixture_deleted_when_opted_in(self, mock_tracked):
        """ACTIVE PATH: fixture content, LEAK_CHECK_AUTO_DELETE_FIXTURE=1 -> True,
        file deleted.
        """
        self.plan_file.write_text('# Remote Plan\nfixture\n', encoding='utf-8')
        os.environ['LEAK_CHECK_AUTO_DELETE_FIXTURE'] = '1'
        result = leak_check._check_plan_integrity(self.ai_dir, self.ai_tooling_root)
        self.assertTrue(result)
        self.assertFalse(self.plan_file.is_file())


class TestSanitizedBranchSet(unittest.TestCase):
    """_sanitized_branch_set(): lowercased, '/' -> '_', '-' removed."""

    @patch(f'{_MOD}.subprocess.run')
    def test_sanitizes_case_slash_and_dash(self, mock_run):
        """'* Feature/My-Branch' and 'main' -> {'feature_mybranch', 'main'}."""
        mock_run.return_value = _git_result(stdout='  main\n* Feature/My-Branch\n')
        result = leak_check._sanitized_branch_set(Path('/repo'))
        self.assertEqual(result, {'main', 'feature_mybranch'})


class TestDefaultBranch(unittest.TestCase):
    """_default_branch(): origin/HEAD symbolic ref, or 'master' if undetermined."""

    @patch(f'{_MOD}.subprocess.run')
    def test_strips_origin_prefix(self, mock_run):
        """'origin/main' -> 'main'."""
        mock_run.return_value = _git_result(stdout='origin/main\n')
        self.assertEqual(leak_check._default_branch(Path('/repo')), 'main')

    @patch(f'{_MOD}.subprocess.run')
    def test_empty_ref_defaults_to_master(self, mock_run):
        """No symbolic-ref output -> 'master'."""
        mock_run.return_value = _git_result(stdout='')
        self.assertEqual(leak_check._default_branch(Path('/repo')), 'master')


class TestCheckAgentSlots(unittest.TestCase):
    """_check_agent_slots(): flags a nested agent folder one level under a slot."""

    def setUp(self):
        self.agents_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.agents_dir, ignore_errors=True)

    def test_no_agents_dir_returns_false(self):
        """agents/ doesn't exist -> False, no crash."""
        missing = self.agents_dir / 'missing'
        self.assertFalse(leak_check._check_agent_slots(missing, 'mybranch', 'label'))

    def test_plain_sibling_slot_not_flagged(self):
        """A normal agent slot with no nested subfolder -> False."""
        (self.agents_dir / 'tester' / 'test_writer').mkdir(parents=True)
        self.assertFalse(leak_check._check_agent_slots(self.agents_dir, 'mybranch', 'label'))

    def test_ass_prefixed_nested_folder_is_flagged(self):
        """A nested folder named 'ass-*' one level under a slot -> True."""
        (self.agents_dir / 'tester' / 'ass-123').mkdir(parents=True)
        self.assertTrue(leak_check._check_agent_slots(self.agents_dir, 'mybranch', 'label'))

    def test_nested_folder_with_output_md_is_flagged(self):
        """A nested folder containing output.md one level under a slot -> True."""
        nested = self.agents_dir / 'tester' / 'inner'
        nested.mkdir(parents=True)
        (nested / 'output.md').write_text('x', encoding='utf-8')
        self.assertTrue(leak_check._check_agent_slots(self.agents_dir, 'mybranch', 'label'))


class TestCheckCacheLayout(unittest.TestCase):
    """_check_cache_layout(): AGT-14 canonical .ai/cache/ layout enforcement."""

    def setUp(self):
        self.cache_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.cache_dir, ignore_errors=True)
        self.repo_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.repo_root, ignore_errors=True)
        # _check_agent_slots is a direct dependency of _check_cache_layout —
        # isolate it per the Main Mock Rule so these tests exercise only the
        # branch-folder matching logic under test.
        agent_slots_patch = patch(f'{_MOD}._check_agent_slots', return_value=False)
        agent_slots_patch.start()
        self.addCleanup(agent_slots_patch.stop)

    def _mocks(self, default_branch, branch_set):
        return (
            patch(f'{_MOD}._default_branch', return_value=default_branch),
            patch(f'{_MOD}._sanitized_branch_set', return_value=branch_set),
        )

    def test_missing_cache_dir_is_clean(self):
        """No .ai/cache/ directory -> False, no crash."""
        missing = self.cache_dir / 'missing'
        self.assertFalse(leak_check._check_cache_layout(missing, self.repo_root, 'label'))

    def test_matching_branch_folder_is_clean(self):
        """Folder name already lowercase and equal to its sanitized branch -> False."""
        (self.cache_dir / 'mybranch' / 'agents').mkdir(parents=True)
        m1, m2 = self._mocks('main', {'mybranch'})
        with m1, m2:
            result = leak_check._check_cache_layout(self.cache_dir, self.repo_root, 'label')
        self.assertFalse(result)

    def test_default_branch_folder_is_leak(self):
        """A folder named after the default branch is forbidden -> True."""
        (self.cache_dir / 'main').mkdir()
        m1, m2 = self._mocks('main', {'main'})
        with m1, m2:
            result = leak_check._check_cache_layout(self.cache_dir, self.repo_root, 'label')
        self.assertTrue(result)

    def test_folder_for_nonexistent_branch_is_leak(self):
        """A folder whose sanitized name isn't in the branch set -> True."""
        (self.cache_dir / 'ghostbranch').mkdir()
        m1, m2 = self._mocks('main', {'realbranch'})
        with m1, m2:
            result = leak_check._check_cache_layout(self.cache_dir, self.repo_root, 'label')
        self.assertTrue(result)

    def test_case_mismatch_folder_is_not_matched_case_sensitively(self):
        """On-disk folder name is NOT lowercased before comparing against the
        sanitized (lowercased) branch set. A folder differing only in case
        from an existing branch is flagged as a leak, not matched.
        """
        (self.cache_dir / 'MyBranch').mkdir()
        # Branch 'MyBranch' really exists. Its sanitized form is lowercase.
        m1, m2 = self._mocks('main', {'mybranch'})
        with m1, m2:
            result = leak_check._check_cache_layout(self.cache_dir, self.repo_root, 'label')
        self.assertTrue(result)

    def test_loose_file_at_cache_top_is_leak(self):
        """A file directly under .ai/cache/ (not a directory) -> True."""
        (self.cache_dir / 'stray.txt').write_text('x', encoding='utf-8')
        m1, m2 = self._mocks('main', set())
        with m1, m2:
            result = leak_check._check_cache_layout(self.cache_dir, self.repo_root, 'label')
        self.assertTrue(result)

    def test_non_canonical_subdir_under_branch_is_leak(self):
        """A top-level dir under the branch folder other than agents/recycle -> True."""
        (self.cache_dir / 'mybranch' / 'badsub').mkdir(parents=True)
        m1, m2 = self._mocks('main', {'mybranch'})
        with m1, m2:
            result = leak_check._check_cache_layout(self.cache_dir, self.repo_root, 'label')
        self.assertTrue(result)

    def test_loose_file_under_branch_folder_is_leak(self):
        """A file directly under the branch folder (not agents/recycle) -> True."""
        branch_dir = self.cache_dir / 'mybranch'
        branch_dir.mkdir()
        (branch_dir / 'stray.txt').write_text('x', encoding='utf-8')
        m1, m2 = self._mocks('main', {'mybranch'})
        with m1, m2:
            result = leak_check._check_cache_layout(self.cache_dir, self.repo_root, 'label')
        self.assertTrue(result)

    def test_plan_cache_files_are_not_flagged(self):
        """cached_BRANCH_PLAN.md, base_PLAN.md, {local,remote,merged}_PLAN.md,
        and session_state.md are legitimate files git_hooks_impl/plan/cache.py
        and the compaction hooks write directly under the branch folder -
        not agent output, so they must not be flagged as loose-file leaks.
        """
        branch_dir = self.cache_dir / 'mybranch'
        branch_dir.mkdir()
        for name in (
            'cached_BRANCH_PLAN.md', 'base_PLAN.md', 'local_PLAN.md',
            'remote_PLAN.md', 'merged_PLAN.md', 'session_state.md',
        ):
            (branch_dir / name).write_text('x', encoding='utf-8')
        m1, m2 = self._mocks('main', {'mybranch'})
        with m1, m2:
            result = leak_check._check_cache_layout(self.cache_dir, self.repo_root, 'label')
        self.assertFalse(result)

    def test_gen_cache_subdir_is_not_flagged(self):
        """gen_cache/ is the plan-generation pipeline's cache dir, not agents/recycle."""
        (self.cache_dir / 'mybranch' / 'gen_cache').mkdir(parents=True)
        m1, m2 = self._mocks('main', {'mybranch'})
        with m1, m2:
            result = leak_check._check_cache_layout(self.cache_dir, self.repo_root, 'label')
        self.assertFalse(result)

    def test_unrecognized_file_alongside_plan_cache_files_is_still_a_leak(self):
        """The allowlist doesn't blanket-exempt the whole branch folder."""
        branch_dir = self.cache_dir / 'mybranch'
        branch_dir.mkdir()
        (branch_dir / 'cached_BRANCH_PLAN.md').write_text('x', encoding='utf-8')
        (branch_dir / 'unexpected.txt').write_text('x', encoding='utf-8')
        m1, m2 = self._mocks('main', {'mybranch'})
        with m1, m2:
            result = leak_check._check_cache_layout(self.cache_dir, self.repo_root, 'label')
        self.assertTrue(result)


class TestCheckWallTime(unittest.TestCase):
    """_check_wall_time(): check 5, only active when TEST_WALL_TIME_SECONDS is set."""

    def setUp(self):
        self._env_patch = patch.dict(os.environ, {}, clear=False)
        self._env_patch.start()
        os.environ.pop('TEST_WALL_TIME_SECONDS', None)
        os.environ.pop('TEST_WALL_TIME_MAX_SECONDS', None)
        self.addCleanup(self._env_patch.stop)

    def test_env_var_absent_is_clean_and_silent(self):
        self.assertFalse(leak_check._check_wall_time())

    def test_non_numeric_env_var_is_clean(self):
        os.environ['TEST_WALL_TIME_SECONDS'] = 'not-a-number'
        self.assertFalse(leak_check._check_wall_time())

    def test_under_threshold_is_clean(self):
        os.environ['TEST_WALL_TIME_SECONDS'] = '30'
        self.assertFalse(leak_check._check_wall_time())

    def test_over_default_threshold_is_leak(self):
        os.environ['TEST_WALL_TIME_SECONDS'] = '200'
        self.assertTrue(leak_check._check_wall_time())

    def test_custom_threshold_is_respected(self):
        os.environ['TEST_WALL_TIME_SECONDS'] = '50'
        os.environ['TEST_WALL_TIME_MAX_SECONDS'] = '40'
        self.assertTrue(leak_check._check_wall_time())

    def test_exactly_at_threshold_is_clean(self):
        os.environ['TEST_WALL_TIME_SECONDS'] = '180'
        self.assertFalse(leak_check._check_wall_time())


class TestLeakCheckRun(unittest.TestCase):
    """run(): aggregates all five checks; cli.py's cmd_verify calls this directly."""

    def _patches(self, hook, tests_log, plan, cache, ai_root, cwd_root, wall_time=False):
        return [
            patch(f'{_MOD}._ai_tooling_root', return_value=ai_root),
            patch(f'{_MOD}._git_toplevel', return_value=cwd_root),
            patch(f'{_MOD}._check_hook_log', return_value=hook),
            patch(f'{_MOD}._check_tests_log', return_value=tests_log),
            patch(f'{_MOD}._check_plan_integrity', return_value=plan),
            patch(f'{_MOD}._check_wall_time', return_value=wall_time),
            patch(f'{_MOD}._check_cache_layout', return_value=cache),
        ]

    def test_all_clean_returns_0(self):
        """Every check clean, cwd same as ai_tooling root -> 0."""
        root = Path('/repo')
        patches = self._patches(False, False, False, False, root, root)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            self.assertEqual(leak_check.run([]), 0)

    def test_any_leak_returns_1(self):
        """Any single check reporting a leak -> 1."""
        root = Path('/repo')
        patches = self._patches(False, True, False, False, root, root)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            self.assertEqual(leak_check.run([]), 1)

    def test_wall_time_leak_alone_returns_1(self):
        """A slow suite alone (all other checks clean) -> 1."""
        root = Path('/repo')
        patches = self._patches(False, False, False, False, root, root, wall_time=True)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            self.assertEqual(leak_check.run([]), 1)

    def test_cwd_differs_from_ai_tooling_checks_cache_twice(self):
        """Running from a consumer repo checks that repo's own cache layout
        in addition to ai_tooling's, so leaks in either are caught.
        """
        ai_root = Path('/repo/ai_tooling')
        cwd_root = Path('/repo/consumer')
        patches = self._patches(False, False, False, False, ai_root, cwd_root)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6] as mock_cache:
            leak_check.run([])
        self.assertEqual(mock_cache.call_count, 2)

    def test_cwd_same_as_ai_tooling_checks_cache_once(self):
        """Running from inside ai_tooling itself checks its cache layout only
        once — the same repo is never checked twice.
        """
        root = Path('/repo')
        patches = self._patches(False, False, False, False, root, root)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6] as mock_cache:
            leak_check.run([])
        self.assertEqual(mock_cache.call_count, 1)

    def test_cwd_outside_any_repo_checks_cache_once(self):
        """Running outside any git repo still checks ai_tooling's own cache
        layout — there is no second repo to check.
        """
        root = Path('/repo')
        patches = self._patches(False, False, False, False, root, None)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6] as mock_cache:
            leak_check.run([])
        self.assertEqual(mock_cache.call_count, 1)


if __name__ == '__main__':
    unittest.main()
