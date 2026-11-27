#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for setup/install_profiles.py, git_hooks_impl/utils.py
(ensure_path/add_env_path), setup/tools.py (Jira download/extract helpers),
and setup/skills.py (Claude tree linking).

All tests are fast (<1s each): no network, no real filesystem writes outside tempfile.
"""

import io
import os
import stat
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from git_hooks_impl.utils import add_env_path, ensure_path
from setup.install_profiles import (
    _BLOCK_BEGIN,
    _BLOCK_END,
    _strip_existing_block,
    append_to_bashrc,
    write_managed_block,
)
from setup.skills import cmd_setup_user_global
from setup.tools import (
    _extract_jira_unix,
    _extract_jira_windows,
    _jira_download_url,
)

# ---------------------------------------------------------------------------
#  Module-level log silencing
# ---------------------------------------------------------------------------

_log_patchers = []

def setUpModule():
    targets = [
        'git_hooks_impl.utils.dbg',
        'setup.tools.dbg',
        'setup.tools.log',
        'setup.tools.ok',
        'setup.tools.warn',
        'setup.tools.err',
        'setup.skills.prompt_yn',
        'setup.skills._print_preflight_warning',
        'setup.skills._print_merge_instruction',
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
#  setup/install_profiles.py
# ===========================================================================

class TestStripExistingBlock(unittest.TestCase):
    """_strip_existing_block: remove managed block from line list."""

    def test_strips_block_from_middle(self):
        """Lines before/after block retained; block lines removed."""
        lines = [
            'before\n',
            _BLOCK_BEGIN + '\n',
            'export FOO=bar\n',
            _BLOCK_END + '\n',
            'after\n',
        ]
        result = _strip_existing_block(lines)
        self.assertEqual(result, ['before\n', 'after\n'])

    def test_passthrough_no_block(self):
        """No managed block -> lines unchanged."""
        lines = ['line1\n', 'line2\n']
        result = _strip_existing_block(lines)
        self.assertEqual(result, lines)

    def test_strips_multiple_blocks(self):
        """Two managed blocks both stripped (idempotent safety)."""
        lines = [
            _BLOCK_BEGIN + '\n', 'inside1\n', _BLOCK_END + '\n',
            'middle\n',
            _BLOCK_BEGIN + '\n', 'inside2\n', _BLOCK_END + '\n',
        ]
        result = _strip_existing_block(lines)
        self.assertEqual(result, ['middle\n'])


class TestAppendToBashrc(unittest.TestCase):
    """append_to_bashrc: idempotent managed block write."""

    def _make_bashrc_path(self, tmp):
        return Path(os.path.join(tmp, '.bashrc'))

    def test_writes_block_to_new_file(self):
        """Non-existent bashrc created with block."""
        with tempfile.TemporaryDirectory() as tmp:
            bashrc = self._make_bashrc_path(tmp)
            with patch('setup.install_profiles._bashrc_path', return_value=bashrc):
                append_to_bashrc(['export X=1'])
            content = bashrc.read_text()
            self.assertIn(_BLOCK_BEGIN, content)
            self.assertIn('export X=1', content)
            self.assertIn(_BLOCK_END, content)

    def test_idempotent_single_block(self):
        """Calling twice produces exactly one managed block."""
        with tempfile.TemporaryDirectory() as tmp:
            bashrc = self._make_bashrc_path(tmp)
            with patch('setup.install_profiles._bashrc_path', return_value=bashrc):
                append_to_bashrc(['export X=1'])
                append_to_bashrc(['export X=2'])
            content = bashrc.read_text()
            self.assertEqual(content.count(_BLOCK_BEGIN), 1)
            self.assertIn('export X=2', content)
            self.assertNotIn('export X=1', content)

    def test_preserves_existing_content(self):
        """Pre-existing bashrc lines outside block are preserved."""
        with tempfile.TemporaryDirectory() as tmp:
            bashrc = self._make_bashrc_path(tmp)
            bashrc.write_text('# my custom line\n')
            with patch('setup.install_profiles._bashrc_path', return_value=bashrc):
                append_to_bashrc(['export Y=2'])
            content = bashrc.read_text()
            self.assertIn('# my custom line', content)
            self.assertIn('export Y=2', content)


class TestWriteManagedBlock(unittest.TestCase):
    """write_managed_block: writes canonical ai_tooling env block."""

    def test_writes_all_three_tokens(self):
        """JIRA_API_TOKEN, GLAB_TOKEN, ANTHROPIC_AUTH_TOKEN all written."""
        with tempfile.TemporaryDirectory() as tmp:
            bashrc = Path(os.path.join(tmp, '.bashrc'))
            tokens = {
                'JIRA_API_TOKEN': 'jira123',
                'GLAB_TOKEN': 'glab456',
                'ANTHROPIC_AUTH_TOKEN': 'anthropic789',
            }
            with patch('setup.install_profiles._bashrc_path', return_value=bashrc):
                write_managed_block('/my/ai_tooling', tokens)
            content = bashrc.read_text()
            self.assertIn('export AI_TOOLING_SRC="/my/ai_tooling"', content)
            self.assertIn('export JIRA_API_TOKEN="jira123"', content)
            self.assertIn('export GLAB_TOKEN="glab456"', content)
            self.assertIn('export ANTHROPIC_AUTH_TOKEN="anthropic789"', content)

    def test_missing_token_written_as_empty(self):
        """Token absent from dict -> written as empty string, not omitted."""
        with tempfile.TemporaryDirectory() as tmp:
            bashrc = Path(os.path.join(tmp, '.bashrc'))
            with patch('setup.install_profiles._bashrc_path', return_value=bashrc):
                write_managed_block('/src', {})
            content = bashrc.read_text()
            self.assertIn('export JIRA_API_TOKEN=""', content)
            self.assertIn('export GLAB_TOKEN=""', content)
            self.assertIn('export ANTHROPIC_AUTH_TOKEN=""', content)

    def test_writes_ai_tooling_enabled(self):
        """Block always contains AI_TOOLING_ENABLED=true."""
        with tempfile.TemporaryDirectory() as tmp:
            bashrc = Path(os.path.join(tmp, '.bashrc'))
            with patch('setup.install_profiles._bashrc_path', return_value=bashrc):
                write_managed_block('/src', {})
            self.assertIn('AI_TOOLING_ENABLED=true', bashrc.read_text())


# ===========================================================================
#  git_hooks_impl/utils.py — ensure_path / add_env_path
# ===========================================================================

class TestEnsurePath(unittest.TestCase):
    """ensure_path: adds directory to PATH if absent."""

    def setUp(self):
        self._orig_path = os.environ.get('PATH', '')

    def tearDown(self):
        os.environ['PATH'] = self._orig_path

    def test_adds_missing_directory(self):
        """Directory not in PATH -> added."""
        os.environ['PATH'] = '/usr/bin'
        ensure_path('/my/new/dir')
        self.assertIn('/my/new/dir', os.environ['PATH'])

    def test_noop_when_already_present(self):
        """Directory already in PATH -> not duplicated."""
        os.environ['PATH'] = '/my/dir' + os.pathsep + '/usr/bin'
        before = os.environ['PATH']
        ensure_path('/my/dir')
        self.assertEqual(os.environ['PATH'], before)


class TestAddEnvPath(unittest.TestCase):
    """add_env_path: thin wrapper over ensure_path."""

    def setUp(self):
        self._orig_path = os.environ.get('PATH', '')

    def tearDown(self):
        os.environ['PATH'] = self._orig_path

    def test_delegates_to_ensure_path(self):
        """add_env_path('/x') -> '/x' appears in PATH."""
        os.environ['PATH'] = '/usr/bin'
        add_env_path('/x')
        self.assertIn('/x', os.environ['PATH'])


# ===========================================================================
#  setup/tools.py — pure URL + extraction helpers
# ===========================================================================

class TestJiraDownloadUrl(unittest.TestCase):
    """_jira_download_url: URL construction, no network."""

    def test_windows_produces_zip_url(self):
        """windows/x86_64 -> .zip URL."""
        url = _jira_download_url('windows', 'x86_64')
        self.assertIn('.zip', url)
        self.assertTrue(url.startswith('https://'))
        self.assertIn('x86_64', url)

    def test_linux_produces_tar_gz_url(self):
        """linux/x86_64 -> .tar.gz URL."""
        url = _jira_download_url('linux', 'x86_64')
        self.assertIn('.tar.gz', url)

    def test_darwin_arm64_url(self):
        """darwin/arm64 -> arm64 in URL."""
        url = _jira_download_url('darwin', 'arm64')
        self.assertIn('arm64', url)
        self.assertIn('darwin', url)


class TestExtractJiraWindows(unittest.TestCase):
    """_extract_jira_windows: zip extraction to target path."""

    def _make_zip(self, exe_name='jira.exe'):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr(exe_name, b'binary_content')
        buf.seek(0)
        return buf

    def test_extracts_jira_exe(self):
        """jira.exe found in zip -> written to target, returns True."""
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, 'jira.exe')
            archive = self._make_zip('subdir/jira.exe')
            with patch('setup.tools.err'):
                result = _extract_jira_windows(archive, target)
            self.assertTrue(result)
            self.assertTrue(os.path.isfile(target))

    def test_returns_false_when_exe_missing(self):
        """Zip with no jira.exe -> returns False."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr('other.txt', b'x')
        buf.seek(0)
        with patch('setup.tools.err'):
            result = _extract_jira_windows(buf, '/tmp/jira.exe')
        self.assertFalse(result)


class TestExtractJiraUnix(unittest.TestCase):
    """_extract_jira_unix: tar.gz extraction + chmod."""

    def _make_targz(self, member_name='jira_linux_x86_64/jira'):
        buf = io.BytesIO()
        content = b'binary_content'
        with tarfile.open(fileobj=buf, mode='w:gz') as tf:
            info = tarfile.TarInfo(name=member_name)
            info.size = len(content)
            tf.addfile(info, io.BytesIO(content))
        buf.seek(0)
        return buf

    @unittest.skipIf(sys.platform == 'win32', 'os.chmod does not set executable bit on NTFS')
    def test_extracts_jira_binary(self):
        """Jira binary in tar.gz -> written to target, executable, returns True."""
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, 'jira')
            archive = self._make_targz('prefix/jira')
            with patch('setup.tools.err'):
                result = _extract_jira_unix(archive, target)
            self.assertTrue(result)
            self.assertTrue(os.path.isfile(target))
            mode = os.stat(target).st_mode
            self.assertTrue(mode & stat.S_IEXEC)

    def test_returns_false_when_member_missing(self):
        """Tar.gz with no jira member -> returns False."""
        buf = io.BytesIO()
        content = b'x'
        with tarfile.open(fileobj=buf, mode='w:gz') as tf:
            info = tarfile.TarInfo(name='other_binary')
            info.size = len(content)
            tf.addfile(info, io.BytesIO(content))
        buf.seek(0)
        with patch('setup.tools.err'):
            result = _extract_jira_unix(buf, '/tmp/jira')
        self.assertFalse(result)


# ===========================================================================
#  setup/skills.py — _link_claude_tree (via mock of helpers)
# ===========================================================================

class TestLinkClaudeTree(unittest.TestCase):
    """cmd_setup_user_global: aborts when claude_src missing; links when present."""

    def test_returns_one_when_claude_src_missing(self):
        """claude/ source tree not found -> returns 1, no linking attempted."""
        with tempfile.TemporaryDirectory() as tmp:
            result = cmd_setup_user_global(ai_tooling_src=tmp)
        self.assertEqual(result, 1)

    def test_aborts_on_user_decline(self):
        """User declines confirmation prompt -> returns 1, no links."""
        with tempfile.TemporaryDirectory() as tmp:
            claude_src = os.path.join(tmp, 'claude')
            os.makedirs(claude_src)
            with patch('setup.skills.prompt_yn', return_value=False), \
                 patch('setup.skills._link_claude_tree') as mock_link, \
                 patch('builtins.print'):
                result = cmd_setup_user_global(ai_tooling_src=tmp)
        self.assertEqual(result, 1)
        mock_link.assert_not_called()

    def test_links_on_confirmation(self):
        """User confirms -> _link_claude_tree called, returns 0."""
        with tempfile.TemporaryDirectory() as tmp:
            claude_src = os.path.join(tmp, 'claude')
            os.makedirs(claude_src)
            with patch('setup.skills.prompt_yn', return_value=True), \
                 patch('setup.skills._link_claude_tree') as mock_link, \
                 patch('setup.skills._prune_stale_targets', return_value=([], [])), \
                 patch('setup.skills._update_claude_settings_env'), \
                 patch('builtins.print'):
                result = cmd_setup_user_global(ai_tooling_src=tmp)
        self.assertEqual(result, 0)
        mock_link.assert_called_once()


if __name__ == '__main__':
    unittest.main()
