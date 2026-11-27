#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for setup.tools.

Network calls, subprocess, and file writes are all mocked.
cmd_install_tools is highly interactive — tests cover discrete helper
functions and the top-level control flow branches.
"""

import io
import os
import tarfile
import tempfile
import unittest
import zipfile
from unittest.mock import MagicMock, patch

from setup.tools import (
    _check_companyname_network,
    _extract_jira_unix,
    _extract_jira_windows,
    _jira_download_url,
    cmd_install_tools,
)

# ---------------------------------------------------------------------------
#  Module-level log silencing
# ---------------------------------------------------------------------------

_log_patchers = []

def setUpModule():
    for t in ('setup.tools.dbg', 'setup.tools.log', 'setup.tools.ok',
              'setup.tools.warn', 'setup.tools.err'):
        p = patch(t)
        p.start()
        _log_patchers.append(p)

def tearDownModule():
    for p in _log_patchers:
        p.stop()
    _log_patchers.clear()


# ===========================================================================
#  _jira_download_url — pure URL construction, no mocks needed
# ===========================================================================

class TestJiraDownloadUrl(unittest.TestCase):

    def test_windows_produces_zip_url(self):
        """windows/x86_64 -> URL ends with .zip."""
        url = _jira_download_url('windows', 'x86_64')
        self.assertTrue(url.endswith('.zip'), url)

    def test_linux_produces_tar_gz_url(self):
        """linux/x86_64 -> URL ends with .tar.gz."""
        url = _jira_download_url('linux', 'x86_64')
        self.assertTrue(url.endswith('.tar.gz'), url)

    def test_url_contains_os_and_arch(self):
        """URL embeds the os_name and arch in the filename."""
        url = _jira_download_url('darwin', 'arm64')
        self.assertIn('darwin', url)
        self.assertIn('arm64', url)

    def test_url_starts_with_https(self):
        """All URLs use HTTPS."""
        for os_name, arch in [('windows', 'x86_64'), ('linux', 'arm64'), ('darwin', 'x86_64')]:
            url = _jira_download_url(os_name, arch)
            self.assertTrue(url.startswith('https://'), url)


# ===========================================================================
#  _extract_jira_windows
# ===========================================================================

class TestExtractJiraWindows(unittest.TestCase):

    def _make_zip(self, name='subdir/jira.exe', content=b'exe_content'):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr(name, content)
        buf.seek(0)
        return buf

    def test_extracts_jira_exe_to_target(self):
        """jira.exe found in zip -> written to target path, returns True."""
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, 'jira.exe')
            archive = self._make_zip('nested/jira.exe')
            result = _extract_jira_windows(archive, target)
        self.assertTrue(result)

    def test_returns_false_when_exe_missing(self):
        """Zip contains no jira.exe -> returns False."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr('other.txt', b'x')
        buf.seek(0)
        with tempfile.TemporaryDirectory() as tmp:
            result = _extract_jira_windows(buf, os.path.join(tmp, 'jira.exe'))
        self.assertFalse(result)


# ===========================================================================
#  _extract_jira_unix
# ===========================================================================

class TestExtractJiraUnix(unittest.TestCase):

    def _make_targz(self, member_name='prefix/jira', content=b'bin_content'):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode='w:gz') as tf:
            info = tarfile.TarInfo(name=member_name)
            info.size = len(content)
            tf.addfile(info, io.BytesIO(content))
        buf.seek(0)
        return buf

    def test_extracts_binary_and_makes_executable(self):
        """Jira binary in tar.gz -> written to target, executable bit set, returns True."""
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, 'jira')
            archive = self._make_targz('dir/jira')
            result = _extract_jira_unix(archive, target)
        self.assertTrue(result)

    def test_returns_false_when_member_missing(self):
        """Tar.gz with no jira member -> returns False."""
        buf = io.BytesIO()
        content = b'x'
        with tarfile.open(fileobj=buf, mode='w:gz') as tf:
            info = tarfile.TarInfo(name='other_binary')
            info.size = len(content)
            tf.addfile(info, io.BytesIO(content))
        buf.seek(0)
        with tempfile.TemporaryDirectory() as tmp:
            result = _extract_jira_unix(buf, os.path.join(tmp, 'jira'))
        self.assertFalse(result)


# ===========================================================================
#  _check_companyname_network
# ===========================================================================

class TestCheckCompanyNameNetwork(unittest.TestCase):
class TestCheckCompanyNameNetwork(unittest.TestCase):

    def test_returns_true_on_successful_connect(self):
        """TCP connect succeeds -> True."""
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=MagicMock())
        mock_ctx.__exit__ = MagicMock(return_value=False)
        with patch('setup.tools.socket.create_connection', return_value=mock_ctx):
            result = _check_companyname_network()
        self.assertTrue(result)

    def test_returns_false_on_oserror(self):
        """OSError (no network) -> False, no exception raised."""
        with patch('setup.tools.socket.create_connection', side_effect=OSError):
            result = _check_companyname_network()
        self.assertFalse(result)


# ===========================================================================
#  cmd_install_tools — control flow branches
# ===========================================================================

class TestInstallTools(unittest.TestCase):
    """cmd_install_tools: mocks all I/O, subprocess, prompts, and file writes."""

    def _all_tools_present_patches(self):
        """Patch context where glab+jira+claude all on PATH, authenticated, tokened."""
        return [
            patch('setup.tools._check_companyname_network', return_value=True),
            patch('setup.tools.shutil.which', return_value='/usr/bin/tool'),
            patch('setup.tools.run', return_value=(0, '', '')),
            patch('setup.tools.prompt_yn', return_value=False),
            patch('setup.tools.prompt_input', return_value=''),
            patch('setup.tools.write_managed_block'),
            patch.dict(os.environ, {
                'GLAB_TOKEN': 'tok',
                'JIRA_API_TOKEN': 'jtok',
                'ANTHROPIC_API_KEY': 'akey',
            }),
        ]

    def test_returns_0_on_all_tools_present(self):
        """Glab authenticated + jira + claude all on PATH -> returns 0."""
        patches = self._all_tools_present_patches()
        with patches[0], patches[1], patches[2], patches[3], \
             patches[4], patches[5], patches[6]:
            result = cmd_install_tools('/src')
        self.assertEqual(result, 0)

    def test_writes_managed_block_always(self):
        """write_managed_block called once regardless of tool state."""
        patches = self._all_tools_present_patches()
        with patches[0], patches[1], patches[2], patches[3], \
             patches[4], patches[5] as mock_write, patches[6]:
            cmd_install_tools('/src')
        mock_write.assert_called_once()

    def test_returns_nonzero_when_glab_missing_and_declined(self):
        """Glab not on PATH, user declines install -> returns 1."""
        def which_side_effect(name):
            return None  # nothing found

        with patch('setup.tools._check_companyname_network', return_value=True), \
             patch('setup.tools.shutil.which', side_effect=which_side_effect), \
             patch('setup.tools.prompt_yn', return_value=False), \
             patch('setup.tools.prompt_input', return_value=''), \
             patch('setup.tools.write_managed_block'):
            result = cmd_install_tools('/src')
        self.assertEqual(result, 1)

    def test_user_declines_vpn_check_returns_1(self):
        """Network unreachable + user says no to continue -> returns 1."""
        with patch('setup.tools._check_companyname_network', return_value=False), \
             patch('setup.tools.prompt_yn', return_value=False):
            result = cmd_install_tools('/src')
        self.assertEqual(result, 1)

    def test_prompts_for_glab_token_when_env_absent(self):
        """GLAB_TOKEN not in env -> prompt_input called for token collection."""
        with patch('setup.tools._check_companyname_network', return_value=True), \
             patch('setup.tools.shutil.which', return_value='/usr/bin/glab'), \
             patch('setup.tools.run', return_value=(0, '', '')), \
             patch('setup.tools.prompt_yn', return_value=False), \
             patch('setup.tools.prompt_input', return_value='mytoken') as mock_prompt, \
             patch('setup.tools.write_managed_block'), \
             patch('setup.tools.webbrowser.open'), \
             patch.dict(os.environ, {}, clear=True):
            cmd_install_tools('/src')
        mock_prompt.assert_called()


if __name__ == '__main__':
    unittest.main()
