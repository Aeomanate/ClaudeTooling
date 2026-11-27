#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for hooks/glab.py — GitLab CLI API wrappers.

Run:  python -m unittest discover -s .git-hooks/hooks/tests -t .git-hooks -p "test_glab.py" -v
"""

import unittest
from unittest.mock import AsyncMock, patch

from git_hooks_impl.glab import (
    current_user,
    get_project_path,
    glab_api,
    glab_api_post,
    glab_api_write,
)

# ---------------------------------------------------------------------------
#  Module-level log silencing — prevent TESTS.log pollution
# ---------------------------------------------------------------------------

_log_patchers = []

def setUpModule():
    targets = [
        'git_hooks_impl.glab.warn',
    ]
    for t in targets:
        p = patch(t)
        p.start()
        _log_patchers.append(p)

def tearDownModule():
    for p in _log_patchers:
        p.stop()
    _log_patchers.clear()


class TestGlabApi(unittest.IsolatedAsyncioTestCase):

    @patch('git_hooks_impl.glab.run_async', new_callable=AsyncMock)
    async def test_returns_parsed_json(self, mock_run):
        """GitLab API success -> caller gets structured data for MR operations."""
        mock_run.return_value = (0, '{"username": "dev"}', '')
        result = await glab_api('user')
        self.assertEqual(result, {'username': 'dev'})

    @patch('git_hooks_impl.glab.run_async', new_callable=AsyncMock)
    async def test_returns_none_on_failure(self, mock_run):
        """GitLab API failure -> None so callers can fall back gracefully."""
        mock_run.return_value = (1, '', 'error')
        result = await glab_api('user')
        self.assertIsNone(result)

    @patch('git_hooks_impl.glab.run_async', new_callable=AsyncMock)
    async def test_returns_none_on_invalid_json(self, mock_run):
        """GitLab API returns garbage -> None, never crash the hook."""
        mock_run.return_value = (0, 'not json', '')
        result = await glab_api('user')
        self.assertIsNone(result)


class TestCurrentUser(unittest.IsolatedAsyncioTestCase):

    @patch('git_hooks_impl.glab.glab_api', new_callable=AsyncMock)
    async def test_returns_username(self, mock_api):
        """Authenticated user -> returns GitLab username for MR assignment."""
        mock_api.return_value = {'username': 'dev', 'id': 1}
        self.assertEqual(await current_user(), 'dev')

    @patch('git_hooks_impl.glab.glab_api', new_callable=AsyncMock)
    async def test_returns_empty_on_api_failure(self, mock_api):
        """GitLab API failure -> empty string so callers can fall back gracefully."""
        mock_api.return_value = None
        self.assertEqual(await current_user(), '')

    @patch('git_hooks_impl.glab.glab_api', new_callable=AsyncMock)
    async def test_returns_empty_when_username_field_is_empty(self, mock_api):
        """API returns a dict but username is an empty string."""
        mock_api.return_value = {'username': '', 'id': 1}
        self.assertEqual(await current_user(), '')


class TestGlabApiPost(unittest.IsolatedAsyncioTestCase):

    @patch('git_hooks_impl.glab.glab_api_write', new_callable=AsyncMock)
    async def test_returns_parsed_json_on_success(self, mock_write):
        """POST success -> parsed JSON dict returned."""
        mock_write.return_value = (0, {'id': 'abc123'}, '')
        result = await glab_api_post('projects/1/discussions', {'body': 'hello'})
        self.assertEqual(result, {'id': 'abc123'})

    @patch('git_hooks_impl.glab.glab_api_write', new_callable=AsyncMock)
    async def test_delegates_to_glab_api_write_with_post(self, mock_write):
        """Fields dict -> delegated to glab_api_write with method='POST'."""
        mock_write.return_value = (0, {'id': 'ok'}, '')
        result = await glab_api_post('path', {'body': 'hi', 'position': '1'})
        mock_write.assert_called_once_with('path', {'body': 'hi', 'position': '1'}, method='POST')
        self.assertEqual(result, {'id': 'ok'})

    @patch('git_hooks_impl.glab.glab_api_write', new_callable=AsyncMock)
    async def test_returns_none_on_failure(self, mock_write):
        """Non-zero exit code -> None."""
        mock_write.return_value = (1, None, 'error')
        result = await glab_api_post('path', {'body': 'x'})
        self.assertIsNone(result)

    @patch('git_hooks_impl.glab.glab_api_write', new_callable=AsyncMock)
    async def test_returns_none_on_invalid_json(self, mock_write):
        """Success but invalid JSON response -> None."""
        mock_write.return_value = (0, None, '')
        result = await glab_api_post('path', {'body': 'x'})
        self.assertIsNone(result)


class TestGlabApiWrite(unittest.IsolatedAsyncioTestCase):
    """glab_api_write pipes JSON via stdin to avoid Windows 32K arg limit."""

    @patch('git_hooks_impl.glab.run_async', new_callable=AsyncMock)
    async def test_post_success_returns_parsed_json(self, mock_run):
        """POST with JSON body -> (0, parsed_dict, '')."""
        mock_run.return_value = (0, '{"iid": 42}', '')
        rc, parsed, stderr = await glab_api_write('projects/1/merge_requests', {'title': 'feat'})
        self.assertEqual(rc, 0)
        self.assertEqual(parsed, {'iid': 42})
        self.assertEqual(stderr, '')
        # Verify JSON was piped via input_data kwarg
        _, kwargs = mock_run.call_args
        self.assertEqual(kwargs['input'], '{"title": "feat"}')

    @patch('git_hooks_impl.glab.run_async', new_callable=AsyncMock)
    async def test_post_passes_stdin_flag(self, mock_run):
        """Command includes '--input -' so glab reads body from stdin."""
        mock_run.return_value = (0, '{}', '')
        await glab_api_write('path', {'k': 'v'})
        cmd = mock_run.call_args.args[0]
        self.assertIn('--input', cmd)
        idx = cmd.index('--input')
        self.assertEqual(cmd[idx + 1], '-')

    @patch('git_hooks_impl.glab.run_async', new_callable=AsyncMock)
    async def test_put_method(self, mock_run):
        """method='PUT' -> '--method PUT' in the command."""
        mock_run.return_value = (0, '{"ok": true}', '')
        rc, parsed, _ = await glab_api_write('projects/1/merge_requests/5', {'description': 'x'}, method='PUT')
        cmd = mock_run.call_args.args[0]
        idx = cmd.index('--method')
        self.assertEqual(cmd[idx + 1], 'PUT')
        self.assertEqual(rc, 0)
        self.assertEqual(parsed, {'ok': True})

    @patch('git_hooks_impl.glab.run_async', new_callable=AsyncMock)
    async def test_json_parse_failure_returns_none(self, mock_run):
        """Glab returns non-JSON stdout -> parsed is None, no crash."""
        mock_run.return_value = (0, 'not valid json', '')
        rc, parsed, stderr = await glab_api_write('path', {'k': 'v'})
        self.assertEqual(rc, 0)
        self.assertIsNone(parsed)

    @patch('git_hooks_impl.glab.run_async', new_callable=AsyncMock)
    async def test_empty_stdout_returns_none(self, mock_run):
        """Glab returns empty stdout -> parsed is None."""
        mock_run.return_value = (0, '', '')
        rc, parsed, stderr = await glab_api_write('path', {'k': 'v'})
        self.assertEqual(rc, 0)
        self.assertIsNone(parsed)

    @patch('git_hooks_impl.glab.run_async', new_callable=AsyncMock)
    async def test_glab_error_returns_nonzero_exit_code(self, mock_run):
        """Glab failure -> non-zero exit_code, parsed is None, stderr captured."""
        mock_run.return_value = (1, '', 'authentication required')
        rc, parsed, stderr = await glab_api_write('path', {'k': 'v'})
        self.assertEqual(rc, 1)
        self.assertIsNone(parsed)
        self.assertEqual(stderr, 'authentication required')


class TestGetProjectPath(unittest.IsolatedAsyncioTestCase):
    """Extracts 'group/project' from git remote URL (SSH or HTTPS)."""

    @patch('git_hooks_impl.glab.run_async', new_callable=AsyncMock)
    async def test_ssh_url_parsing(self, mock_run):
        """SSH URL 'git@gitlab.com:group/project.git' -> 'group/project'."""
        mock_run.return_value = (0, 'git@gitlab.com:group/project.git\n', '')
        self.assertEqual(await get_project_path(), 'group/project')

    @patch('git_hooks_impl.glab.run_async', new_callable=AsyncMock)
    async def test_https_url_parsing(self, mock_run):
        """HTTPS URL 'https://gitlab.com/group/project.git' -> 'group/project'."""
        mock_run.return_value = (0, 'https://gitlab.com/group/project.git\n', '')
        self.assertEqual(await get_project_path(), 'group/project')

    @patch('git_hooks_impl.glab.run_async', new_callable=AsyncMock)
    async def test_https_url_no_dot_git(self, mock_run):
        """HTTPS URL without .git suffix -> still parses correctly."""
        mock_run.return_value = (0, 'https://gitlab.com/group/productname/reponame\n', '')
        mock_run.return_value = (0, 'https://gitlab.com/group/productname/reponame\n', '')
        self.assertEqual(await get_project_path(), 'productname/reponame')
        self.assertEqual(await get_project_path(), 'productname/reponame')
        self.assertEqual(await get_project_path(), 'productname/reponame')
        self.assertEqual(await get_project_path(), 'productname/reponame')

    @patch('git_hooks_impl.glab.run_async', new_callable=AsyncMock)
    async def test_git_remote_failure(self, mock_run):
        """Git remote get-url fails (rc=1) -> returns empty string."""
        mock_run.return_value = (1, '', 'not a git repo')
        self.assertEqual(await get_project_path(), '')

    @patch('git_hooks_impl.glab.run_async', new_callable=AsyncMock)
    async def test_unparseable_url(self, mock_run):
        """Unusual URL format that doesn't match the regex -> returns empty string."""
        mock_run.return_value = (0, 'some-weird-string\n', '')
        self.assertEqual(await get_project_path(), '')
