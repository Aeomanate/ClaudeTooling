#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for hooks/first_push.py — MR title generation and MR creation.

Run:  python -m unittest discover -s .git-hooks/hooks/tests -t .git-hooks -p "test_first_push.py" -v
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from git_hooks_impl.first_push import (
    _extract_mr_url,
    _extract_summary_from_plan_title,
    create_mr,
    mr_title,
)
from git_hooks_impl.plan.parser import plan_footer as build_plan_footer

# ---------------------------------------------------------------------------
#  Module-level log silencing — prevent TESTS.log pollution
# ---------------------------------------------------------------------------

_log_patchers = []

def setUpModule():
    targets = [
        'git_hooks_impl.first_push.dbg',
        'git_hooks_impl.first_push.err',
        'git_hooks_impl.first_push.log',
        'git_hooks_impl.first_push.ok',
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
#  MR title — built from Jira summary or derived from branch name
# ---------------------------------------------------------------------------

class TestMrTitle(unittest.TestCase):

    def test_with_jira_ticket_and_summary(self):
        """MR title from Jira: ticket + summary -> '[PROJECTNAME-1234] Fix race condition'."""
        title = mr_title('productname/fixes/PROJECTNAME-1234_fix', 'PROJECTNAME-1234', 'Fix race condition')
        title = mr_title('productname/fixes/PROJECTNAME-1234_fix', 'PROJECTNAME-1234', 'Fix race condition')
        self.assertEqual(title, '[PROJECTNAME-1234] Fix race condition')

    def test_without_jira_derives_from_branch(self):
        """No Jira -> capitalise branch tail, underscores become spaces."""
        title = mr_title('productname/fixes/dangerous_race_condition', '', '')
        title = mr_title('productname/fixes/dangerous_race_condition', '', '')
        self.assertEqual(title, 'Dangerous race condition')

    def test_strips_ticket_prefix_from_tail(self):
        """If branch tail starts with TICKET_, it's stripped from derived title."""
        title = mr_title('productname/fixes/PROJECTNAME-1234_race_condition', '', '')
        title = mr_title('productname/fixes/PROJECTNAME-1234_race_condition', '', '')
        self.assertEqual(title, 'Race condition')

    def test_jira_ticket_without_summary_keeps_prefix(self):
        """Ticket present but no summary -> '[PROJECTNAME-1234] Fix' (ticket prefix kept)."""
        title = mr_title('productname/fixes/PROJECTNAME-1234_fix', 'PROJECTNAME-1234', '')
        title = mr_title('productname/fixes/PROJECTNAME-1234_fix', 'PROJECTNAME-1234', '')
        self.assertEqual(title, '[PROJECTNAME-1234] Fix')

    def test_lowercase_ticket_stripped_from_derived_title(self):
        """Lowercase ticket prefix in branch name is stripped from derived title."""
        title = mr_title('productname/fixes/productname-1234_race_condition', '', '')
        title = mr_title('productname/fixes/productname-1234_race_condition', '', '')
        self.assertEqual(title, 'Race condition')

    def test_empty_tail_after_stripping_returns_raw_tail(self):
        """If stripping ticket leaves nothing, fall back to the raw branch tail."""
        title = mr_title('productname/fixes/PROJECTNAME-1234_', '', '')
        title = mr_title('productname/fixes/PROJECTNAME-1234_', '', '')
        self.assertEqual(title, 'PROJECTNAME-1234_')


# ---------------------------------------------------------------------------
#  create_mr — first push creates a draft MR via glab
# ---------------------------------------------------------------------------

_MR_RESPONSE = {'web_url': 'https://gitlab.example.com/mr/1', 'iid': 1}


@patch('git_hooks_impl.first_push.webbrowser.open')
@patch('git_hooks_impl.first_push.get_project_path', return_value='group/productname/reponame')
@patch('git_hooks_impl.first_push.get_project_path', return_value='group/productname/reponame')
@patch('git_hooks_impl.first_push.template_skeleton', return_value=('skeleton', ['Fix'], []))
@patch('git_hooks_impl.first_push.visible_plan_body', return_value='')
@patch('git_hooks_impl.first_push.basic_fill_template', return_value='filled body')
class TestCreateMr(unittest.TestCase):

    @patch('git_hooks_impl.first_push.glab_api_write', new_callable=AsyncMock)
    def test_creates_draft_mr_via_api(self, mock_write, _mock_fill,
                                       _mock_vpb, _mock_skel, _mock_proj, _mock_browser):
        """MR is created via glab_api_write with correct API path and payload."""
        mock_write.return_value = (0, _MR_RESPONSE, '')
        asyncio.run(create_mr(
            branch='productname/fixes/PROJECTNAME-1_fix',
            branch='productname/fixes/PROJECTNAME-1_fix',
            template='fix',
            jira_ticket='',
            plan_content='plan',
            plan_footer=build_plan_footer('plan'),
            username='dev',
        ))
        api_path, payload = mock_write.call_args.args
        self.assertIn('merge_requests', api_path)
        self.assertEqual(payload['source_branch'], 'productname/fixes/PROJECTNAME-1_fix')
        self.assertEqual(payload['source_branch'], 'productname/fixes/PROJECTNAME-1_fix')
        self.assertEqual(payload['target_branch'], 'master')
        self.assertTrue(payload['title'].startswith('Draft: '))

    @patch('git_hooks_impl.first_push.glab_api_write', new_callable=AsyncMock)
    def test_applies_labels_for_fix_template(self, mock_write, _mock_fill,
                                              _mock_vpb, _mock_skel, _mock_proj, _mock_browser):
        """Fix branch -> MR created with 'Fix' label in payload."""
        mock_write.return_value = (0, _MR_RESPONSE, '')
        asyncio.run(create_mr('productname/fixes/x', 'fix', '', 'plan',
        asyncio.run(create_mr('productname/fixes/x', 'fix', '', 'plan',
                   build_plan_footer('plan'), 'dev'))
        _, payload = mock_write.call_args.args
        self.assertIn('Fix', payload['labels'])

    @patch('git_hooks_impl.first_push.glab_api_write', new_callable=AsyncMock)
    def test_description_contains_plan_footer(self, mock_write, _mock_fill,
                                               mock_vpb, _mock_skel, _mock_proj, _mock_browser):
        """MR description embeds the plan-meta footer when the plan has a visible body."""
        plan = '# Feature\n\n## Context\n\nmy plan content\n'
        mock_vpb.return_value = '## Context\n\nmy plan content\n'
        mock_write.return_value = (0, _MR_RESPONSE, '')
        asyncio.run(create_mr('productname/fixes/x', 'fix', '', plan,
        asyncio.run(create_mr('productname/fixes/x', 'fix', '', plan,
                   build_plan_footer(plan), 'dev'))
        _, payload = mock_write.call_args.args
        self.assertIn('<!-- plan-meta', payload['description'])
        self.assertIn('my plan content', payload['description'])

    @patch('git_hooks_impl.first_push.glab_api_write', new_callable=AsyncMock)
    def test_opens_browser_after_mr_creation(self, mock_write, _mock_fill,
                                              _mock_vpb, _mock_skel, _mock_proj, mock_browser):
        """Browser opens to the new MR URL after successful creation."""
        mock_write.return_value = (0, {'web_url': 'https://gitlab.example.com/mr/99'}, '')
        asyncio.run(create_mr('productname/fixes/x', 'fix', '', '', '', 'dev'))
        asyncio.run(create_mr('productname/fixes/x', 'fix', '', '', '', 'dev'))
        mock_browser.assert_called_once_with('https://gitlab.example.com/mr/99')

    @patch('git_hooks_impl.first_push.glab_api_write', new_callable=AsyncMock)
    def test_no_browser_on_mr_creation_failure(self, mock_write, _mock_fill,
                                                _mock_vpb, _mock_skel, _mock_proj, mock_browser):
        """API failure -> err() called, browser NOT opened."""
        mock_write.return_value = (1, None, 'fatal error')
        asyncio.run(create_mr('productname/fixes/x', 'fix', '', '', '', 'dev'))
        asyncio.run(create_mr('productname/fixes/x', 'fix', '', '', '', 'dev'))
        mock_browser.assert_not_called()

    @patch('git_hooks_impl.first_push.glab_api_write', new_callable=AsyncMock)
    def test_jira_summary_line_used_in_title(self, mock_write, _mock_fill,
                                              _mock_vpb, _mock_skel, _mock_proj, _mock_browser):
        """jira_summary_line param -> title uses 'Draft: [PROJECTNAME-10] Fix crash'."""
        mock_write.return_value = (0, _MR_RESPONSE, '')
        asyncio.run(create_mr('productname/fixes/PROJECTNAME-10_fix', 'fix', 'PROJECTNAME-10', '', '', 'dev',
        asyncio.run(create_mr('productname/fixes/PROJECTNAME-10_fix', 'fix', 'PROJECTNAME-10', '', '', 'dev',
                   jira_summary_line='Fix crash'))
        _, payload = mock_write.call_args.args
        self.assertEqual(payload['title'], 'Draft: [PROJECTNAME-10] Fix crash')

    @patch('git_hooks_impl.first_push.glab_api_write', new_callable=AsyncMock)
    def test_template_assignees_not_in_payload(self, mock_write, _mock_fill,
                                                _mock_vpb, mock_skel, _mock_proj, mock_browser):
        """Template /assign @qa-tester is a quick action -- not in API payload."""
        mock_skel.return_value = ('skeleton', ['Fix'], ['qa-tester'])
        mock_write.return_value = (0, _MR_RESPONSE, '')
        asyncio.run(create_mr('productname/fixes/x', 'fix', '', '', '', 'dev'))
        asyncio.run(create_mr('productname/fixes/x', 'fix', '', '', '', 'dev'))
        _, payload = mock_write.call_args.args
        self.assertNotIn('assignee_ids', payload)

    @patch('git_hooks_impl.first_push.glab_api_write', new_callable=AsyncMock)
    def test_no_labels_omits_labels_key(self, mock_write, _mock_fill,
                                         _mock_vpb, mock_skel, _mock_proj, mock_browser):
        """No labels -> 'labels' key absent from payload."""
        mock_skel.return_value = ('skeleton', [], [])
        mock_write.return_value = (0, _MR_RESPONSE, '')
        asyncio.run(create_mr('productname/fixes/x', 'fix', '', '', '', 'dev'))
        asyncio.run(create_mr('productname/fixes/x', 'fix', '', '', '', 'dev'))
        _, payload = mock_write.call_args.args
        self.assertNotIn('labels', payload)

    @patch('git_hooks_impl.first_push.glab_api_write', new_callable=AsyncMock)
    def test_project_path_encoded_in_api_path(self, mock_write, _mock_fill,
                                               _mock_vpb, _mock_skel, _mock_proj, _mock_browser):
        """Project path slashes are URL-encoded in the API path."""
        mock_write.return_value = (0, _MR_RESPONSE, '')
        asyncio.run(create_mr('productname/fixes/x', 'fix', '', '', '', 'dev'))
        asyncio.run(create_mr('productname/fixes/x', 'fix', '', '', '', 'dev'))
        api_path = mock_write.call_args.args[0]
        self.assertIn('dx%2Fproductname%2Freponame', api_path)
        self.assertIn('dx%2Fproductname%2Freponame', api_path)
        self.assertIn('dx%2Fproductname%2Freponame', api_path)
        self.assertIn('dx%2Fproductname%2Freponame', api_path)
        self.assertNotIn('group/productname/reponame', api_path)
        self.assertNotIn('group/productname/reponame', api_path)


# ---------------------------------------------------------------------------
#  _extract_summary_from_plan_title — Jira summary from plan heading
# ---------------------------------------------------------------------------

class TestExtractSummaryFromPlanTitle(unittest.TestCase):
    """Extract Jira summary text from the plan's first heading line."""

    def test_outer_bracket_format_extracts_summary(self):
        """'# [[PROJECTNAME-1234] Fix race condition]' -> 'Fix race condition'."""
        plan = '# [[PROJECTNAME-1234] Fix race condition in auth]\n## Context\n'
        result = _extract_summary_from_plan_title(plan, 'PROJECTNAME-1234')
        self.assertEqual(result, 'Fix race condition in auth')

    def test_legacy_format_without_outer_brackets(self):
        """'# [PROJECTNAME-1234] Fix crash' (no outer brackets) -> 'Fix crash'."""
        plan = '# [PROJECTNAME-1234] Fix crash on startup\n## Context\n'
        result = _extract_summary_from_plan_title(plan, 'PROJECTNAME-1234')
        self.assertEqual(result, 'Fix crash on startup')

    def test_empty_plan_returns_empty(self):
        """plan_content='' -> '' (no title to parse)."""
        result = _extract_summary_from_plan_title('', 'PROJECTNAME-1234')
        self.assertEqual(result, '')

    def test_no_jira_ticket_returns_empty(self):
        """jira_ticket='' -> '' (can't strip prefix without ticket)."""
        plan = '# [[PROJECTNAME-1234] Fix race condition]\n'
        result = _extract_summary_from_plan_title(plan, '')
        self.assertEqual(result, '')

    def test_ticket_not_in_title_returns_empty(self):
        """Title doesn't start with [TICKET] prefix -> '' (no match)."""
        plan = '# [OTHER-999] Unrelated task\n'
        result = _extract_summary_from_plan_title(plan, 'PROJECTNAME-1234')
        self.assertEqual(result, '')

    def test_leading_whitespace_stripped(self):
        """Plan content with leading newlines -> first non-empty line parsed."""
        plan = '\n\n# [[PROJECTNAME-5] Add tests]\n'
        result = _extract_summary_from_plan_title(plan, 'PROJECTNAME-5')
        self.assertEqual(result, 'Add tests')

    def test_title_without_heading_prefix_returns_empty(self):
        """First line doesn't start with '# ' -> '' (not a title)."""
        plan = '[PROJECTNAME-1234] No heading marker\n'
        result = _extract_summary_from_plan_title(plan, 'PROJECTNAME-1234')
        self.assertEqual(result, '')

    def test_trailing_bracket_in_summary_not_misdetected_as_outer_format(self):
        """Title ending with ']' that is NOT the outer-bracket format.

        '# [PROJECTNAME-1234] Fix array indexing [0]' ends with ']' but the '[0]'
        is part of the summary, not an outer bracket wrapper. Before the fix,
        endswith(']') caused the code to strip the trailing ']', producing
        the corrupted summary 'Fix array indexing [0' instead of the correct
        'Fix array indexing [0]'.
        """
        plan = '# [PROJECTNAME-1234] Fix array indexing [0]\n## Context\n'
        result = _extract_summary_from_plan_title(plan, 'PROJECTNAME-1234')
        self.assertEqual(result, 'Fix array indexing [0]')


# ---------------------------------------------------------------------------
#  _extract_mr_url — extract URL from API response dict
# ---------------------------------------------------------------------------

class TestExtractMrUrl(unittest.TestCase):
    """Pure function: extract URL from GitLab API response dict."""

    def test_url_found_in_response(self):
        """Response dict with web_url -> extracted correctly."""
        response = {'web_url': 'https://gitlab.example.com/group/productname/reponame/-/merge_requests/42', 'iid': 42}
        response = {'web_url': 'https://gitlab.example.com/group/productname/reponame/-/merge_requests/42', 'iid': 42}
        result = _extract_mr_url(response)
        self.assertEqual(result, 'https://gitlab.example.com/group/productname/reponame/-/merge_requests/42')
        self.assertEqual(result, 'https://gitlab.example.com/group/productname/reponame/-/merge_requests/42')

    def test_none_response_returns_empty(self):
        """None response -> '' returned."""
        result = _extract_mr_url(None)
        self.assertEqual(result, '')

    def test_empty_dict_returns_empty(self):
        """Empty dict -> '' returned (no web_url key)."""
        result = _extract_mr_url({})
        self.assertEqual(result, '')

    def test_dict_without_web_url_returns_empty(self):
        """Dict missing web_url key -> '' returned."""
        result = _extract_mr_url({'iid': 42, 'title': 'Some MR'})
        self.assertEqual(result, '')

    def test_non_dict_response_returns_empty(self):
        """Non-dict response (e.g. string) -> '' returned."""
        result = _extract_mr_url('unexpected string')
        self.assertEqual(result, '')


# ---------------------------------------------------------------------------
#  create_mr — glab failure path
# ---------------------------------------------------------------------------

@patch('git_hooks_impl.first_push.webbrowser.open')
@patch('git_hooks_impl.first_push.get_project_path', return_value='group/productname/reponame')
@patch('git_hooks_impl.first_push.get_project_path', return_value='group/productname/reponame')
@patch('git_hooks_impl.first_push.template_skeleton', return_value=('skeleton', ['Fix'], []))
@patch('git_hooks_impl.first_push.visible_plan_body', return_value='')
@patch('git_hooks_impl.first_push.basic_fill_template', return_value='filled body')
class TestCreateMrFailurePath(unittest.TestCase):
    """MR creation failure: API returns error or no web_url."""

    @patch('git_hooks_impl.first_push.glab_api_write', new_callable=AsyncMock)
    def test_api_failure_shows_error(self, mock_write, _mock_fill,
                                      _mock_vpb, _mock_skel, _mock_proj, mock_browser):
        """API returns non-zero exit code -> browser not opened.

        err() is called with the error lines (silenced by module-level patchers).
        """
        mock_write.return_value = (1, None, 'authorization error')
        asyncio.run(create_mr('productname/fixes/x', 'fix', '', '', '', 'dev'))
        asyncio.run(create_mr('productname/fixes/x', 'fix', '', '', '', 'dev'))
        mock_browser.assert_not_called()

    @patch('git_hooks_impl.first_push.glab_api_write', new_callable=AsyncMock)
    def test_api_success_but_no_web_url_still_errors(self, mock_write, _mock_fill,
                                                      _mock_vpb, _mock_skel, _mock_proj, mock_browser):
        """API exits 0 but response has no web_url -> still treated as failure."""
        mock_write.return_value = (0, {'iid': 42}, '')
        asyncio.run(create_mr('productname/fixes/x', 'fix', '', '', '', 'dev'))
        asyncio.run(create_mr('productname/fixes/x', 'fix', '', '', '', 'dev'))
        mock_browser.assert_not_called()

    @patch('git_hooks_impl.first_push.glab_api_write', new_callable=AsyncMock)
    def test_project_path_failure_skips_creation(self, mock_write, _mock_fill,
                                                  _mock_vpb, _mock_skel, mock_proj, mock_browser):
        """get_project_path returns '' -> MR creation skipped entirely."""
        mock_proj.return_value = ''
        asyncio.run(create_mr('productname/fixes/x', 'fix', '', '', '', 'dev'))
        asyncio.run(create_mr('productname/fixes/x', 'fix', '', '', '', 'dev'))
        mock_write.assert_not_called()
        mock_browser.assert_not_called()


# ---------------------------------------------------------------------------
#  Run all
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    unittest.main(verbosity=2)
