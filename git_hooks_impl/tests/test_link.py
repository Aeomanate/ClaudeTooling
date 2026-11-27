#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for setup.link and git_hooks_impl.entry_points.link_check.

os.symlink is always mocked — symlinks are never created in tests.
"""

import os
import unittest
from unittest.mock import MagicMock, patch

from git_hooks_impl.entry_points.link_check import main as link_check_main
from setup._link_helpers import _is_linked, _link_unconditional
from setup.link import (
    LINK_MAPPINGS,
    _set_hooks_path,
    check,
    install,
)

# ---------------------------------------------------------------------------
#  Module-level silencers
# ---------------------------------------------------------------------------

_log_patchers = []

def setUpModule():
    for t in ('setup.link.run',):
        p = patch(t)
        p.start()
        _log_patchers.append(p)

def tearDownModule():
    for p in _log_patchers:
        p.stop()
    _log_patchers.clear()


# ===========================================================================
#  LINK_MAPPINGS
# ===========================================================================

class TestLinkMappings(unittest.TestCase):

    def test_link_mappings_has_8_entries(self):
        """8 hook stubs (6 native + 2 pre_commit-framework forwarders) are registered in LINK_MAPPINGS."""
        self.assertEqual(len(LINK_MAPPINGS), 8)

    def test_link_mappings_includes_pre_commit_framework_forwarders(self):
        """pre-commit and commit-msg forwarding stubs are present in LINK_MAPPINGS."""
        self.assertIn(('git-hooks/pre-commit', '.git-hooks/pre-commit'), LINK_MAPPINGS)
        self.assertIn(('git-hooks/commit-msg', '.git-hooks/commit-msg'), LINK_MAPPINGS)

    def test_link_mappings_all_are_tuples(self):
        """Every LINK_MAPPINGS entry is a (src, target) 2-tuple of strings."""
        for entry in LINK_MAPPINGS:
            self.assertIsInstance(entry, tuple)
            self.assertEqual(len(entry), 2)
            self.assertIsInstance(entry[0], str)
            self.assertIsInstance(entry[1], str)


# ===========================================================================
#  _set_hooks_path
# ===========================================================================

class TestSetHooksPath(unittest.TestCase):
    """_set_hooks_path: normalizes core.hooksPath, backs up prior value if set."""

    def test_noop_when_already_correct_with_trailing_slash(self):
        """core.hooksPath == '.git-hooks/' -> trailing slash normalizes to match, no writes."""
        with patch('setup.link.run', return_value=(0, '.git-hooks/', '')) as mock_run, \
             patch('builtins.print'):
            _set_hooks_path('/proj')
        self.assertEqual(mock_run.call_count, 1)

    def test_noop_when_already_correct_without_trailing_slash(self):
        """core.hooksPath == '.git-hooks' -> already correct, no writes."""
        with patch('setup.link.run', return_value=(0, '.git-hooks', '')) as mock_run, \
             patch('builtins.print'):
            _set_hooks_path('/proj')
        self.assertEqual(mock_run.call_count, 1)

    def test_backs_up_and_overwrites_when_different_path_set(self):
        """core.hooksPath set to a different path -> backed up then overwritten to .git-hooks."""
        with patch('setup.link.run', side_effect=[
                (0, 'some/other/path', ''), (0, '', ''), (0, '', '')]) as mock_run, \
             patch('builtins.print'):
            _set_hooks_path('/proj')
        self.assertEqual(mock_run.call_count, 3)
        backup_call = mock_run.call_args_list[1].args[0]
        set_call = mock_run.call_args_list[2].args[0]
        self.assertEqual(
            backup_call,
            ['git', 'config', '--local', 'ai-tooling.previousHooksPath', 'some/other/path'])
        self.assertEqual(
            set_call,
            ['git', 'config', '--local', 'core.hooksPath', '.git-hooks'])

    def test_sets_without_backup_when_unset(self):
        """core.hooksPath unset -> sets .git-hooks directly, no backup call."""
        with patch('setup.link.run', side_effect=[(0, '', ''), (0, '', '')]) as mock_run, \
             patch('builtins.print'):
            _set_hooks_path('/proj')
        self.assertEqual(mock_run.call_count, 2)
        set_call = mock_run.call_args_list[1].args[0]
        self.assertEqual(
            set_call,
            ['git', 'config', '--local', 'core.hooksPath', '.git-hooks'])
        all_args = [c.args[0] for c in mock_run.call_args_list]
        self.assertFalse(any('ai-tooling.previousHooksPath' in args for args in all_args))


# ===========================================================================
#  _is_linked
# ===========================================================================

class TestIsLinked(unittest.TestCase):

    def test_returns_false_when_realpaths_differ(self):
        """Target is a symlink but its realpath differs from source realpath -> False."""
        with patch('setup._link_helpers.os.path.islink', return_value=True), \
             patch('setup._link_helpers.os.path.realpath', side_effect=lambda p: p):
            result = _is_linked('/src/file', '/dst/file')
        self.assertFalse(result)

    def test_returns_true_when_symlink_resolves_correctly(self):
        """Target symlink resolves to same realpath as source -> True."""
        with patch('setup._link_helpers.os.path.islink', return_value=True), \
             patch('setup._link_helpers.os.path.realpath', return_value='/real/source'):
            result = _is_linked('/src/file', '/dst/symlink')
        self.assertTrue(result)

    def test_returns_false_when_not_a_symlink(self):
        """Target exists but is not a symlink (e.g., hard-link or regular file) -> False."""
        with patch('setup._link_helpers.os.path.islink', return_value=False):
            result = _is_linked('/src/file', '/dst/file')
        self.assertFalse(result)

    def test_returns_false_on_oserror(self):
        """OSError (missing file) -> False, no exception raised."""
        with patch('setup._link_helpers.os.path.islink', side_effect=OSError):
            result = _is_linked('/no/src', '/no/dst')
        self.assertFalse(result)


# ===========================================================================
#  _link_unconditional
# ===========================================================================

class TestLinkUnconditional(unittest.TestCase):

    def test_links_when_target_absent(self):
        """Target does not exist -> os.symlink called, returns True."""
        with patch('setup._link_helpers._is_linked', return_value=False), \
             patch('setup._link_helpers.os.path.exists', return_value=False), \
             patch('setup._link_helpers.os.path.islink', return_value=False), \
             patch('setup._link_helpers.os.symlink') as mock_symlink:
            result = _link_unconditional('/src/file', '/dst/file')
        self.assertTrue(result)
        mock_symlink.assert_called_once_with('/src/file', '/dst/file')

    def test_skips_when_already_linked(self):
        """Target is a symlink to source -> returns False, no os.symlink."""
        with patch('setup._link_helpers._is_linked', return_value=True), \
             patch('setup._link_helpers.os.symlink') as mock_symlink:
            result = _link_unconditional('/src/file', '/dst/file')
        self.assertFalse(result)
        mock_symlink.assert_not_called()

    def test_replaces_when_diverged(self):
        """Target exists but not linked to source -> os.remove + os.symlink, returns True."""
        with patch('setup._link_helpers._is_linked', return_value=False), \
             patch('setup._link_helpers.os.path.exists', return_value=True), \
             patch('setup._link_helpers.os.path.islink', return_value=False), \
             patch('setup._link_helpers.os.remove') as mock_remove, \
             patch('setup._link_helpers.os.symlink') as mock_symlink:
            result = _link_unconditional('/src/file', '/dst/file')
        self.assertTrue(result)
        mock_remove.assert_called_once_with('/dst/file')
        mock_symlink.assert_called_once_with('/src/file', '/dst/file')


# ===========================================================================
#  install()
# ===========================================================================

class TestInstall(unittest.TestCase):
    """install(): symlink stubs, hooksPath — fully mocked."""

    def _common_patches(self, project, ai_src):
        """Return helpers for a clean happy-path install().

        isfile: True for source files (prefix-matched under ai_src/git-hooks/),
                False for target files (route through os.symlink new-file branch).
        exists: False for all targets (new-file branch).
        stat: same device number for all paths (no cross-volume rejection).
        """
        stat_obj = MagicMock()
        stat_obj.st_dev = 5

        def isfile_side_effect(path):
            norm = path.replace('\\', '/')
            return norm.startswith(ai_src + '/git-hooks/')

        return (isfile_side_effect, stat_obj)

    def test_install_calls_symlink_for_each_mapping(self):
        """install() calls os.symlink once per LINK_MAPPINGS entry (new-file path)."""
        project = '/proj'
        ai_src = '/ai'
        isfile_side_effect, stat_obj = self._common_patches(project, ai_src)
        with patch('setup.link._AI_TOOLING_SRC', ai_src), \
             patch('setup.link.run', return_value=(0, project + '\n', '')), \
             patch('setup.link.os.path.realpath', side_effect=lambda p: p), \
             patch.dict(os.environ, {'AI_TOOLING_ENABLED': 'true'}), \
             patch('setup.link.os.path.isfile', side_effect=isfile_side_effect), \
             patch('setup.link.os.path.exists', return_value=False), \
             patch('setup.link.os.makedirs'), \
             patch('setup.link._is_linked', return_value=False), \
             patch('setup.link._set_hooks_path'), \
             patch('setup.link.os.stat', return_value=stat_obj), \
             patch('setup.link.os.symlink') as mock_symlink, \
             patch('builtins.print'):
            result = install(project)
        self.assertEqual(result, 0)
        self.assertEqual(mock_symlink.call_count, len(LINK_MAPPINGS))

    def test_install_sets_git_hooks_path(self):
        """install() calls _set_hooks_path after linking."""
        project = '/proj'
        ai_src = '/ai'
        isfile_side_effect, stat_obj = self._common_patches(project, ai_src)
        with patch('setup.link._AI_TOOLING_SRC', ai_src), \
             patch('setup.link.run', return_value=(0, project + '\n', '')), \
             patch('setup.link.os.path.realpath', side_effect=lambda p: p), \
             patch.dict(os.environ, {'AI_TOOLING_ENABLED': 'true'}), \
             patch('setup.link.os.path.isfile', side_effect=isfile_side_effect), \
             patch('setup.link.os.path.exists', return_value=False), \
             patch('setup.link.os.makedirs'), \
             patch('setup.link._is_linked', return_value=False), \
             patch('setup.link._set_hooks_path') as mock_set, \
             patch('setup.link.os.stat', return_value=stat_obj), \
             patch('setup.link.os.symlink'), \
             patch('builtins.print'):
            install(project)
        mock_set.assert_called_once()

    def test_install_aborts_when_not_git_repo(self):
        """install() returns 1 when 'git rev-parse --show-toplevel' fails — no link work performed."""
        with patch('setup.link.run', return_value=(1, '', 'fatal: not a git repository\n')), \
             patch.dict(os.environ, {'AI_TOOLING_ENABLED': 'true'}), \
             patch('setup.link.os.symlink') as mock_symlink, \
             patch('setup.link._set_hooks_path') as mock_set, \
             patch('builtins.print'):
            result = install('/proj')
        self.assertEqual(result, 1)
        mock_symlink.assert_not_called()
        mock_set.assert_not_called()

    def test_install_self_skips_when_project_is_ai_tooling_src(self):
        """install() returns 1 when project_root resolves to _AI_TOOLING_SRC itself — no link work performed."""
        with patch('setup.link._AI_TOOLING_SRC', '/ai'), \
             patch('setup.link.run', return_value=(0, '/ai\n', '')), \
             patch('setup.link.os.path.realpath', side_effect=lambda p: p), \
             patch.dict(os.environ, {'AI_TOOLING_ENABLED': 'true'}), \
             patch('setup.link.os.symlink') as mock_symlink, \
             patch('setup.link._set_hooks_path') as mock_set, \
             patch('builtins.print'):
            result = install('/ai')
        self.assertEqual(result, 1)
        mock_symlink.assert_not_called()
        mock_set.assert_not_called()

    def test_install_does_not_create_ai_artifacts_dir(self):
        """install() never creates a .ai/artifacts directory anywhere."""
        project = '/proj'
        ai_src = '/ai'

        # Sources live under '/ai/git-hooks/'; targets under '/proj/.git-hooks/'.
        # Prefix-check avoids false positives from substring overlap.
        def isfile_side_effect(path):
            norm = path.replace('\\', '/')
            return norm.startswith('/ai/git-hooks/')

        stat_obj = MagicMock()
        stat_obj.st_dev = 5

        with patch('setup.link._AI_TOOLING_SRC', ai_src), \
             patch('setup.link.run', return_value=(0, project + '\n', '')), \
             patch.dict(os.environ, {'AI_TOOLING_ENABLED': 'true'}), \
             patch('setup.link.os.path.realpath', side_effect=lambda p: p), \
             patch('setup.link.os.path.isfile', side_effect=isfile_side_effect), \
             patch('setup.link.os.path.exists', return_value=False), \
             patch('setup.link.os.makedirs') as mock_makedirs, \
             patch('setup.link._is_linked', return_value=False), \
             patch('setup.link.prompt_yn', return_value=True), \
             patch('setup.link._set_hooks_path'), \
             patch('setup.link.os.stat', return_value=stat_obj), \
             patch('setup.link.os.symlink'), \
             patch('builtins.print'):
            result = install(project)

        self.assertEqual(result, 0)
        for c in mock_makedirs.call_args_list:
            path_arg = str(c.args[0]) if c.args else ''
            self.assertNotIn('.ai/artifacts', path_arg.replace('\\', '/'))

    def test_install_does_not_touch_dot_claude(self):
        """install() never creates or links anything under .claude/ in the consumer project."""
        project = '/proj'
        ai_src = '/ai'

        # Sources live under '/ai/git-hooks/'; targets under '/proj/.git-hooks/'.
        # Prefix-check avoids false positives from substring overlap.
        def isfile_side_effect(path):
            norm = path.replace('\\', '/')
            return norm.startswith('/ai/git-hooks/')

        stat_obj = MagicMock()
        stat_obj.st_dev = 5

        with patch('setup.link._AI_TOOLING_SRC', ai_src), \
             patch('setup.link.run', return_value=(0, project + '\n', '')), \
             patch.dict(os.environ, {'AI_TOOLING_ENABLED': 'true'}), \
             patch('setup.link.os.path.realpath', side_effect=lambda p: p), \
             patch('setup.link.os.path.isfile', side_effect=isfile_side_effect), \
             patch('setup.link.os.path.exists', return_value=False), \
             patch('setup.link.os.makedirs') as mock_makedirs, \
             patch('setup.link._is_linked', return_value=False), \
             patch('setup.link.prompt_yn', return_value=True), \
             patch('setup.link._set_hooks_path'), \
             patch('setup.link.os.stat', return_value=stat_obj), \
             patch('setup.link.os.symlink') as mock_symlink, \
             patch('builtins.print'):
            result = install(project)

        self.assertEqual(result, 0)
        for c in mock_makedirs.call_args_list:
            path_arg = str(c.args[0]) if c.args else ''
            self.assertNotIn('.claude', path_arg.replace('\\', '/'))
        for c in mock_symlink.call_args_list:
            target_arg = str(c.args[1]) if len(c.args) > 1 else ''
            self.assertNotIn('.claude', target_arg.replace('\\', '/'))

    def test_install_short_circuits_when_ai_tooling_disabled(self):
        """install() returns 0 silently and does no work when AI_TOOLING_ENABLED is not 'true'."""
        with patch.dict(os.environ, {'AI_TOOLING_ENABLED': 'false'}), \
             patch('setup.link.run') as mock_run, \
             patch('setup.link.os.symlink') as mock_symlink, \
             patch('setup.link._set_hooks_path') as mock_set, \
             patch('builtins.print') as mock_print:
            result = install('/proj')
        self.assertEqual(result, 0)
        mock_run.assert_not_called()
        mock_symlink.assert_not_called()
        mock_set.assert_not_called()
        printed = ' '.join(str(a) for call in mock_print.call_args_list for a in call.args)
        self.assertIn('AI_TOOLING_ENABLED', printed)


# ===========================================================================
#  check()
# ===========================================================================

class TestCheck(unittest.TestCase):

    def test_check_returns_0_when_all_linked(self):
        """All hook files present and symlinked to source -> returns 0."""
        with patch('setup.link._AI_TOOLING_SRC', '/ai'), \
             patch('setup.link.os.path.isfile', return_value=True), \
             patch('setup.link._is_linked', return_value=True), \
             patch('setup.link.run', return_value=(0, '.git-hooks', '')):
            result = check('/proj')
        self.assertEqual(result, 0)

    def test_check_returns_0_even_when_diverged(self):
        """Diverged hooks -> prints warning but still returns 0 (never blocks git)."""
        with patch('setup.link._AI_TOOLING_SRC', '/ai'), \
             patch('setup.link.os.path.isfile', return_value=True), \
             patch('setup.link._is_linked', return_value=False), \
             patch('setup.link.run', return_value=(0, '.git-hooks', '')), \
             patch('builtins.print') as mock_print:
            result = check('/proj')
        self.assertEqual(result, 0)
        printed = ' '.join(str(c) for c in mock_print.call_args_list)
        self.assertIn('DIVERGED', printed)

    def test_check_reports_missing(self):
        """Missing hook files -> MISSING in output, still returns 0."""
        with patch('setup.link._AI_TOOLING_SRC', '/ai'), \
             patch('setup.link.os.path.isfile', return_value=False), \
             patch('setup.link.run', return_value=(0, '.git-hooks', '')), \
             patch('builtins.print') as mock_print:
            result = check('/proj')
        self.assertEqual(result, 0)
        printed = ' '.join(str(c) for c in mock_print.call_args_list)
        self.assertIn('MISSING', printed)

    def test_check_reports_hooks_path_wrong_when_unset(self):
        """core.hooksPath unset -> HOOKS_PATH_WRONG flagged, still returns 0."""
        with patch('setup.link._AI_TOOLING_SRC', '/ai'), \
             patch('setup.link.os.path.isfile', return_value=True), \
             patch('setup.link._is_linked', return_value=True), \
             patch('setup.link.run', return_value=(0, '', '')), \
             patch('builtins.print') as mock_print:
            result = check('/proj')
        self.assertEqual(result, 0)
        printed = ' '.join(str(c) for c in mock_print.call_args_list)
        self.assertIn('HOOKS_PATH_WRONG', printed)

    def test_check_no_hooks_path_wrong_when_correct(self):
        """core.hooksPath == .git-hooks -> no HOOKS_PATH_WRONG warning."""
        with patch('setup.link._AI_TOOLING_SRC', '/ai'), \
             patch('setup.link.os.path.isfile', return_value=True), \
             patch('setup.link._is_linked', return_value=True), \
             patch('setup.link.run', return_value=(0, '.git-hooks', '')), \
             patch('builtins.print') as mock_print:
            result = check('/proj')
        self.assertEqual(result, 0)
        printed = ' '.join(str(c) for c in mock_print.call_args_list)
        self.assertNotIn('HOOKS_PATH_WRONG', printed)


# ===========================================================================
#  link_check entry-point
# ===========================================================================

class TestLinkCheck(unittest.TestCase):
    """git_hooks_impl.entry_points.link_check.main() delegates to check()."""

    def test_link_check_cmd_delegates_to_check(self):
        """main() calls cmd_link_check exactly once."""
        with patch('git_hooks_impl.entry_points.link_check.cmd_link_check') as mock_check:
            result = link_check_main()
        mock_check.assert_called_once()
        self.assertEqual(result, 0)

    def test_link_check_passes_argv_path(self):
        """sys.argv[1] provided -> passed as project_root to cmd_link_check."""
        with patch('git_hooks_impl.entry_points.link_check.cmd_link_check') as mock_check, \
             patch('sys.argv', ['link_check.py', '/some/project']):
            link_check_main()
        mock_check.assert_called_once_with('/some/project')

    def test_link_check_defaults_to_cwd(self):
        """No sys.argv[1] -> os.getcwd() passed as project_root."""
        with patch('git_hooks_impl.entry_points.link_check.cmd_link_check') as mock_check, \
             patch('sys.argv', ['link_check.py']):
            link_check_main()
        mock_check.assert_called_once_with(os.getcwd())


if __name__ == '__main__':
    unittest.main()
