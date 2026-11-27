#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for hooks/extract_plan.py — file categorization into omission tiers
for the diff-context token budget, branch-derived plan titles, merge-base
resolution against TARGET_BRANCH/main, the 3-way git merge-file auto-merge
helper, handling of an existing PLAN section on the MR (hash match / identical
/ conflict), and SHA-to-branch-name resolution for cache swap.

Run:  python -m unittest discover -s .git-hooks/hooks/tests -t .git-hooks -p "test_extract_plan_generation.py" -v
"""

import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

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
    _categorize_files,
    _collect_context_for_generation,
    _get_merge_base,
    _handle_existing_plan,
    _title_from_branch,
)
from git_hooks_impl.plan.cache import _resolve_branch_from_ref
from git_hooks_impl.plan.merge import _try_auto_merge
from git_hooks_impl.plan.parser import embed_plan_hash

# ---------------------------------------------------------------------------
#  File categorization for omission tiers
# ---------------------------------------------------------------------------

class TestOmissionTiers(unittest.IsolatedAsyncioTestCase):

    def test_omits_tests_first(self):
        """Test files go to 'tests' tier (highest priority to omit).
        Matched by: test_* prefix, tests/ directory, *_test.* suffix.
        Examples: tests/test_foo.py, src/tests/helper.py, lib/bar_test.cpp.

        Function under test: _categorize_files()
        Refactoring required: NO (pure function)
        Dependency missed/absent: NO
        """
        files = [
            ('tests/test_foo.py', 100),
            ('src/main.py', 200),
            ('src/tests/helper.py', 50),
            ('lib/bar_test.cpp', 75),
        ]
        tiers = _categorize_files(files)
        test_paths = [p for p, _ in tiers['tests']]
        self.assertIn('tests/test_foo.py', test_paths)
        self.assertIn('src/tests/helper.py', test_paths)
        self.assertIn('lib/bar_test.cpp', test_paths)
        self.assertNotIn('src/main.py', test_paths)

    def test_omits_configs_second(self):
        """Config/generated files go to 'configs' tier (second priority).
        Matched by: .json, .lock, .cmake extensions, docs/ directory.
        Examples: package.json, yarn.lock, CMakeLists.cmake, docs/readme.md.
        src/main.py does NOT match -- it goes to 'keep'.

        Function under test: _categorize_files()
        Refactoring required: NO (pure function)
        Dependency missed/absent: NO
        """
        files = [
            ('package.json', 100),
            ('yarn.lock', 500),
            ('CMakeLists.cmake', 50),
            ('docs/readme.md', 30),
            ('src/main.py', 200),
        ]
        tiers = _categorize_files(files)
        config_paths = [p for p, _ in tiers['configs']]
        self.assertIn('package.json', config_paths)
        self.assertIn('yarn.lock', config_paths)
        self.assertIn('CMakeLists.cmake', config_paths)
        self.assertIn('docs/readme.md', config_paths)

    def test_omission_order_preserved(self):
        """Each file lands in exactly one tier: test_a.py -> tests,
        config.json -> configs, src/core.py -> keep.  No file is categorized
        into multiple tiers.

        Function under test: _categorize_files()
        Refactoring required: NO (pure function)
        Dependency missed/absent: NO
        """
        files = [
            ('test_a.py', 100),
            ('config.json', 50),
            ('src/core.py', 200),
        ]
        tiers = _categorize_files(files)
        self.assertEqual(len(tiers['tests']), 1)
        self.assertEqual(len(tiers['configs']), 1)
        self.assertEqual(len(tiers['keep']), 1)
        self.assertEqual(tiers['keep'][0][0], 'src/core.py')

    async def test_falls_back_to_diffstat(self):
        """All omission tiers exhausted and still over budget -> last resort.
        src/huge.py alone is >600k chars.  After omitting test_x.py (tier 1) and
        data.json (tier 2), remaining is still over budget -> falls back to
        commit messages + diffstat summary only (no full diff in context).

        Function under test: _collect_context_for_generation()
        Refactoring required: YES (82 lines, 7 deps)
        Dependency missed/absent: NO
        """
        huge_file = ('src/huge.py', _TOKEN_BUDGET_CHARS + 100)
        test_file = ('test_x.py', 50)
        config_file = ('data.json', 30)
        over_diff = 'x' * (_TOKEN_BUDGET_CHARS + 200)
        with patch('git_hooks_impl.entry_points.extract_plan._get_merge_base', return_value='abc'), \
             patch('git_hooks_impl.entry_points.extract_plan._get_commit_messages', return_value='msg'), \
             patch('git_hooks_impl.entry_points.extract_plan._get_diff_stat', return_value='1 file changed'), \
             patch('git_hooks_impl.entry_points.extract_plan._get_full_diff', return_value=over_diff), \
             patch('git_hooks_impl.entry_points.extract_plan._get_diff_files', return_value=[huge_file, test_file, config_file]), \
             patch('git_hooks_impl.entry_points.extract_plan.jira_summary', new_callable=AsyncMock, return_value=('', '')):
            parts = await _collect_context_for_generation('branch', '')
        # Should have fallen back to diffstat
        found_diffstat = any('Diffstat' in p for p in parts)
        self.assertTrue(found_diffstat, 'Should fall back to diffstat when all tiers exhausted')


# ---------------------------------------------------------------------------
#  Title derivation
# ---------------------------------------------------------------------------

class TestTitleFromBranch(unittest.TestCase):

    def test_with_jira_and_summary(self):
        """Ticket + Jira summary -> '[PROJECTNAME-1] Fix crash' (summary used verbatim).

        Function under test: _title_from_branch()
        Refactoring required: NO (pure function)
        Dependency missed/absent: NO
        """
        # productname/fixes/PROJECTNAME-1_fix + Jira "Fix crash" -> [PROJECTNAME-1] Fix crash
        # productname/fixes/PROJECTNAME-1_fix + Jira "Fix crash" -> [PROJECTNAME-1] Fix crash
        self.assertEqual(
            _title_from_branch('productname/fixes/PROJECTNAME-1_fix', 'PROJECTNAME-1', 'Fix crash'),
            _title_from_branch('productname/fixes/PROJECTNAME-1_fix', 'PROJECTNAME-1', 'Fix crash'),
            '[PROJECTNAME-1] Fix crash',
        )

    def test_without_jira(self):
        """No ticket -> derive from branch tail: my_cool_fix -> 'My cool fix'.

        Function under test: _title_from_branch()
        Refactoring required: NO (pure function)
        Dependency missed/absent: NO
        """
        # productname/fixes/my_cool_fix -> "My cool fix"
        # productname/fixes/my_cool_fix -> "My cool fix"
        self.assertEqual(
            _title_from_branch('productname/fixes/my_cool_fix', '', ''),
            _title_from_branch('productname/fixes/my_cool_fix', '', ''),
            'My cool fix',
        )

    def test_strips_ticket_prefix(self):
        """No ticket passed but branch has one -> strip it: PROJECTNAME-1234_race_fix -> 'Race fix'.

        Function under test: _title_from_branch()
        Refactoring required: NO (pure function)
        Dependency missed/absent: NO
        """
        # productname/fixes/PROJECTNAME-1234_race_fix (no ticket arg) -> "Race fix"
        # productname/fixes/PROJECTNAME-1234_race_fix (no ticket arg) -> "Race fix"
        self.assertEqual(
            _title_from_branch('productname/fixes/PROJECTNAME-1234_race_fix', '', ''),
            _title_from_branch('productname/fixes/PROJECTNAME-1234_race_fix', '', ''),
            'Race fix',
        )

    def test_ticket_only_no_summary(self):
        """Ticket present but Jira summary empty -> derive from branch tail, capitalised.
        productname/fixes/PROJECTNAME-1234_race_fix + PROJECTNAME-1234 -> '[PROJECTNAME-1234] Race fix'.
        productname/fixes/PROJECTNAME-1234_race_fix + PROJECTNAME-1234 -> '[PROJECTNAME-1234] Race fix'.

        Function under test: _title_from_branch()
        Refactoring required: NO (pure function)
        Dependency missed/absent: NO
        """
        self.assertEqual(
            _title_from_branch('productname/fixes/PROJECTNAME-1234_race_fix', 'PROJECTNAME-1234', ''),
            _title_from_branch('productname/fixes/PROJECTNAME-1234_race_fix', 'PROJECTNAME-1234', ''),
            '[PROJECTNAME-1234] Race fix',
        )


# ---------------------------------------------------------------------------
#  Merge-base branch selection
# ---------------------------------------------------------------------------

class TestGetMergeBase(unittest.TestCase):
    """Tests for _get_merge_base() — TARGET_BRANCH-first fallback to main."""

    @patch('git_hooks_impl.entry_points.extract_plan.run')
    def test_merge_base_prefers_target_branch(self, mock_run):
        """TARGET_BRANCH succeeds -> returns its SHA, never tries main.
        refs=(TARGET_BRANCH, 'main'), first hit -> 'aaa111'.

        Function under test: _get_merge_base()
        Refactoring required: NO (12 lines, 1 dep: run)
        Dependency missed/absent: NO
        """
        mock_run.return_value = (0, 'aaa111\n', '')
        result = _get_merge_base()
        self.assertEqual(result, 'aaa111')
        mock_run.assert_called_once()

    @patch('git_hooks_impl.entry_points.extract_plan.run')
    def test_merge_base_falls_back_to_main(self, mock_run):
        """TARGET_BRANCH fails (rc=1), 'main' succeeds -> 'bbb222'.
        Two calls: first fails, second returns main merge-base.

        Function under test: _get_merge_base()
        Refactoring required: NO (12 lines, 1 dep: run)
        Dependency missed/absent: NO
        """
        mock_run.side_effect = [
            (1, '', ''),            # TARGET_BRANCH — not found
            (0, 'bbb222\n', ''),    # 'main' — success
        ]
        result = _get_merge_base()
        self.assertEqual(result, 'bbb222')
        self.assertEqual(mock_run.call_count, 2)


# ---------------------------------------------------------------------------
#  _try_auto_merge — 3-way merge via git merge-file
# ---------------------------------------------------------------------------

class TestTryAutoMerge(unittest.TestCase):
    """3-way merge: base + local + remote -> merged via git merge-file."""

    @patch('subprocess.run')
    def test_clean_merge_returns_merged_content(self, mock_subprocess):
        """rc=0 from git merge-file -> returns decoded stdout (merged content).

        base='A\\nB', local='A\\nB\\nC', remote='A-edit\\nB' -> merged output.

        Function under test: _try_auto_merge()
        Refactoring required: NO (plan_merge function, 2 deps: subprocess.run, tempfile)
        Dependency missed/absent: NO
        """
        mock_subprocess.return_value = MagicMock(
            returncode=0,
            stdout=b'merged content here\n',
        )
        with patch('os.remove'):
            result = _try_auto_merge('base', 'local', 'remote')
        self.assertEqual(result, 'merged content here\n')

    @patch('subprocess.run')
    def test_conflict_returns_none(self, mock_subprocess):
        """rc>0 from git merge-file (conflict markers) -> returns None.

        Overlapping changes -> caller falls back to dialog.

        Function under test: _try_auto_merge()
        Refactoring required: NO (plan_merge function, 2 deps: subprocess.run, tempfile)
        Dependency missed/absent: NO
        """
        mock_subprocess.return_value = MagicMock(
            returncode=1,
            stdout=b'<<<<<<< local\nfoo\n=======\nbar\n>>>>>>> remote\n',
        )
        with patch('os.remove'):
            result = _try_auto_merge('base', 'local', 'remote')
        self.assertIsNone(result)

    def test_exception_returns_none(self):
        """subprocess.run raises exception -> returns None (graceful fallback).

        git merge-file not found / timeout / OS error -> None.

        Function under test: _try_auto_merge()
        Refactoring required: NO (plan_merge function, 2 deps: subprocess.run, tempfile)
        Dependency missed/absent: NO
        """
        with patch('subprocess.run', side_effect=OSError('git not found')):
            result = _try_auto_merge('base', 'local', 'remote')
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
#  _handle_existing_plan — hash check, conflict resolution on pull
# ---------------------------------------------------------------------------

class TestHandleExistingPlan(unittest.TestCase):
    """MR has PLAN section: decide whether to pull, skip, or resolve conflict."""

    def test_hash_match_keeps_local(self):
        """MR plan unchanged since push -> skip, local file untouched.

        _should_overwrite_plan='hash_match' -> ok() message, return 0.

        Function under test: _handle_existing_plan()
        """
        stamped = embed_plan_hash('# Plan\nOriginal\n')
        with patch('git_hooks_impl.entry_points.extract_plan._should_overwrite_plan',
                   return_value='hash_match'), \
             patch('git_hooks_impl.entry_points.extract_plan._write_plan') as mock_write:
            result = _handle_existing_plan(stamped, 42, 'feature/x')
        self.assertEqual(result, 0)
        mock_write.assert_not_called()

    def test_content_identical_is_noop(self):
        """Local and MR content identical after stripping meta -> skip.

        _should_overwrite_plan='identical' -> ok() message, return 0, no write.

        Function under test: _handle_existing_plan()
        """
        content = '# Plan\nSame content\n' + 'x' * 100
        with patch('git_hooks_impl.entry_points.extract_plan._should_overwrite_plan',
                   return_value='identical'), \
             patch('git_hooks_impl.entry_points.extract_plan._write_plan') as mock_write:
            result = _handle_existing_plan(content, 42, 'feature/x')
        self.assertEqual(result, 0)
        mock_write.assert_not_called()

    def test_conflict_case_calls_resolve(self):
        """Both sides diverged -> _resolve_conflict called, result written.

        _should_overwrite_plan='conflict' triggers the interactive resolution path.

        Function under test: _handle_existing_plan()
        """
        local_text = '# Plan\nLocal version\n' + 'x' * 100
        remote_text = '# Plan\nRemote version\n' + 'y' * 100
        with tempfile.TemporaryDirectory() as tmp:
            plan_file = os.path.join(tmp, 'PLAN.md')
            with open(plan_file, 'w') as f:
                f.write(local_text)
            with patch('git_hooks_impl.entry_points.extract_plan.PLAN_FILE', plan_file), \
                 patch('git_hooks_impl.entry_points.extract_plan._should_overwrite_plan',
                       return_value='conflict'), \
                 patch('git_hooks_impl.entry_points.extract_plan._resolve_conflict',
                       return_value=('remote', remote_text)) as mock_resolve, \
                 patch('git_hooks_impl.entry_points.extract_plan._write_plan') as mock_write, \
                 patch('git_hooks_impl.entry_points.extract_plan._save_cache') as mock_cache:
                result = _handle_existing_plan(remote_text, 42, 'feature/x')
            self.assertEqual(result, 0)
            mock_resolve.assert_called_once()
            mock_write.assert_called_once()
            mock_cache.assert_called_once()


# ---------------------------------------------------------------------------
#  _resolve_branch_from_ref — SHA -> branch name via git name-rev
# ---------------------------------------------------------------------------

class TestResolveBranchFromRef(unittest.TestCase):
    """Resolve a SHA ref to a branch name, filtering tags and undefined."""

    @patch('git_hooks_impl.plan.cache.run')
    def test_tag_ref_returns_empty(self, mock_run):
        """Git name-rev returns 'tags/v1.0' -> '' (tags are not branches).

        Tag refs cannot be used for cache swap -- filtered out.

        Function under test: _resolve_branch_from_ref()
        Refactoring required: NO (17 lines, 1 dep: plan_cache.run)
        Dependency missed/absent: NO
        """
        mock_run.return_value = (0, 'tags/v1.0\n', '')
        result = _resolve_branch_from_ref('abc123')
        self.assertEqual(result, '')

    @patch('git_hooks_impl.plan.cache.run')
    def test_suffix_strip(self, mock_run):
        """Git name-rev returns 'feature/x~2' -> 'feature/x' (suffix stripped).

        Trailing ~N or ^N from merge commits -> cleaned off.

        Function under test: _resolve_branch_from_ref()
        Refactoring required: NO (17 lines, 1 dep: plan_cache.run)
        Dependency missed/absent: NO
        """
        mock_run.return_value = (0, 'feature/x~2\n', '')
        result = _resolve_branch_from_ref('abc123')
        self.assertEqual(result, 'feature/x')

    @patch('git_hooks_impl.plan.cache.run')
    def test_normal_branch_name(self, mock_run):
        """Git name-rev returns 'productname/fixes/PROJECTNAME-1_fix' -> same string returned.
        """Git name-rev returns 'productname/fixes/PROJECTNAME-1_fix' -> same string returned.

        Clean branch name, no suffix -> pass through unchanged.

        Function under test: _resolve_branch_from_ref()
        Refactoring required: NO (17 lines, 1 dep: plan_cache.run)
        Dependency missed/absent: NO
        """
        mock_run.return_value = (0, 'productname/fixes/PROJECTNAME-1_fix\n', '')
        mock_run.return_value = (0, 'productname/fixes/PROJECTNAME-1_fix\n', '')
        result = _resolve_branch_from_ref('abc123')
        self.assertEqual(result, 'productname/fixes/PROJECTNAME-1_fix')
        self.assertEqual(result, 'productname/fixes/PROJECTNAME-1_fix')

    def test_empty_ref_returns_empty(self):
        """Empty ref string -> '' (early return, no git call).

        Function under test: _resolve_branch_from_ref()
        Refactoring required: NO (17 lines, 1 dep: plan_cache.run)
        Dependency missed/absent: NO
        """
        result = _resolve_branch_from_ref('')
        self.assertEqual(result, '')

    @patch('git_hooks_impl.plan.cache.run')
    def test_undefined_returns_empty(self, mock_run):
        """Git name-rev returns 'undefined' (detached HEAD) -> ''.

        Detached HEAD or ambiguous refs produce 'undefined'.

        Function under test: _resolve_branch_from_ref()
        Refactoring required: NO (17 lines, 1 dep: plan_cache.run)
        Dependency missed/absent: NO
        """
        mock_run.return_value = (0, 'undefined\n', '')
        result = _resolve_branch_from_ref('abc123')
        self.assertEqual(result, '')


if __name__ == '__main__':
    unittest.main(verbosity=2)
