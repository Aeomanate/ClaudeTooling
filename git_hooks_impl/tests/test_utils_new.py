#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for runtime path / env utilities in git_hooks_impl.utils."""

import os
import unittest
from unittest.mock import patch

from git_hooks_impl.utils import _to_posix_path, add_env_path, ensure_path

# ---------------------------------------------------------------------------
#  Module-level log silencing
# ---------------------------------------------------------------------------

_log_patchers = []

def setUpModule():
    for t in ('git_hooks_impl.utils.dbg',):
        p = patch(t)
        p.start()
        _log_patchers.append(p)

def tearDownModule():
    for p in _log_patchers:
        p.stop()
    _log_patchers.clear()


# ===========================================================================
#  ensure_path
# ===========================================================================

class TestEnsurePath(unittest.TestCase):

    def setUp(self):
        self._orig_path = os.environ.get('PATH', '')

    def tearDown(self):
        os.environ['PATH'] = self._orig_path

    def test_adds_directory_when_absent_from_path(self):
        """Directory not in PATH -> appended to PATH."""
        os.environ['PATH'] = '/usr/bin'
        ensure_path('/my/new/dir')
        path_entries = os.environ['PATH'].split(os.pathsep)
        self.assertIn('/my/new/dir', path_entries)

    def test_no_duplicate_when_already_present(self):
        """Directory already in PATH -> PATH unchanged."""
        os.environ['PATH'] = '/my/dir' + os.pathsep + '/usr/bin'
        before = os.environ['PATH']
        ensure_path('/my/dir')
        self.assertEqual(os.environ['PATH'], before)

    def test_empty_path_still_adds(self):
        """PATH is empty -> directory added."""
        os.environ['PATH'] = ''
        ensure_path('/only/dir')
        self.assertIn('/only/dir', os.environ['PATH'])


# ===========================================================================
#  add_env_path
# ===========================================================================

class TestAddEnvPath(unittest.TestCase):

    def setUp(self):
        self._orig_path = os.environ.get('PATH', '')

    def tearDown(self):
        os.environ['PATH'] = self._orig_path

    def test_prepends_directory_to_path(self):
        """add_env_path('/x') -> '/x' appears in PATH."""
        os.environ['PATH'] = '/usr/bin'
        add_env_path('/x')
        self.assertIn('/x', os.environ['PATH'])

    def test_no_duplicate_when_already_present(self):
        """add_env_path with directory already in PATH -> no duplication."""
        os.environ['PATH'] = '/existing' + os.pathsep + '/usr/bin'
        before = os.environ['PATH']
        add_env_path('/existing')
        self.assertEqual(os.environ['PATH'], before)

    def test_delegates_to_ensure_path(self):
        """add_env_path is a thin wrapper — same effect as ensure_path."""
        os.environ['PATH'] = '/usr/bin'
        add_env_path('/delegate/test')
        self.assertIn('/delegate/test', os.environ['PATH'])


# ===========================================================================
#  _to_posix_path
# ===========================================================================

class TestToPosixPath(unittest.TestCase):
    """_to_posix_path: convert Windows paths to POSIX/Git Bash format."""

    def test_converts_windows_drive_path(self):
        """C:\\Kragle\\reponame -> /c/Kragle/reponame."""
        """C:\\Kragle\\reponame -> /c/Kragle/reponame."""
        result = _to_posix_path('C:\\Kragle\\reponame')
        result = _to_posix_path('C:\\Kragle\\reponame')
        self.assertEqual(result, '/c/Kragle/reponame')
        self.assertEqual(result, '/c/Kragle/reponame')

    def test_lowercase_drive_letter(self):
        """Drive letter is lowercased in output."""
        result = _to_posix_path('D:\\foo\\bar')
        self.assertTrue(result.startswith('/d/'))

    def test_passthrough_already_posix(self):
        """Already-POSIX path returned unchanged."""
        result = _to_posix_path('/usr/local/bin')
        self.assertEqual(result, '/usr/local/bin')

    def test_converts_backslashes_to_forward_slashes(self):
        """All backslashes replaced with forward slashes."""
        result = _to_posix_path('C:\\a\\b\\c')
        self.assertNotIn('\\', result)

    def test_single_char_path_no_drive(self):
        """Short path without drive letter treated as passthrough."""
        result = _to_posix_path('/x')
        self.assertEqual(result, '/x')


if __name__ == '__main__':
    unittest.main()
