#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for hooks/utils.py — subprocess helpers and tool discovery.

Run:  python -m unittest discover -s .git-hooks/hooks/tests -t .git-hooks -p "test_utils.py" -v
"""

import asyncio
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from pathlib import Path

from git_hooks_impl.templates import (
    _fallback_skeleton,
    _parse_template,
    _resolve_templates_dir,
    basic_fill_template,
    template_skeleton,
)
from git_hooks_impl.utils import (
    _cmd_display,
    find_tool,
    prompt_input,
    prompt_yn,
    run,
    run_async,
)

# ---------------------------------------------------------------------------
#  Module-level log silencing — prevent TESTS.log pollution
# ---------------------------------------------------------------------------

_log_patchers = []

def setUpModule():
    targets = [
        'git_hooks_impl.utils.dbg',
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
#  _parse_template — extract body, labels, assignees from raw template text
# ---------------------------------------------------------------------------

class TestParseTemplate(unittest.TestCase):

    def test_strips_draft(self):
        """/draft line removed from body."""
        body, labels, assignees = _parse_template('/draft\n\n## Description\n\nHello')
        self.assertNotIn('/draft', body)
        self.assertIn('## Description', body)

    def test_extracts_labels(self):
        """/label Fix -> labels=['Fix']."""
        body, labels, _ = _parse_template('## Body\n\n/label Fix')
        self.assertEqual(labels, ['Fix'])
        self.assertNotIn('/label', body)

    def test_extracts_assignees(self):
        """/assign @qa-tester -> assignees=['@qa-tester']."""
        _, _, assignees = _parse_template('## Body\n\n/assign @qa-tester')
        self.assertEqual(assignees, ['@qa-tester'])

    def test_multiple_labels(self):
        """Multiple /label lines -> all extracted in order."""
        text = '## Body\n\n/label Fix\n/label QA Required'
        _, labels, _ = _parse_template(text)
        self.assertEqual(labels, ['Fix', 'QA Required'])

    def test_body_without_quick_actions(self):
        """Body text preserved intact when no quick actions present."""
        text = '## Description\n\nSome text\n\n## Checklist\n\n- [ ] item'
        body, labels, assignees = _parse_template(text)
        self.assertIn('## Description', body)
        self.assertIn('- [ ] item', body)
        self.assertEqual(labels, [])
        self.assertEqual(assignees, [])

    def test_full_template_parse(self):
        """Full template: /draft + /label + /assign all extracted, body clean."""
        text = (
            '/draft\n\n'
            '## Bug description\n\n[Jira Ticket Link]\n\n'
            '## Checklist\n\n- [ ] tested\n\n'
            '/label Fix\n'
            '/assign @qa-tester'
        )
        body, labels, assignees = _parse_template(text)
        self.assertNotIn('/draft', body)
        self.assertNotIn('/label', body)
        self.assertNotIn('/assign', body)
        self.assertEqual(labels, ['Fix'])
        self.assertEqual(assignees, ['@qa-tester'])
        self.assertIn('## Bug description', body)
        self.assertIn('[Jira Ticket Link]', body)


# ---------------------------------------------------------------------------
#  Template skeletons — loading from .gitlab/merge_request_templates/
# ---------------------------------------------------------------------------

class TestTemplates(unittest.TestCase):
    """Tests for template_skeleton() fallback path (no .gitlab/ files in ai_tooling)."""

    def test_fallback_when_file_missing(self):
        """Unknown template name + missing file -> fallback skeleton, empty labels."""
        with patch('git_hooks_impl.templates.os.path.isfile', return_value=False):
            body, labels, assignees = template_skeleton('nonexistent')
        self.assertIn('## Description', body)
        self.assertEqual(labels, [])
        self.assertEqual(assignees, [])


# ---------------------------------------------------------------------------
#  _resolve_templates_dir — runtime context detection (GIT_WORK_TREE vs cwd)
# ---------------------------------------------------------------------------

class TestResolveTemplatesDir(unittest.TestCase):
    """_resolve_templates_dir() locates MR templates relative to project root.

    In hook context GIT_WORK_TREE is set by git; outside hooks (CLI, tests)
    it falls back to os.getcwd().  The module-level _TEMPLATES_DIR is frozen
    at import; this tests the function itself, which re-reads the env each call.
    """

    def test_uses_git_work_tree_when_set(self):
        """GIT_WORK_TREE in env -> path built from that root."""
        with patch.dict(os.environ, {'GIT_WORK_TREE': '/project/root'}):
            result = _resolve_templates_dir()
        expected = '/project/root/.gitlab/merge_request_templates'
        self.assertEqual(str(result).replace('\\', '/'), expected)

    def test_falls_back_to_cwd_when_git_work_tree_absent(self):
        """No GIT_WORK_TREE -> path built from os.getcwd()."""
        env_without = {k: v for k, v in os.environ.items() if k != 'GIT_WORK_TREE'}
        with patch.dict(os.environ, env_without, clear=True), \
             patch('git_hooks_impl.templates.os.getcwd', return_value='/my/cwd'):
            result = _resolve_templates_dir()
        self.assertIn('.gitlab', str(result))
        self.assertIn('merge_request_templates', str(result))
        self.assertTrue(str(result).replace('\\', '/').startswith('/my/cwd'))

    def test_git_work_tree_empty_string_falls_back_to_cwd(self):
        """GIT_WORK_TREE='' (set but empty) -> falls back to cwd."""
        with patch.dict(os.environ, {'GIT_WORK_TREE': ''}), \
             patch('git_hooks_impl.templates.os.getcwd', return_value='/fallback'):
            result = _resolve_templates_dir()
        self.assertTrue(str(result).replace('\\', '/').startswith('/fallback'))

    def test_returns_path_ending_in_merge_request_templates(self):
        """Result always ends with merge_request_templates regardless of root."""
        with patch.dict(os.environ, {'GIT_WORK_TREE': '/any/root'}):
            result = _resolve_templates_dir()
        self.assertEqual(result.name, 'merge_request_templates')


class TestResolveTemplatesDirFallback(unittest.TestCase):
    """Explicit fallback test: GIT_WORK_TREE absent -> cwd used, result non-empty."""

    def test_resolves_without_git_work_tree_set(self):
        """No GIT_WORK_TREE in env -> function returns non-empty Path without raising."""
        env = {k: v for k, v in os.environ.items() if k != 'GIT_WORK_TREE'}
        with patch.dict(os.environ, env, clear=True):
            result = _resolve_templates_dir()
        self.assertIsInstance(result, Path)
        self.assertTrue(len(str(result)) > 0)


# ---------------------------------------------------------------------------
#  Basic fill — inserts Jira summary into the first description placeholder
# ---------------------------------------------------------------------------

class TestBasicFillTemplate(unittest.TestCase):

    def test_no_jira_summary_returns_unchanged(self):
        """Empty jira_sum -> skeleton returned unchanged."""
        body, _, _ = template_skeleton('fix', 'PROJECTNAME-1')
        filled = basic_fill_template(body, '')
        self.assertEqual(filled, body)


# ---------------------------------------------------------------------------
#  _cmd_display — format command list for debug logging
# ---------------------------------------------------------------------------

class TestCmdDisplay(unittest.TestCase):

    def test_truncates_long_arg(self):
        """Arg over 80 chars -> truncated to 77 chars + '..."'."""
        long_arg = 'x' * 100
        result = _cmd_display(['echo', long_arg])
        self.assertIn('...', result)
        self.assertNotIn(long_arg, result)

    def test_quotes_arg_with_space(self):
        """Arg containing a space -> wrapped in double quotes."""
        result = _cmd_display(['echo', 'hello world'])
        self.assertIn('"hello world"', result)

    def test_quotes_arg_with_newline(self):
        """Arg containing a newline -> wrapped in double quotes."""
        result = _cmd_display(['echo', 'line1\nline2'])
        # The actual newline char gets quoted
        self.assertIn('"line1\nline2"', result)

    def test_plain_arg_not_quoted(self):
        """Short arg without spaces -> no quotes."""
        result = _cmd_display(['git', 'status'])
        self.assertEqual(result, 'git status')


# ---------------------------------------------------------------------------
#  _fallback_skeleton — hardcoded fallback when template files are missing
# ---------------------------------------------------------------------------

class TestFallbackSkeleton(unittest.TestCase):

    def test_fix_with_ticket_includes_jira_url(self):
        """template='fix' + jira_ticket='PROJECTNAME-99' -> Jira URL in body."""
        body = _fallback_skeleton('fix', 'PROJECTNAME-99')
        self.assertIn('https://jira.companyname.io/browse/PROJECTNAME-99', body)
        self.assertIn('## Bug description', body)

    def test_fix_without_ticket_no_jira_url(self):
        """template='fix' + no ticket -> no Jira URL, just headings."""
        body = _fallback_skeleton('fix')
        self.assertNotIn('jira.companyname.io', body)
        self.assertIn('## Bug description', body)

    def test_non_fix_returns_generic_sections(self):
        """template='feature' -> ## Description + ## Areas of impact."""
        body = _fallback_skeleton('feature')
        self.assertIn('## Description', body)
        self.assertIn('## Areas of impact', body)
        self.assertNotIn('## Bug description', body)


# ---------------------------------------------------------------------------
#  find_tool — PATH lookup with fallback directories
# ---------------------------------------------------------------------------

class TestFindTool(unittest.TestCase):

    @patch('git_hooks_impl.utils.shutil.which', return_value='/usr/bin/glab')
    def test_returns_path_from_which(self, mock_which):
        """Tool found on PATH via shutil.which -> returned directly."""
        result = find_tool('glab')
        self.assertEqual(result, '/usr/bin/glab')

    @patch('git_hooks_impl.utils.shutil.which', return_value=None)
    @patch('git_hooks_impl.utils.os.path.isfile', return_value=False)
    def test_returns_empty_when_not_found(self, mock_isfile, mock_which):
        """Tool not on PATH, not in fallback dirs -> ''."""
        result = find_tool('glab')
        self.assertEqual(result, '')

    @patch('git_hooks_impl.utils.ensure_path')
    @patch('git_hooks_impl.utils.os.path.isfile', return_value=True)
    @patch('git_hooks_impl.utils.shutil.which', return_value=None)
    def test_finds_in_fallback_dir(self, mock_which, mock_isfile, mock_ensure):
        """Tool not on PATH but exists in fallback dir -> found and PATH updated."""
        result = find_tool('jira')
        self.assertIn('jira', result)
        mock_ensure.assert_called_once()


# ---------------------------------------------------------------------------
#  run() — subprocess wrapper with logging and timing
# ---------------------------------------------------------------------------

class TestRun(unittest.TestCase):
    """Tests for run() — subprocess.run wrapper returning (exit_code, stdout, stderr)."""

    @patch('git_hooks_impl.utils.subprocess.run')
    def test_run_success_returns_tuple(self, mock_subproc):
        """returncode=0 -> (0, stdout, stderr) tuple returned.

        Function under test: run()
        Dependency missed/absent: NO
        """
        mock_subproc.return_value.returncode = 0
        mock_subproc.return_value.stdout = 'output text\n'
        mock_subproc.return_value.stderr = ''
        exit_code, stdout, stderr = run(['git', 'status'])
        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout, 'output text\n')
        self.assertEqual(stderr, '')
        mock_subproc.assert_called_once()

    @patch('git_hooks_impl.utils.subprocess.run')
    def test_run_failure_returns_nonzero(self, mock_subproc):
        """returncode=1 + stderr -> (1, stdout, stderr) tuple returned.

        Function under test: run()
        Dependency missed/absent: NO
        """
        mock_subproc.return_value.returncode = 1
        mock_subproc.return_value.stdout = ''
        mock_subproc.return_value.stderr = 'fatal: not a git repository'
        exit_code, stdout, stderr = run(['git', 'status'])
        self.assertEqual(exit_code, 1)
        self.assertEqual(stderr, 'fatal: not a git repository')

    @patch('git_hooks_impl.utils.subprocess.run')
    def test_run_passes_input_data(self, mock_subproc):
        """input_data provided -> passed to subprocess.run via stdin.

        Function under test: run()
        Dependency missed/absent: NO
        """
        mock_subproc.return_value.returncode = 0
        mock_subproc.return_value.stdout = 'ok'
        mock_subproc.return_value.stderr = ''
        run(['git', 'hash-object', '--stdin'], input_data='hello')
        call_kwargs = mock_subproc.call_args
        self.assertEqual(call_kwargs.kwargs['input'], 'hello')


class TestRunAsync(unittest.IsolatedAsyncioTestCase):
    """Tests for run_async() — async subprocess returning (exit_code, stdout, stderr)."""

    async def test_run_async_returns_output(self):
        """Success -> (0, stdout, stderr) tuple returned."""
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(b'output text\n', b''))
        mock_proc.returncode = 0
        with patch('git_hooks_impl.utils.asyncio.create_subprocess_exec',
                   new_callable=AsyncMock, return_value=mock_proc):
            exit_code, stdout, stderr = await run_async(['git', 'status'])
        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout, 'output text\n')
        self.assertEqual(stderr, '')

    async def test_run_async_nonzero_exit(self):
        """Non-zero exit code -> (N, stdout, stderr) returned, no exception."""
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(b'', b'fatal: not a git repo'))
        mock_proc.returncode = 1
        with patch('git_hooks_impl.utils.asyncio.create_subprocess_exec',
                   new_callable=AsyncMock, return_value=mock_proc):
            exit_code, stdout, stderr = await run_async(['git', 'status'])
        self.assertEqual(exit_code, 1)
        self.assertIn('fatal', stderr)

    async def test_run_async_cancelled_kills_process(self):
        """CancelledError -> process killed before re-raise."""
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.CancelledError())
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock(return_value=None)
        mock_proc.returncode = None
        with patch('git_hooks_impl.utils.asyncio.create_subprocess_exec',
                   new_callable=AsyncMock, return_value=mock_proc):
            with self.assertRaises(asyncio.CancelledError):
                await run_async(['glab', 'api', 'user'])
        mock_proc.kill.assert_called_once()


# ---------------------------------------------------------------------------
#  prompt_yn() — yes/no user prompt
# ---------------------------------------------------------------------------

class TestPromptYn(unittest.TestCase):
    """Tests for prompt_yn() — yes/no prompt with default."""

    @patch('builtins.input', return_value='y')
    def test_prompt_yn_yes(self, mock_input):
        """User types 'y' -> True.

        Function under test: prompt_yn()
        Dependency missed/absent: NO
        """
        self.assertTrue(prompt_yn('Continue?'))

    @patch('builtins.input', return_value='n')
    def test_prompt_yn_no(self, mock_input):
        """User types 'n' -> False.

        Function under test: prompt_yn()
        Dependency missed/absent: NO
        """
        self.assertFalse(prompt_yn('Continue?'))

    @patch('builtins.input', return_value='')
    def test_prompt_yn_empty_default_yes(self, mock_input):
        """User presses Enter with default_yes=True -> True.

        Function under test: prompt_yn()
        Dependency missed/absent: NO
        """
        self.assertTrue(prompt_yn('Continue?', default_yes=True))

    @patch('builtins.input', return_value='')
    def test_prompt_yn_empty_default_no(self, mock_input):
        """User presses Enter with default_yes=False -> False.

        Function under test: prompt_yn()
        Dependency missed/absent: NO
        """
        self.assertFalse(prompt_yn('Continue?', default_yes=False))

    @patch('builtins.input', return_value='yes')
    def test_prompt_yn_yes_full_word(self, mock_input):
        """User types 'yes' -> True.

        Function under test: prompt_yn()
        Dependency missed/absent: NO
        """
        self.assertTrue(prompt_yn('Continue?'))

    @patch('git_hooks_impl.utils.sys.stderr')
    @patch('builtins.input', side_effect=EOFError)
    def test_prompt_yn_eof_returns_false(self, mock_input, mock_stderr):
        """EOFError (piped input) -> False.

        Function under test: prompt_yn()
        Dependency missed/absent: NO
        """
        self.assertFalse(prompt_yn('Continue?'))

    @patch('git_hooks_impl.utils.sys.stderr')
    @patch('builtins.input', side_effect=KeyboardInterrupt)
    def test_prompt_yn_keyboard_interrupt_returns_false(self, mock_input,
                                                        mock_stderr):
        """KeyboardInterrupt (Ctrl+C) -> False.

        Function under test: prompt_yn()
        Dependency missed/absent: NO
        """
        self.assertFalse(prompt_yn('Continue?'))


# ---------------------------------------------------------------------------
#  prompt_input() — single value user prompt
# ---------------------------------------------------------------------------

class TestPromptInput(unittest.TestCase):
    """Tests for prompt_input() — single value prompt with default."""

    @patch('builtins.input', return_value='my-value')
    def test_prompt_input_returns_value(self, mock_input):
        """User types a value -> that value returned.

        Function under test: prompt_input()
        Dependency missed/absent: NO
        """
        result = prompt_input('Enter token')
        self.assertEqual(result, 'my-value')

    @patch('builtins.input', return_value='')
    def test_prompt_input_empty_returns_default(self, mock_input):
        """User presses Enter -> default value returned.

        Function under test: prompt_input()
        Dependency missed/absent: NO
        """
        result = prompt_input('Enter token', default='fallback')
        self.assertEqual(result, 'fallback')

    @patch('git_hooks_impl.utils.sys.stderr')
    @patch('builtins.input', side_effect=EOFError)
    def test_prompt_input_eof_returns_default(self, mock_input, mock_stderr):
        """EOFError -> default value returned.

        Function under test: prompt_input()
        Dependency missed/absent: NO
        """
        result = prompt_input('Enter token', default='safe')
        self.assertEqual(result, 'safe')

    @patch('git_hooks_impl.utils.sys.stderr')
    @patch('builtins.input', side_effect=KeyboardInterrupt)
    def test_prompt_input_keyboard_interrupt_returns_default(self, mock_input,
                                                             mock_stderr):
        """KeyboardInterrupt (Ctrl+C) -> default value returned.

        Function under test: prompt_input()
        Dependency missed/absent: NO
        """
        result = prompt_input('Enter token', default='safe')
        self.assertEqual(result, 'safe')

    @patch('builtins.input', return_value='  spaced  ')
    def test_prompt_input_strips_whitespace(self, mock_input):
        """User types value with leading/trailing spaces -> stripped.

        Function under test: prompt_input()
        Dependency missed/absent: NO
        """
        result = prompt_input('Enter token')
        self.assertEqual(result, 'spaced')


# ---------------------------------------------------------------------------
#  Run all
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    unittest.main(verbosity=2)
