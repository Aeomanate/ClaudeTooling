#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Tests for git_hooks_impl.plan.git_utils.detect_nearest_parent_branch.

detect_nearest_parent_branch()'s only dependency is git_utils.run() (a thin
subprocess wrapper). Mocked at the git_utils import location per the Main
Mock Rule with a fake that pattern-matches each git command shape and
returns a scripted (exit_code, stdout, stderr) - no real git process, no
real repo. These tests used to build a real git repo in a tempdir per
test; that made the whole class the slowest part of the suite (subprocess
spawn cost, several checkouts and commits per test) to verify an algorithm
that is pure command-sequencing logic, not git's own ancestry computation.
"""

import unittest
from unittest.mock import patch

from git_hooks_impl.plan.git_utils import detect_nearest_parent_branch
from git_hooks_impl.utils import TARGET_BRANCH

_MOD = 'git_hooks_impl.plan.git_utils'


def _fake_run(current_branch, master_sha, refs, ancestors=None, distances=None, shas=None):
    """Builds a run() replacement scripted for one test's repo topology.

    current_branch: value `git rev-parse --abbrev-ref HEAD` returns.
    master_sha: value `git rev-parse master` returns.
    refs: local branch names `git for-each-ref` lists (master included).
    ancestors: {branch: True/False} for `git merge-base --is-ancestor`.
    distances: {branch: commit_count} for `git rev-list --count master..branch`.
    shas: {branch: sha} for the winning candidate's `git rev-parse <branch>`.
    """
    ancestors = ancestors or {}
    distances = distances or {}
    shas = shas or {}

    def fake(cmd):
        if cmd[:3] == ['git', 'rev-parse', TARGET_BRANCH]:
            return (0, master_sha + '\n', '')
        if cmd[:4] == ['git', 'rev-parse', '--abbrev-ref', 'HEAD']:
            return (0, current_branch + '\n', '')
        if cmd[:2] == ['git', 'for-each-ref']:
            return (0, '\n'.join(refs) + '\n', '')
        if cmd[:3] == ['git', 'merge-base', '--is-ancestor']:
            candidate = cmd[3]
            return (0, '', '') if ancestors.get(candidate) else (1, '', '')
        if cmd[:3] == ['git', 'rev-list', '--count']:
            candidate = cmd[3].split('..', 1)[1]
            return (0, f'{distances.get(candidate, 0)}\n', '')
        if cmd[:2] == ['git', 'rev-parse']:
            candidate = cmd[2]
            sha = shas.get(candidate, '')
            return (0, sha + '\n', '') if sha else (1, '', 'unknown revision')
        raise AssertionError(f'unscripted git command in test: {cmd}')

    return fake


class TestDetectNearestParentBranch(unittest.TestCase):

    def test_returns_master_when_no_other_branches(self):
        """Single branch repo -> (TARGET_BRANCH, master_sha)."""
        fake = _fake_run(current_branch='master', master_sha='masterSHA', refs=['master'])
        with patch(f'{_MOD}.run', side_effect=fake):
            name, sha = detect_nearest_parent_branch()
        self.assertEqual(name, TARGET_BRANCH)
        self.assertEqual(sha, 'masterSHA')

    def test_returns_deepest_parent(self):
        """feature/child stacked on feature/parent -> (feature/parent, parent_sha)."""
        fake = _fake_run(
            current_branch='feature/child',
            master_sha='masterSHA',
            refs=['master', 'feature/parent', 'feature/child'],
            ancestors={'feature/parent': True},
            distances={'feature/parent': 1},
            shas={'feature/parent': 'parentSHA'},
        )
        with patch(f'{_MOD}.run', side_effect=fake):
            name, sha = detect_nearest_parent_branch()
        self.assertEqual(name, 'feature/parent')
        self.assertEqual(sha, 'parentSHA')

    def test_falls_back_to_master_on_detached_head(self):
        """Detached HEAD ('HEAD' itself, already excluded) -> master fallback."""
        fake = _fake_run(current_branch='HEAD', master_sha='masterSHA', refs=['master'])
        with patch(f'{_MOD}.run', side_effect=fake):
            name, sha = detect_nearest_parent_branch()
        self.assertEqual(name, TARGET_BRANCH)
        self.assertEqual(sha, 'masterSHA')

    def test_skips_non_ancestor(self):
        """Sibling branch not ancestor of HEAD -> master fallback."""
        fake = _fake_run(
            current_branch='feature/work',
            master_sha='masterSHA',
            refs=['master', 'feature/sibling', 'feature/work'],
            ancestors={'feature/sibling': False},
        )
        with patch(f'{_MOD}.run', side_effect=fake):
            name, sha = detect_nearest_parent_branch()
        self.assertEqual(name, TARGET_BRANCH)

    def test_skips_default_branch_itself(self):
        """master/main excluded; single feature branch off master -> master fallback."""
        fake = _fake_run(
            current_branch='feature/x',
            master_sha='masterSHA',
            refs=['master', 'feature/x'],
        )
        with patch(f'{_MOD}.run', side_effect=fake):
            name, sha = detect_nearest_parent_branch()
        self.assertEqual(name, TARGET_BRANCH)
        self.assertEqual(sha, 'masterSHA')

    def test_picks_deepest_among_multiple_ancestors(self):
        """Two parent branches at different depths: must pick the deeper one.

        master: M
        feature/A: M -> A1          (master..A = 1 commit)
        feature/B: M -> A1 -> B1 -> B2  (master..B = 3 commits)
        feature/current: M -> A1 -> B1 -> B2 -> C1

        Expected: feature/B (deeper) not feature/A (shallower).
        This specifically tests the metric direction: master..candidate,
        not candidate..master.
        """
        fake = _fake_run(
            current_branch='feature/current',
            master_sha='masterSHA',
            refs=['master', 'feature/A', 'feature/B', 'feature/current'],
            ancestors={'feature/A': True, 'feature/B': True},
            distances={'feature/A': 1, 'feature/B': 3},
            shas={'feature/A': 'aSHA', 'feature/B': 'bSHA'},
        )
        with patch(f'{_MOD}.run', side_effect=fake):
            name, sha = detect_nearest_parent_branch()
        self.assertEqual(name, 'feature/B')
        self.assertEqual(sha, 'bSHA')


if __name__ == '__main__':
    unittest.main()
