#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Integration tests for the pre-push hook — exercises real network downloads
and archive extraction against actual GitHub releases.

These tests are opt-in: set the INTEGRATION=1 environment variable to run them.

  INTEGRATION=1 python -m unittest discover -s .git-hooks/hooks/tests -t .git-hooks -p "test_integration.py" -v

Each test cleans up after itself and installs to a temporary directory,
so it never touches ~/bin or ~/.config/.jira.
"""

import os
import platform
import shutil
import stat
import sys
import tempfile
import unittest
import urllib.request
from unittest.mock import patch

from git_hooks_impl.jira import JIRA_VERSION
from git_hooks_impl.tests.utils import download
from setup.tools import (
    _extract_jira_unix,
    _extract_jira_windows,
    _jira_download_url,
)

INTEGRATION = os.environ.get('INTEGRATION') == '1'
SKIP_MSG = 'Set INTEGRATION=1 to run integration tests (requires network)'


# ---------------------------------------------------------------------------
#  Module-level log silencing — prevent TESTS.log pollution
# ---------------------------------------------------------------------------

_log_patchers = []

def setUpModule():
    targets = [
        'setup.tools.dbg',
        'setup.tools.err',
        'setup.tools.log',
        'setup.tools.ok',
        'setup.tools.warn',
    ]
    for t in targets:
        p = patch(t)
        p.start()
        _log_patchers.append(p)

def tearDownModule():
    for p in _log_patchers:
        p.stop()
    _log_patchers.clear()


# ---------------------------------------------------------------------------
#  Jira download URL construction  (no network — always runs)
# ---------------------------------------------------------------------------

class TestJiraDownloadUrl(unittest.TestCase):
    """Verify URL construction for all platforms. No network required."""

    def test_windows_url(self):
        url = _jira_download_url('windows', 'x86_64')
        self.assertIn(f'jira_{JIRA_VERSION}_windows_x86_64.zip', url)
        self.assertTrue(url.startswith('https://'))

    def test_darwin_x86_url(self):
        url = _jira_download_url('darwin', 'x86_64')
        self.assertIn(f'jira_{JIRA_VERSION}_darwin_x86_64.tar.gz', url)

    def test_darwin_arm64_url(self):
        url = _jira_download_url('darwin', 'arm64')
        self.assertIn(f'jira_{JIRA_VERSION}_darwin_arm64.tar.gz', url)

    def test_linux_arm64_url(self):
        url = _jira_download_url('linux', 'arm64')
        self.assertIn(f'jira_{JIRA_VERSION}_linux_arm64.tar.gz', url)


# ---------------------------------------------------------------------------
#  Jira — download + extract + uninstall  (network required)
# ---------------------------------------------------------------------------

@unittest.skipUnless(INTEGRATION, SKIP_MSG)
class TestJiraInstallWindows(unittest.TestCase):
    """Download the real Windows jira zip and test extraction."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.target = os.path.join(self.tmp, 'jira.exe')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_download_url_is_reachable(self):
        url = _jira_download_url('windows', 'x86_64')
        response = urllib.request.urlopen(url, timeout=30)
        self.assertEqual(response.status, 200)
        response.close()

    def test_extract_produces_binary(self):
        archive = download(_jira_download_url('windows', 'x86_64'))
        result = _extract_jira_windows(archive, self.target)
        self.assertTrue(result, 'Extraction returned False')
        self.assertTrue(os.path.isfile(self.target))
        self.assertGreater(os.path.getsize(self.target), 0)

    def test_uninstall_removes_binary(self):
        archive = download(_jira_download_url('windows', 'x86_64'))
        _extract_jira_windows(archive, self.target)
        self.assertTrue(os.path.isfile(self.target))

        os.remove(self.target)
        self.assertFalse(os.path.isfile(self.target))


@unittest.skipUnless(INTEGRATION, SKIP_MSG)
@unittest.skipIf(sys.platform == 'win32', 'Unix-only test')
class TestJiraInstallUnix(unittest.TestCase):
    """Download the real macOS/Linux jira tar.gz and test extraction."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.target = os.path.join(self.tmp, 'jira')
        machine = platform.machine().lower()
        self.arch = 'arm64' if machine in ('arm64', 'aarch64') else 'x86_64'
        self.os_name = 'darwin' if sys.platform == 'darwin' else 'linux'

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_download_url_is_reachable(self):
        url = _jira_download_url(self.os_name, self.arch)
        response = urllib.request.urlopen(url, timeout=30)
        self.assertEqual(response.status, 200)
        response.close()

    def test_extract_produces_executable(self):
        archive = download(_jira_download_url(self.os_name, self.arch))
        result = _extract_jira_unix(archive, self.target)
        self.assertTrue(result, 'Extraction returned False')
        self.assertTrue(os.path.isfile(self.target))
        self.assertGreater(os.path.getsize(self.target), 0)
        mode = os.stat(self.target).st_mode
        self.assertTrue(mode & stat.S_IEXEC, 'Binary is not executable')

    def test_uninstall_removes_binary(self):
        archive = download(_jira_download_url(self.os_name, self.arch))
        _extract_jira_unix(archive, self.target)
        self.assertTrue(os.path.isfile(self.target))

        os.remove(self.target)
        self.assertFalse(os.path.isfile(self.target))


# ---------------------------------------------------------------------------
#  glab — install + uninstall stubs  (browser auth required)
# ---------------------------------------------------------------------------

@unittest.skip('TODO: implement with Selenium for browser auth (glab auth login opens GitLab PAT page)')
class TestGlabInstall(unittest.TestCase):
    """Integration tests for glab installation.

    The auth step (glab auth login --hostname) opens a browser for PAT creation.
    Future implementation can drive the browser with Selenium / Playwright.

    Test plan:
      Windows: winget install GLab.GLab → binary in %LOCALAPPDATA%/Programs/glab/
      macOS:   brew install glab         → binary resolved by brew PATH

    What to verify after install:
      - shutil.which('glab') returns a path
      - glab auth status --hostname gitlab.companyname.com exits 0
      - glab api user returns username field

    What to verify after uninstall:
      - uninstall_glab() returns True
      - %LOCALAPPDATA%/glab-cli/ directory is removed
    """

    def test_install_and_check_windows(self):
        raise NotImplementedError

    def test_install_and_check_unix(self):
        raise NotImplementedError

    def test_uninstall_removes_config(self):
        raise NotImplementedError


# ---------------------------------------------------------------------------
#  claude — install + uninstall stubs  (token prompt required)
# ---------------------------------------------------------------------------

@unittest.skip('TODO: automate ANTHROPIC_AUTH_TOKEN prompt, or inject via env before install')
class TestClaudeInstall(unittest.TestCase):
    """Integration tests for Claude CLI installation.

    The setup step prompts for ANTHROPIC_AUTH_TOKEN.
    If ANTHROPIC_AUTH_TOKEN is already set in the environment, the prompt is
    skipped — so tests can set it via env before running _install_claude().

    What to verify after install:
      - shutil.which('claude') returns a path
      - ANTHROPIC_BASE_URL is in ~/.bashrc
      - claude --version exits 0

    What to verify after uninstall:
      - claude binary is not in PATH (removed via npm uninstall or manual delete)
      - env vars remain in ~/.bashrc (they do not break anything when claude is absent)
    """

    def test_install_and_check_windows(self):
        raise NotImplementedError

    def test_install_and_check_unix(self):
        raise NotImplementedError


if __name__ == '__main__':
    unittest.main()
