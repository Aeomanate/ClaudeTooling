"""Tests for setup/_link_helpers.py prune logic.

Covers the three-bug fix to mr setup pruning:
- Bug A non-change: _prune_flat_directory still prefix-protects shared namespaces.
- Bug B fix: _prune_managed_skill_orphan_files surfaces file-level orphans
  inside ai_tooling-managed skill subtrees.
- Bug C fix: _prune_recursive_directory skips the user-file guard inside
  managed namespaces (orphan subtree with stale ai_tooling files inside is
  safe to prune within managed namespace, NOT safe outside).
"""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from setup._link_helpers import (
    AI_TOOLING_MANAGED_SKILLS,
    PruneStatError,
    _is_linked,
    _link_directory_recursive,
    _prune_flat_directory,
    _prune_managed_skill_orphan_files,
    _prune_recursive_directory,
    _resolves_to_source,
)


def _touch(path, content=''):
    """Create a regular file (not a symlink) with given content."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def _symlink_into(source_file, target_file):
    """Create a symlink at target_file pointing at source_file."""
    os.makedirs(os.path.dirname(target_file), exist_ok=True)
    os.symlink(source_file, target_file)


class TestPruneManagedSkillOrphanFiles(unittest.TestCase):
    """Bug B fix: file-level orphan detection inside managed skill subtree."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.source_skills = os.path.join(self.tmp, 'source', 'skills')
        self.target_skills = os.path.join(self.tmp, 'target', 'skills')
        os.makedirs(self.source_skills)
        os.makedirs(self.target_skills)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_orphan_file_in_managed_subtree_detected(self):
        """File in target/orchestrator/ without source counterpart -> orphan."""
        _touch(os.path.join(self.source_skills, 'orchestrator', 'live.md'))
        _touch(os.path.join(self.target_skills, 'orchestrator', 'live.md'))
        _touch(os.path.join(self.target_skills, 'orchestrator', 'orphan.md'))

        orphans = _prune_managed_skill_orphan_files(
            self.source_skills, self.target_skills, ('orchestrator',))

        expected = os.path.join(self.target_skills, 'orchestrator', 'orphan.md')
        self.assertEqual(orphans, [expected])

    def test_symlinked_file_present_in_source_not_orphan(self):
        """Symlinked file that resolves to source counterpart -> not orphan."""
        source_file = os.path.join(self.source_skills, 'orchestrator', 'live.md')
        target_file = os.path.join(self.target_skills, 'orchestrator', 'live.md')
        _touch(source_file, 'content')
        _symlink_into(source_file, target_file)

        orphans = _prune_managed_skill_orphan_files(
            self.source_skills, self.target_skills, ('orchestrator',))

        self.assertEqual(orphans, [])

    def test_file_in_non_managed_skill_not_flagged(self):
        """File under skills/<non-managed>/ -> not considered (user content)."""
        _touch(os.path.join(self.source_skills, 'orchestrator', 'live.md'))
        _touch(os.path.join(self.target_skills, 'user-skill', 'note.md'))

        orphans = _prune_managed_skill_orphan_files(
            self.source_skills, self.target_skills, ('orchestrator',))

        self.assertEqual(orphans, [])

    def test_orphan_file_in_nested_managed_subtree_detected(self):
        """Orphan in target/orchestrator/roles/x/old.md -> detected."""
        _touch(os.path.join(self.source_skills, 'orchestrator', 'SKILL.md'))
        _touch(os.path.join(self.target_skills, 'orchestrator', 'SKILL.md'))
        _touch(os.path.join(self.target_skills, 'orchestrator', 'roles',
                            'planner', 'old.md'))

        orphans = _prune_managed_skill_orphan_files(
            self.source_skills, self.target_skills, ('orchestrator',))

        expected = os.path.join(self.target_skills, 'orchestrator', 'roles',
                                'planner', 'old.md')
        self.assertEqual(orphans, [expected])

    def test_returns_empty_when_managed_skill_absent_in_source(self):
        """No source/orchestrator/ -> no orphans collected for orchestrator."""
        _touch(os.path.join(self.target_skills, 'orchestrator', 'something.md'))

        orphans = _prune_managed_skill_orphan_files(
            self.source_skills, self.target_skills, ('orchestrator',))

        self.assertEqual(orphans, [])

    def test_default_managed_skills_includes_orchestrator(self):
        """AI_TOOLING_MANAGED_SKILLS default applied when arg omitted."""
        self.assertIn('orchestrator', AI_TOOLING_MANAGED_SKILLS)
        _touch(os.path.join(self.source_skills, 'orchestrator', 'a.md'))
        _touch(os.path.join(self.target_skills, 'orchestrator', 'a.md'))
        _touch(os.path.join(self.target_skills, 'orchestrator', 'b.md'))

        orphans = _prune_managed_skill_orphan_files(
            self.source_skills, self.target_skills)

        expected = os.path.join(self.target_skills, 'orchestrator', 'b.md')
        self.assertEqual(orphans, [expected])


class TestPruneRecursiveDirectoryManagedNamespace(unittest.TestCase):
    """Bug C fix: orphan subtree under managed namespace prunes despite stale files inside."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.source_skills = os.path.join(self.tmp, 'source', 'skills')
        self.target_skills = os.path.join(self.tmp, 'target', 'skills')
        os.makedirs(self.source_skills)
        os.makedirs(self.target_skills)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_orphan_subtree_in_managed_namespace_pruned_despite_stale_files(self):
        """target/orchestrator/scripts/ (no source counterpart, stale files inside) -> flagged."""
        _touch(os.path.join(self.source_skills, 'orchestrator', 'SKILL.md'))
        # Orphan subtree with stale ai_tooling files (non-source inodes).
        _touch(os.path.join(self.target_skills, 'orchestrator', 'scripts',
                            'old1.sh'))
        _touch(os.path.join(self.target_skills, 'orchestrator', 'scripts',
                            'old2.sh'))

        orphans = _prune_recursive_directory(
            self.source_skills, self.target_skills, ('orchestrator',))

        expected = os.path.join(self.target_skills, 'orchestrator', 'scripts')
        self.assertIn(expected, orphans)

    def test_orphan_subtree_outside_managed_with_user_file_preserved(self):
        """target/user-skill/ with foreign-inode files -> NOT flagged (user content protected)."""
        _touch(os.path.join(self.source_skills, 'orchestrator', 'SKILL.md'))
        _touch(os.path.join(self.target_skills, 'user-skill', 'notes.md'),
               'user content')

        orphans = _prune_recursive_directory(
            self.source_skills, self.target_skills, ('orchestrator',))

        user_path = os.path.join(self.target_skills, 'user-skill')
        self.assertNotIn(user_path, orphans)

    def test_orphan_subtree_outside_managed_with_only_source_inodes_pruned(self):
        """target/user-skill/ where every file IS a source symlink -> safe to prune."""
        source_file = os.path.join(self.source_skills, 'orchestrator', 'SKILL.md')
        _touch(source_file)
        # Symlink the same source into a non-managed namespace; safe to prune.
        target_subtree = os.path.join(self.target_skills, 'user-skill', 'mirror.md')
        _symlink_into(source_file, target_subtree)

        orphans = _prune_recursive_directory(
            self.source_skills, self.target_skills, ('orchestrator',))

        self.assertIn(os.path.join(self.target_skills, 'user-skill'), orphans)

    def test_existing_source_subtree_not_pruned(self):
        """target/orchestrator/roles/ exists in source -> not orphan."""
        _touch(os.path.join(self.source_skills, 'orchestrator', 'roles',
                            'fixer', 'rules.md'))
        _touch(os.path.join(self.target_skills, 'orchestrator', 'roles',
                            'fixer', 'rules.md'))

        orphans = _prune_recursive_directory(
            self.source_skills, self.target_skills, ('orchestrator',))

        roles = os.path.join(self.target_skills, 'orchestrator', 'roles')
        self.assertNotIn(roles, orphans)


class TestPruneFlatDirectoryRegression(unittest.TestCase):
    """Bug A non-change: prefix protection on shared namespaces still works."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.source_dir = os.path.join(self.tmp, 'source')
        self.target_dir = os.path.join(self.tmp, 'target')
        os.makedirs(self.source_dir)
        os.makedirs(self.target_dir)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_prefix_matched_file_without_source_counterpart_flagged(self):
        """orchestrator-old.md in target, not in source -> orphan."""
        live_source = os.path.join(self.source_dir, 'orchestrator-live.md')
        live_target = os.path.join(self.target_dir, 'orchestrator-live.md')
        _touch(live_source)
        # live target must symlink to source so the inode check matches; a
        # standalone _touch would give it a foreign inode and flag it as orphan.
        _symlink_into(live_source, live_target)
        _touch(os.path.join(self.target_dir, 'orchestrator-old.md'))

        orphans = _prune_flat_directory(
            self.source_dir, self.target_dir, 'orchestrator-')

        expected = os.path.join(self.target_dir, 'orchestrator-old.md')
        self.assertEqual(orphans, [expected])

    def test_non_prefix_file_not_flagged_even_without_source(self):
        """user-note.md (no orchestrator- prefix) -> not orphan (protected)."""
        _touch(os.path.join(self.source_dir, 'orchestrator-live.md'))
        _touch(os.path.join(self.target_dir, 'user-note.md'), 'mine')

        orphans = _prune_flat_directory(
            self.source_dir, self.target_dir, 'orchestrator-')

        self.assertEqual(orphans, [])

    def test_symlinked_file_with_source_counterpart_not_orphan(self):
        """orchestrator-live.md symlinked to source -> not orphan."""
        source = os.path.join(self.source_dir, 'orchestrator-live.md')
        target = os.path.join(self.target_dir, 'orchestrator-live.md')
        _touch(source)
        _symlink_into(source, target)

        orphans = _prune_flat_directory(
            self.source_dir, self.target_dir, 'orchestrator-')

        self.assertEqual(orphans, [])


class TestLinkDirectoryRecursiveSymlinkedSubtree(unittest.TestCase):
    """Regression: a subtree whose target dir is already a directory-level
    symlink into source must not be walked file-by-file. Walking it computes
    per-file target paths that physically resolve back into source_dir —
    os.remove() deletes the real source file, os.symlink() recreates it
    pointing at itself.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.source_dir = os.path.join(self.tmp, 'source', 'skills')
        self.target_dir = os.path.join(self.tmp, 'target', 'skills')
        os.makedirs(self.source_dir)
        os.makedirs(self.target_dir)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_symlinked_subdir_not_corrupted(self):
        """target/orchestrator already a dir-symlink into source/orchestrator ->
        file inside is untouched, not replaced with a self-referential symlink.
        """
        source_skill = os.path.join(self.source_dir, 'orchestrator')
        nested_file = os.path.join(source_skill, 'roles', 'coder', 'rules.md')
        _touch(nested_file, 'original content')

        target_skill = os.path.join(self.target_dir, 'orchestrator')
        os.symlink(source_skill, target_skill)

        _link_directory_recursive(self.source_dir, self.target_dir)

        self.assertFalse(os.path.islink(nested_file))
        with open(nested_file, encoding='utf-8') as f:
            self.assertEqual(f.read(), 'original content')

    def test_unsymlinked_subdir_still_linked_normally(self):
        """A plain (non-symlinked) subdir still gets its files linked file-by-file."""
        source_skill = os.path.join(self.source_dir, 'other-skill')
        nested_file = os.path.join(source_skill, 'nested', 'file.md')
        _touch(nested_file, 'content')

        linked, up_to_date = _link_directory_recursive(self.source_dir, self.target_dir)

        target_file = os.path.join(self.target_dir, 'other-skill', 'nested', 'file.md')
        self.assertTrue(os.path.islink(target_file))
        self.assertEqual(os.path.realpath(target_file), os.path.realpath(nested_file))
        self.assertEqual((linked, up_to_date), (1, 0))


class TestResolvesToSource(unittest.TestCase):
    """_resolves_to_source recognizes a file reached through a symlinked
    ancestor directory, which _is_linked reports as not-linked since the
    leaf itself isn't a symlink.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_leaf_reached_via_symlinked_ancestor_dir(self):
        """target/skill is a dir-symlink into source/skill -> a file inside
        resolves to source even though the leaf itself is not a symlink.
        """
        source_skill = os.path.join(self.tmp, 'source', 'skill')
        source_file = os.path.join(source_skill, 'SKILL.md')
        _touch(source_file, 'content')

        target_skill = os.path.join(self.tmp, 'target', 'skill')
        os.makedirs(os.path.dirname(target_skill))
        os.symlink(source_skill, target_skill)
        target_file = os.path.join(target_skill, 'SKILL.md')

        self.assertFalse(os.path.islink(target_file))
        self.assertFalse(_is_linked(source_file, target_file))
        self.assertTrue(_resolves_to_source(source_file, target_file))

    def test_direct_leaf_symlink_still_resolves(self):
        """A plain per-file symlink still resolves (not ancestor-dependent)."""
        source_file = os.path.join(self.tmp, 'source', 'file.md')
        _touch(source_file, 'content')

        target_file = os.path.join(self.tmp, 'target', 'file.md')
        _symlink_into(source_file, target_file)

        self.assertTrue(_resolves_to_source(source_file, target_file))

    def test_unlinked_file_does_not_resolve(self):
        """A regular, unrelated file at the target path does not resolve."""
        source_file = os.path.join(self.tmp, 'source', 'file.md')
        _touch(source_file, 'content')

        target_file = os.path.join(self.tmp, 'target', 'file.md')
        _touch(target_file, 'different content')

        self.assertFalse(_resolves_to_source(source_file, target_file))

    def test_missing_target_does_not_resolve(self):
        """A target path that doesn't exist at all does not resolve."""
        source_file = os.path.join(self.tmp, 'source', 'file.md')
        _touch(source_file, 'content')

        target_file = os.path.join(self.tmp, 'target', 'missing.md')

        self.assertFalse(_resolves_to_source(source_file, target_file))


class TestPruneStatErrorRegression(unittest.TestCase):
    """Regression: an OSError from os.stat() while building the SOURCE-side
    inode set must raise PruneStatError rather than being silently swallowed
    (which previously could misreport a live source file as an orphan).
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_flat_directory_source_stat_error_raises(self):
        """os.stat() failing on the sole source file during the source_inodes
        build in _prune_flat_directory must raise PruneStatError.
        """
        source_dir = os.path.join(self.tmp, 'source')
        target_dir = os.path.join(self.tmp, 'target')
        os.makedirs(source_dir)
        os.makedirs(target_dir)
        source_file = os.path.join(source_dir, 'orchestrator-live.md')
        _touch(source_file)

        real_stat = os.stat
        target_path = os.path.abspath(source_file)
        # os.path.isfile(src) also calls os.stat() internally and swallows
        # OSError itself (returning False) -- it must be allowed to succeed
        # so the loop reaches the explicit stat() call under test. Only the
        # second stat() on this path (the explicit one in the try/except)
        # should raise.
        call_count = {'n': 0}

        def fake_stat(path, *args, **kwargs):
            if os.path.abspath(path) == target_path:
                call_count['n'] += 1
                if call_count['n'] > 1:
                    raise OSError('permission denied')
            return real_stat(path, *args, **kwargs)

        with mock.patch('setup._link_helpers.os.stat', side_effect=fake_stat):
            with self.assertRaises(PruneStatError):
                _prune_flat_directory(source_dir, target_dir, 'orchestrator-')

    def test_recursive_directory_has_user_file_walk_stat_error_raises(self):
        """os.stat() failing on a file inside a non-managed orphan subtree,
        during the has_user_file walk of _prune_recursive_directory, must
        raise PruneStatError (not the outer source_inodes build, which still
        swallows OSError).
        """
        source_dir = os.path.join(self.tmp, 'source', 'skills')
        target_dir = os.path.join(self.tmp, 'target', 'skills')
        os.makedirs(source_dir)
        os.makedirs(target_dir)
        # Managed skill present in source so the outer source_inodes build
        # has a real file to stat successfully.
        _touch(os.path.join(source_dir, 'orchestrator', 'SKILL.md'))
        # Non-managed orphan subtree (no source counterpart) containing a
        # file whose stat will fail inside the has_user_file walk.
        bad_file = os.path.join(target_dir, 'user-skill', 'notes.md')
        _touch(bad_file, 'content')

        real_stat = os.stat

        def fake_stat(path, *args, **kwargs):
            if os.path.abspath(path) == os.path.abspath(bad_file):
                raise OSError('transient error')
            return real_stat(path, *args, **kwargs)

        with mock.patch('setup._link_helpers.os.stat', side_effect=fake_stat):
            with self.assertRaises(PruneStatError):
                _prune_recursive_directory(
                    source_dir, target_dir, ('orchestrator',))

    def test_managed_skill_orphan_files_source_stat_error_raises(self):
        """os.stat() failing on a source file during the per-skill
        source_inodes build in _prune_managed_skill_orphan_files must raise
        PruneStatError (not the second try/except over target files, which
        still swallows OSError).
        """
        source_skills = os.path.join(self.tmp, 'source', 'skills')
        target_skills = os.path.join(self.tmp, 'target', 'skills')
        os.makedirs(source_skills)
        os.makedirs(target_skills)
        source_file = os.path.join(source_skills, 'orchestrator', 'live.md')
        _touch(source_file)
        _touch(os.path.join(target_skills, 'orchestrator', 'live.md'))

        real_stat = os.stat

        def fake_stat(path, *args, **kwargs):
            if os.path.abspath(path) == os.path.abspath(source_file):
                raise OSError('permission denied')
            return real_stat(path, *args, **kwargs)

        with mock.patch('setup._link_helpers.os.stat', side_effect=fake_stat):
            with self.assertRaises(PruneStatError):
                _prune_managed_skill_orphan_files(
                    source_skills, target_skills, ('orchestrator',))


if __name__ == '__main__':
    unittest.main()
