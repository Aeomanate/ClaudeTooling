#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for hooks/jira.py — Jira CLI wrapper.

Run:  python -m unittest discover -s .git-hooks/hooks/tests -t .git-hooks -p "test_jira.py" -v
"""

import unittest
from unittest.mock import AsyncMock, patch

from git_hooks_impl.jira import jira_summary

# ---------------------------------------------------------------------------
#  Module-level log silencing — prevent TESTS.log pollution
# ---------------------------------------------------------------------------

_log_patchers = []

def setUpModule():
    targets = [
        'git_hooks_impl.jira.log',
        'git_hooks_impl.jira.warn',
    ]
    for t in targets:
        p = patch(t)
        p.start()
        _log_patchers.append(p)

def tearDownModule():
    for p in _log_patchers:
        p.stop()
    _log_patchers.clear()


class TestJiraSummary(unittest.IsolatedAsyncioTestCase):

    @patch('git_hooks_impl.jira.find_tool', return_value='/usr/bin/jira')
    @patch('git_hooks_impl.jira.run_async', new_callable=AsyncMock)
    async def test_extracts_summary_from_header(self, mock_run, mock_which):
        """Jira issue view returns markdown — summary is the first # header."""
        mock_run.return_value = (0, '# [Profile Switching] Fix crash\n\nDetails...', '')
        summary, content = await jira_summary('PROJECTNAME-1234')
        self.assertEqual(summary, '[Profile Switching] Fix crash')
        self.assertIn('Details...', content)

    @patch('git_hooks_impl.jira.find_tool', return_value='/usr/bin/jira')
    @patch('git_hooks_impl.jira.run_async', new_callable=AsyncMock)
    async def test_returns_empty_on_failure(self, mock_run, mock_which):
        """Jira CLI error -> empty strings so MR title falls back to branch name."""
        mock_run.return_value = (1, '', 'not found')
        summary, content = await jira_summary('PROJECTNAME-9999')
        self.assertEqual(summary, '')
        self.assertEqual(content, '')

    @patch('git_hooks_impl.jira.find_tool', return_value='')
    async def test_returns_empty_when_jira_not_installed(self, mock_which):
        """No jira binary on PATH -> graceful skip, empty strings returned."""
        summary, content = await jira_summary('PROJECTNAME-1')
        self.assertEqual(summary, '')
        self.assertEqual(content, '')

    @patch('git_hooks_impl.jira.find_tool', return_value='/usr/bin/jira')
    @patch('git_hooks_impl.jira.run_async', new_callable=AsyncMock)
    async def test_returns_empty_on_empty_output(self, mock_run, mock_which):
        """Jira returns success but output is whitespace-only -> ('', '')."""
        mock_run.return_value = (0, '   \n  ', '')
        summary, content = await jira_summary('PROJECTNAME-5')
        self.assertEqual(summary, '')
        self.assertEqual(content, '')

    @patch('git_hooks_impl.jira.find_tool', return_value='/usr/bin/jira')
    @patch('git_hooks_impl.jira.run_async', new_callable=AsyncMock)
    async def test_returns_empty_summary_when_no_header(self, mock_run, mock_which):
        """Jira returns content but no '# ...' header -> summary='', content kept."""
        mock_run.return_value = (0, 'No header here\nJust text', '')
        summary, content = await jira_summary('PROJECTNAME-6')
        self.assertEqual(summary, '')
        self.assertIn('No header here', content)
