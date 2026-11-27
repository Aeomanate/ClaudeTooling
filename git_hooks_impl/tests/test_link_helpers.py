#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for setup/_link_helpers.py, setup/link.py (check()/install()),
and the git_hooks_impl/entry_points/link_check.py entry point.

All tests are fast (<1s each): no network, no real filesystem writes outside tempfile.
"""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from git_hooks_impl.entry_points.link_check import main as link_check_main
from setup._link_helpers import (
    _is_linked,
    _link_directory_recursive,
    _link_flat_directory,
    _link_unconditional,
    _prune_flat_directory,
)
from setup.link import (
    LINK_MAPPINGS,
    check,
    install,
)

# ---------------------------------------------------------------------------
#  Module-level log silencing
# ---------------------------------------------------------------------------

_log_patchers = []

def setUpModule():
    targets = [
        'setup.link.run',
        'setup.link.prompt_yn',
    ]
    for t in targets:
        p = patch(t)
        p.start()
        _log_patchers.append(p)

def tearDownModule():
    for p in _log_patchers:
        p.stop()
    _log_patchers.clear()


# ===========================================================================
#  setup/_link_helpers.py
# ===========================================================================

class TestIsLinked(unittest.TestCase):
    """_is_linked: symlink path-resolution check."""

    def test_symlinked_file_is_linked(self):
        """Target is a symlink pointing to source -> True."""
        with tempfile.TemporaryDirectory() as tmp:
            a = os.path.join(tmp, 'a')
            b = os.path.join(tmp, 'b')
            with open(a, 'w') as f:
                f.write('x')
            os.symlink(a, b)
            self.assertTrue(_is_linked(a, b))

    def test_hard_linked_file_is_not_linked(self):
        """Hard-linked target (not a symlink) -> False (auto-migration case)."""
        with tempfile.TemporaryDirectory() as tmp:
            a = os.path.join(tmp, 'a')
            b = os.path.join(tmp, 'b')
            with open(a, 'w') as f:
                f.write('x')
            os.link(a, b)
            self.assertFalse(_is_linked(a, b))

    def test_different_files_are_not_linked(self):
        """Two independent files -> False."""
        with tempfile.TemporaryDirectory() as tmp:
            a = os.path.join(tmp, 'a')
            b = os.path.join(tmp, 'b')
            for p in (a, b):
                with open(p, 'w') as f:
                    f.write('x')
            self.assertFalse(_is_linked(a, b))

    def test_missing_file_returns_false(self):
        """OSError (missing file) -> False, never raises."""
        self.assertFalse(_is_linked('/no/such/a', '/no/such/b'))


class TestLinkUnconditional(unittest.TestCase):
    """_link_unconditional: replace-if-diverged symlink."""

    def test_links_new_file(self):
        """Target absent -> symlinked, returns True."""
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, 'src')
            dst = os.path.join(tmp, 'dst')
            with open(src, 'w') as f:
                f.write('content')
            result = _link_unconditional(src, dst)
            self.assertTrue(result)
            self.assertTrue(_is_linked(src, dst))

    def test_noop_when_already_linked(self):
        """Target already symlinked to source -> returns False, no change."""
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, 'src')
            dst = os.path.join(tmp, 'dst')
            with open(src, 'w') as f:
                f.write('content')
            os.symlink(src, dst)
            result = _link_unconditional(src, dst)
            self.assertFalse(result)

    def test_replaces_diverged_file(self):
        """Target exists but not a symlink to source -> removed + symlinked, returns True."""
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, 'src')
            dst = os.path.join(tmp, 'dst')
            with open(src, 'w') as f:
                f.write('source')
            with open(dst, 'w') as f:
                f.write('other')
            result = _link_unconditional(src, dst)
            self.assertTrue(result)
            self.assertTrue(_is_linked(src, dst))

    def test_replaces_hard_link(self):
        """Target is a hard-link (not a symlink) -> replaced with symlink, returns True."""
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, 'src')
            dst = os.path.join(tmp, 'dst')
            with open(src, 'w') as f:
                f.write('content')
            os.link(src, dst)
            result = _link_unconditional(src, dst)
            self.assertTrue(result)
            self.assertTrue(_is_linked(src, dst))


class TestLinkFlatDirectory(unittest.TestCase):
    """_link_flat_directory: non-recursive flat link."""

    def test_links_all_files_in_source(self):
        """All files in source_dir are hard-linked into target_dir."""
        with tempfile.TemporaryDirectory() as tmp:
            src_dir = os.path.join(tmp, 'src')
            dst_dir = os.path.join(tmp, 'dst')
            os.makedirs(src_dir)
            for name in ('a.sh', 'b.sh'):
                with open(os.path.join(src_dir, name), 'w') as f:
                    f.write(name)
            linked, up_to_date = _link_flat_directory(src_dir, dst_dir)
            self.assertEqual(linked, 2)
            self.assertEqual(up_to_date, 0)
            for name in ('a.sh', 'b.sh'):
                self.assertTrue(_is_linked(
                    os.path.join(src_dir, name),
                    os.path.join(dst_dir, name),
                ))

    def test_up_to_date_on_second_call(self):
        """Running twice: all files already linked -> linked=0, up_to_date=N."""
        with tempfile.TemporaryDirectory() as tmp:
            src_dir = os.path.join(tmp, 'src')
            dst_dir = os.path.join(tmp, 'dst')
            os.makedirs(src_dir)
            with open(os.path.join(src_dir, 'file'), 'w') as f:
                f.write('x')
            _link_flat_directory(src_dir, dst_dir)
            linked, up_to_date = _link_flat_directory(src_dir, dst_dir)
            self.assertEqual(linked, 0)
            self.assertEqual(up_to_date, 1)

    def test_skips_subdirectories(self):
        """Subdirectories inside source_dir are not linked."""
        with tempfile.TemporaryDirectory() as tmp:
            src_dir = os.path.join(tmp, 'src')
            dst_dir = os.path.join(tmp, 'dst')
            os.makedirs(os.path.join(src_dir, 'subdir'))
            with open(os.path.join(src_dir, 'file.sh'), 'w') as f:
                f.write('x')
            linked, _ = _link_flat_directory(src_dir, dst_dir)
            self.assertEqual(linked, 1)


class TestLinkDirectoryRecursive(unittest.TestCase):
    """_link_directory_recursive: recursive walk + link."""

    def test_links_nested_files(self):
        """Files in subdirectories are linked into matching target structure."""
        with tempfile.TemporaryDirectory() as tmp:
            src_dir = os.path.join(tmp, 'src')
            os.makedirs(os.path.join(src_dir, 'sub'))
            with open(os.path.join(src_dir, 'top.md'), 'w') as f:
                f.write('top')
            with open(os.path.join(src_dir, 'sub', 'nested.md'), 'w') as f:
                f.write('nested')
            dst_dir = os.path.join(tmp, 'dst')
            linked, _ = _link_directory_recursive(src_dir, dst_dir)
            self.assertEqual(linked, 2)
            self.assertTrue(_is_linked(
                os.path.join(src_dir, 'sub', 'nested.md'),
                os.path.join(dst_dir, 'sub', 'nested.md'),
            ))


# ===========================================================================
#  setup/_link_helpers.py — _prune_flat_directory
# ===========================================================================

class TestPruneFlatDirectory(unittest.TestCase):
    """_prune_flat_directory: prefix-matched, inode-unverified orphan detection."""

    def test_no_orphans_when_all_linked(self):
        """Files hard-linked from source -> inode present in source -> not orphans."""
        with tempfile.TemporaryDirectory() as tmp:
            src_dir = os.path.join(tmp, 'src')
            dst_dir = os.path.join(tmp, 'dst')
            os.makedirs(src_dir)
            os.makedirs(dst_dir)
            src_file = os.path.join(src_dir, 'orchestrator-agent-foo.md')
            with open(src_file, 'w') as f:
                f.write('x')
            os.link(src_file, os.path.join(dst_dir, 'orchestrator-agent-foo.md'))
            orphans = _prune_flat_directory(src_dir, dst_dir, 'orchestrator-')
            self.assertEqual(orphans, [])

    def test_detects_orphan_after_source_removed(self):
        """File linked from source, then source removed -> orphan detected."""
        with tempfile.TemporaryDirectory() as tmp:
            src_dir = os.path.join(tmp, 'src')
            dst_dir = os.path.join(tmp, 'dst')
            os.makedirs(src_dir)
            os.makedirs(dst_dir)
            src_file = os.path.join(src_dir, 'orchestrator-agent-old.md')
            with open(src_file, 'w') as f:
                f.write('x')
            os.link(src_file, os.path.join(dst_dir, 'orchestrator-agent-old.md'))
            # Simulate source removal (rename out of src_dir)
            os.remove(src_file)
            orphans = _prune_flat_directory(src_dir, dst_dir, 'orchestrator-')
            self.assertEqual(len(orphans), 1)
            self.assertIn('orchestrator-agent-old.md', orphans[0])

    def test_ignores_non_prefix_files(self):
        """Files in target_dir without the prefix are never flagged."""
        with tempfile.TemporaryDirectory() as tmp:
            src_dir = os.path.join(tmp, 'src')
            dst_dir = os.path.join(tmp, 'dst')
            os.makedirs(src_dir)
            os.makedirs(dst_dir)
            # User-created file without prefix — no source counterpart
            with open(os.path.join(dst_dir, 'my-custom-agent.md'), 'w') as f:
                f.write('user file')
            orphans = _prune_flat_directory(src_dir, dst_dir, 'orchestrator-')
            self.assertEqual(orphans, [])

    def test_ignores_subdirectories_in_target(self):
        """Subdirectories in target_dir are not flagged even if prefix-matched."""
        with tempfile.TemporaryDirectory() as tmp:
            src_dir = os.path.join(tmp, 'src')
            dst_dir = os.path.join(tmp, 'dst')
            os.makedirs(src_dir)
            os.makedirs(os.path.join(dst_dir, 'orchestrator-subdir'))
            orphans = _prune_flat_directory(src_dir, dst_dir, 'orchestrator-')
            self.assertEqual(orphans, [])

    def test_inode_match_across_different_filenames(self):
        """Target file renamed in source -> same inode still present -> not an orphan."""
        with tempfile.TemporaryDirectory() as tmp:
            src_dir = os.path.join(tmp, 'src')
            dst_dir = os.path.join(tmp, 'dst')
            os.makedirs(src_dir)
            os.makedirs(dst_dir)
            # Create a source file and link it to target under a different name
            src_file = os.path.join(src_dir, 'orchestrator-agent-new.md')
            with open(src_file, 'w') as f:
                f.write('x')
            # Target has old name but same inode (hard-linked to same content)
            os.link(src_file, os.path.join(dst_dir, 'orchestrator-agent-old.md'))
            # Source still has the inode -> target is NOT orphaned
            orphans = _prune_flat_directory(src_dir, dst_dir, 'orchestrator-')
            self.assertEqual(orphans, [])

    def test_empty_source_and_target_returns_empty(self):
        """Both dirs empty -> no orphans."""
        with tempfile.TemporaryDirectory() as tmp:
            src_dir = os.path.join(tmp, 'src')
            dst_dir = os.path.join(tmp, 'dst')
            os.makedirs(src_dir)
            os.makedirs(dst_dir)
            self.assertEqual(_prune_flat_directory(src_dir, dst_dir, 'orchestrator-'), [])

    def test_missing_source_dir_returns_empty(self):
        """Non-existent source_dir -> no orphans (safe fallback)."""
        with tempfile.TemporaryDirectory() as tmp:
            dst_dir = os.path.join(tmp, 'dst')
            os.makedirs(dst_dir)
            with open(os.path.join(dst_dir, 'orchestrator-agent-foo.md'), 'w') as f:
                f.write('x')
            orphans = _prune_flat_directory('/no/such/src', dst_dir, 'orchestrator-')
            self.assertEqual(orphans, [])


# ===========================================================================
#  setup/link.py — check() mode B
# ===========================================================================

class TestLinkCheck(unittest.TestCase):
    """check(): inode compare, warn-only, always returns 0."""

    def test_returns_zero_always(self):
        """check() never returns non-zero — must not block git."""
        with tempfile.TemporaryDirectory() as tmp, \
             patch('setup.link._AI_TOOLING_SRC', tmp), \
             patch('setup.link._is_linked', return_value=True), \
             patch('setup.link.run', return_value=(0, '.git-hooks', '')):
            result = check(tmp)
        self.assertEqual(result, 0)

    def test_reports_missing_hooks(self):
        """Missing target files are listed in output."""
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, 'project')
            os.makedirs(project)
            with patch('setup.link._AI_TOOLING_SRC', tmp), \
                 patch('setup.link.run', return_value=(0, '.git-hooks', '')), \
                 patch('builtins.print') as mock_print:
                result = check(project)
            self.assertEqual(result, 0)
            printed = ' '.join(str(c) for c in mock_print.call_args_list)
            self.assertIn('MISSING', printed)

    def test_reports_diverged_hooks(self):
        """Hooks that exist but differ in inode are flagged DIVERGED."""
        with tempfile.TemporaryDirectory() as tmp:
            src_rel, tgt_rel = LINK_MAPPINGS[0]
            src_file = os.path.join(tmp, src_rel)
            os.makedirs(os.path.dirname(src_file), exist_ok=True)
            with open(src_file, 'w') as f:
                f.write('stub')

            project = os.path.join(tmp, 'project')
            tgt_file = os.path.join(project, tgt_rel)
            os.makedirs(os.path.dirname(tgt_file), exist_ok=True)
            with open(tgt_file, 'w') as f:
                f.write('other')

            with patch('setup.link._AI_TOOLING_SRC', tmp), \
                 patch('setup.link.run', return_value=(0, '.git-hooks', '')), \
                 patch('builtins.print') as mock_print:
                result = check(project)

            self.assertEqual(result, 0)
            printed = ' '.join(str(c) for c in mock_print.call_args_list)
            self.assertIn('DIVERGED', printed)

    def test_reports_hooks_path_wrong_when_unset(self):
        """core.hooksPath unset -> HOOKS_PATH_WRONG flagged, still returns 0."""
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, 'project')
            os.makedirs(project)
            with patch('setup.link._AI_TOOLING_SRC', tmp), \
                 patch('setup.link.run', return_value=(0, '', '')), \
                 patch('builtins.print') as mock_print:
                result = check(project)
            self.assertEqual(result, 0)
            printed = ' '.join(str(c) for c in mock_print.call_args_list)
            self.assertIn('HOOKS_PATH_WRONG', printed)

    def test_no_hooks_path_wrong_when_correct(self):
        """core.hooksPath == .git-hooks -> no HOOKS_PATH_WRONG warning."""
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, 'project')
            os.makedirs(project)
            with patch('setup.link._AI_TOOLING_SRC', tmp), \
                 patch('setup.link.run', return_value=(0, '.git-hooks', '')), \
                 patch('builtins.print') as mock_print:
                result = check(project)
            self.assertEqual(result, 0)
            printed = ' '.join(str(c) for c in mock_print.call_args_list)
            self.assertNotIn('HOOKS_PATH_WRONG', printed)


# ===========================================================================
#  setup/link.py — install() mode A
# ===========================================================================

class TestLinkInstall(unittest.TestCase):
    """install(): hard-link stubs, update .gitignore, set hooksPath."""

    def _make_source_stubs(self, ai_src):
        for src_rel, _tgt_rel in LINK_MAPPINGS:
            src_file = os.path.join(ai_src, src_rel)
            os.makedirs(os.path.dirname(src_file), exist_ok=True)
            with open(src_file, 'w') as f:
                f.write('stub')

    def test_kill_switch_skips_install(self):
        """AI_TOOLING_ENABLED != 'true' -> returns 0, no work done."""
        with patch.dict(os.environ, {'AI_TOOLING_ENABLED': 'false'}):
            result = install('/some/project')
        self.assertEqual(result, 0)

    def test_refuses_self_link(self):
        """project_root == _AI_TOOLING_SRC -> returns 1."""
        with tempfile.TemporaryDirectory() as tmp:
            real = os.path.realpath(tmp)
            with patch('setup.link._AI_TOOLING_SRC', real), \
                 patch('setup.link.run', return_value=(0, real + '\n', '')), \
                 patch.dict(os.environ, {'AI_TOOLING_ENABLED': 'true'}):
                result = install(real)
        self.assertEqual(result, 1)

    def test_error_when_not_in_git_repo(self):
        """Git rev-parse fails -> returns 1."""
        with tempfile.TemporaryDirectory() as tmp, \
             patch('setup.link.run', return_value=(1, '', 'not a repo')), \
             patch.dict(os.environ, {'AI_TOOLING_ENABLED': 'true'}):
            result = install(tmp)
        self.assertEqual(result, 1)

    def test_cross_volume_returns_error(self):
        """src_dev != tgt_dev -> returns 1, message printed."""
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, 'project')
            os.makedirs(project)
            self._make_source_stubs(tmp)

            _real_stat = os.stat  # capture function object before patch replaces os.stat

            def fake_stat(path):
                real = _real_stat(path)  # calls original stat (not the mock)
                result = MagicMock()
                result.st_mode = real.st_mode   # preserve real mode (isfile/isdir stay correct)
                result.st_ino = real.st_ino
                result.st_dev = 1 if path.startswith(os.path.join(tmp, 'git-hooks')) else 2
                return result

            with patch('setup.link._AI_TOOLING_SRC', tmp), \
                 patch('setup.link.run', return_value=(0, project + '\n', '')), \
                 patch('setup.link.os.stat', side_effect=fake_stat), \
                 patch.dict(os.environ, {'AI_TOOLING_ENABLED': 'true'}):
                result = install(project)
        self.assertEqual(result, 1)

    def test_links_stubs(self):
        """Happy path: all stubs linked, returns 0."""
        with tempfile.TemporaryDirectory() as tmp:
            ai_src = os.path.join(tmp, 'ai_tooling')
            project = os.path.join(tmp, 'project')
            os.makedirs(project)
            self._make_source_stubs(ai_src)

            with patch('setup.link._AI_TOOLING_SRC', ai_src), \
                 patch('setup.link.run', return_value=(0, project + '\n', '')), \
                 patch('setup.link._set_hooks_path'), \
                 patch.dict(os.environ, {'AI_TOOLING_ENABLED': 'true'}):
                result = install(project)

            self.assertEqual(result, 0)


# ===========================================================================
#  git_hooks_impl/entry_points/link_check.py
# ===========================================================================

class TestLinkCheckEntry(unittest.TestCase):
    """link_check.main(): delegates to check(), always returns 0."""

    def test_main_returns_zero(self):
        """main() calls check() and returns 0 regardless."""
        with patch('git_hooks_impl.entry_points.link_check.cmd_link_check', return_value=0) as mock_check:
            result = link_check_main()
        self.assertEqual(result, 0)
        mock_check.assert_called_once()

    def test_main_passes_cwd_when_no_argv(self):
        """No sys.argv[1] -> project_root defaults to os.getcwd()."""
        with patch('git_hooks_impl.entry_points.link_check.cmd_link_check') as mock_check, \
             patch('sys.argv', ['link_check.py']):
            link_check_main()
        mock_check.assert_called_once_with(os.getcwd())

    def test_main_passes_argv_project_root(self):
        """sys.argv[1] provided -> that path passed to check()."""
        with patch('git_hooks_impl.entry_points.link_check.cmd_link_check') as mock_check, \
             patch('sys.argv', ['link_check.py', '/some/project']):
            link_check_main()
        mock_check.assert_called_once_with('/some/project')


if __name__ == '__main__':
    unittest.main()
