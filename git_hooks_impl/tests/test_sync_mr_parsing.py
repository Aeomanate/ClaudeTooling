#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for hooks/sync_mr.py — branch name parsing, PLAN.md section
wrapping, MR body-hash edit detection, plan-to-body mapping, and update_mr()
(replaces the PLAN.md section in an existing MR description).

Run:  python -m unittest discover -s .git-hooks/hooks/tests -t .git-hooks -p "test_sync_mr_parsing.py" -v
"""

import unittest
from unittest.mock import AsyncMock, patch

# Silence all logging — tests that verify log calls use their own @patch
_log_patchers = [
    patch('git_hooks_impl.entry_points.sync_mr.log'),
    patch('git_hooks_impl.entry_points.sync_mr.warn'),
    patch('git_hooks_impl.entry_points.sync_mr.err'),
    patch('git_hooks_impl.entry_points.sync_mr.dbg'),
    patch('git_hooks_impl.entry_points.sync_mr.ok'),
    # branch_utils is tested directly in this file — silence its logging too
    patch('git_hooks_impl.branch_utils.log'),
    patch('git_hooks_impl.branch_utils.warn'),
    patch('git_hooks_impl.branch_utils.dbg'),
]


def setUpModule():
    for p in _log_patchers:
        p.start()


def tearDownModule():
    for p in _log_patchers:
        p.stop()

from git_hooks_impl.branch_utils import (
    _clean_body,
    _compute_mr_body_hash,
    _embed_body_hash,
    body_was_edited,
    parse_branch,
)
from git_hooks_impl.entry_points.sync_mr import (
    _extract_checklist,
    _map_plan_to_body,
    update_mr,
)
from git_hooks_impl.plan.parser import extract_footer_meta

# ---------------------------------------------------------------------------
#  Branch parsing — determines template and Jira ticket from branch name
# ---------------------------------------------------------------------------

class TestParseBranch(unittest.TestCase):
    """Branch naming convention:
      <swimlane>/(fixes|features|devices|docs)/<description>
      private/<username>/<description>
    The Jira ticket is optional, prefixed before the description: PROJ-1234_
    """

    def test_fixes_branch_with_ticket(self):
        """'productname/fixes/PROJECTNAME-1234_dangerous_race' -> fix template + PROJECTNAME-1234 ticket."""
        """'productname/fixes/PROJECTNAME-1234_dangerous_race' -> fix template + PROJECTNAME-1234 ticket."""
        template, ticket = parse_branch('productname/fixes/PROJECTNAME-1234_dangerous_race')
        template, ticket = parse_branch('productname/fixes/PROJECTNAME-1234_dangerous_race')
        self.assertEqual(template, 'fix')
        self.assertEqual(ticket, 'PROJECTNAME-1234')

    def test_features_branch_with_ticket(self):
        """'gkbm/features/GKBM-567_new_lighting' -> feature template + GKBM-567 ticket."""
        template, ticket = parse_branch('gkbm/features/GKBM-567_new_lighting')
        self.assertEqual(template, 'feature')
        self.assertEqual(ticket, 'GKBM-567')

    def test_devices_branch_no_ticket(self):
        """Devices swimlane without ticket -> default template, no ticket."""
        template, ticket = parse_branch('gsim/devices/da_silva')
        self.assertEqual(template, 'default')
        self.assertEqual(ticket, '')

    def test_docs_branch_with_ticket(self):
        """'productname/docs/PROJECTNAME-100_api_docs' -> documentation template + PROJECTNAME-100."""
        """'productname/docs/PROJECTNAME-100_api_docs' -> documentation template + PROJECTNAME-100."""
        template, ticket = parse_branch('productname/docs/PROJECTNAME-100_api_docs')
        template, ticket = parse_branch('productname/docs/PROJECTNAME-100_api_docs')
        self.assertEqual(template, 'documentation')
        self.assertEqual(ticket, 'PROJECTNAME-100')

    def test_documentation_branch_with_ticket(self):
        """Long-form 'documentation' swimlane -> same template as 'docs'."""
        template, ticket = parse_branch('productname/documentation/PROJECTNAME-200_update_readme')
        template, ticket = parse_branch('productname/documentation/PROJECTNAME-200_update_readme')
        self.assertEqual(template, 'documentation')
        self.assertEqual(ticket, 'PROJECTNAME-200')

    def test_private_branch(self):
        """Private branch -> default template, no ticket extraction."""
        template, ticket = parse_branch('private/rbosa/experiment')
        self.assertEqual(template, 'default')
        self.assertEqual(ticket, '')

    def test_fixes_branch_without_ticket(self):
        """Missing ticket -> still returns 'fix' template, empty ticket string."""
        template, ticket = parse_branch('productname/fixes/no_ticket_here')
        template, ticket = parse_branch('productname/fixes/no_ticket_here')
        self.assertEqual(template, 'fix')
        self.assertEqual(ticket, '')

    def test_nonconformant_branch(self):
        """Unknown format -> falls back to 'default' template."""
        template, ticket = parse_branch('some-random-branch')
        self.assertEqual(template, 'default')
        self.assertEqual(ticket, '')

    def test_different_swimlanes(self):
        """Any lowercase swimlane code is accepted."""
        for swimlane in ('productname', 'gxdv', 'gsim', 'gkbm'):
        for swimlane in ('productname', 'gxdv', 'gsim', 'gkbm'):
            template, ticket = parse_branch(f'{swimlane}/fixes/PROJECTNAME-1_fix')
            self.assertEqual(template, 'fix', f"Failed for swimlane '{swimlane}'")

    def test_lowercase_ticket_uppercased(self):
        """Lowercase ticket in branch name is normalised to uppercase."""
        template, ticket = parse_branch('productname/fixes/productname-1234_my_fix')
        template, ticket = parse_branch('productname/fixes/productname-1234_my_fix')
        self.assertEqual(template, 'fix')
        self.assertEqual(ticket, 'PROJECTNAME-1234')


# ---------------------------------------------------------------------------
#  PLAN.md section — appended to every MR description
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
#  Body hash — detects manual edits to MR body on GitLab
# ---------------------------------------------------------------------------

class TestBodyHash(unittest.TestCase):

    def test_compute_mr_body_hash_deterministic(self):
        """Same input -> same hash."""
        h1 = _compute_mr_body_hash('## Description\n\nSome text')
        h2 = _compute_mr_body_hash('## Description\n\nSome text')
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 12)

    def test_compute_mr_body_hash_differs_on_change(self):
        """Different input -> different hash."""
        h1 = _compute_mr_body_hash('Original text')
        h2 = _compute_mr_body_hash('Edited text')
        self.assertNotEqual(h1, h2)

    def test_clean_body_strips_footer_and_body_hash(self):
        """Strips the plan-meta footer and body-hash comment, keeps everything
        else (## Discussions is part of the visible body now, not stripped).
        """
        desc = (
            '## Description\n\nVisible body'
            '\n\n## Discussions\n\n### [Topic](url)'
            '\n\n<!-- plan-meta\nplan-hash: abc\nbody-hash: abc\n-->'
            '\n<!-- body-hash: abc123def456 -->'
        )
        clean = _clean_body(desc)
        self.assertIn('Visible body', clean)
        self.assertIn('## Discussions', clean)
        self.assertIn('[Topic](url)', clean)
        self.assertNotIn('plan-meta', clean)
        self.assertNotIn('body-hash', clean)

    def test_body_was_edited_no_hash(self):
        """No body-hash in description -> treated as not edited (first push)."""
        desc = '## Description\n\nSome text'
        edited, clean = body_was_edited(desc)
        self.assertFalse(edited)
        self.assertIn('Some text', clean)

    def test_body_was_edited_hash_matches(self):
        """Body-hash matches current body -> not edited."""
        body = '## Description\n\nSome text'
        h = _compute_mr_body_hash(body)
        desc = f'{body}\n<!-- body-hash: {h} -->'
        edited, clean = body_was_edited(desc)
        self.assertFalse(edited)

    def test_body_was_edited_hash_mismatch(self):
        """Body-hash doesn't match (someone edited on GitLab) -> edited=True."""
        desc = '## Description\n\nEdited on GitLab\n<!-- body-hash: 000000000000 -->'
        edited, clean = body_was_edited(desc)
        self.assertTrue(edited)
        self.assertIn('Edited on GitLab', clean)

    def test_embed_body_hash(self):
        """Embeds body-hash comment at end of description."""
        desc = '## Description\n\nText'
        result = _embed_body_hash(desc)
        self.assertIn('<!-- body-hash:', result)
        self.assertTrue(result.endswith('-->'))
        # Hash should match the clean body
        h = _compute_mr_body_hash('## Description\n\nText')
        self.assertIn(h, result)

    def test_embed_replaces_existing_hash(self):
        """Existing body-hash is replaced, not duplicated."""
        desc = '## Description\n\nText\n<!-- body-hash: aaa111bbb222 -->'
        result = _embed_body_hash(desc)
        self.assertNotIn('aaa111bbb222', result)
        self.assertEqual(result.count('body-hash'), 1)


# ---------------------------------------------------------------------------
#  _extract_checklist / _map_plan_to_body — plan-to-body mapping
# ---------------------------------------------------------------------------

class TestMapPlanToBody(unittest.TestCase):

    def test_maps_visible_sections_to_body(self):
        """Visible plan content replaces MR body.
        Plan with Context + Description -> MR body = Context + Description.
        """
        plan = (
            '<!-- meta\nplan-hash: abc\n-->\n'
            '# [Feature]\n\n'
            '## Context\n\nBackground.\n\n'
            '## Description\n\nWhat it does.\n\n'
            '## Implementation Plan\n\n- [ ] Step 1\n'
        )
        result = _map_plan_to_body('## Description\n\nOld text', plan)
        self.assertIn('## Context', result)
        self.assertIn('Background.', result)
        self.assertIn('## Description', result)
        self.assertIn('What it does.', result)
        self.assertNotIn('Old text', result)

    def test_preserves_checklist(self):
        """## Checklist from MR body appended after visible plan content.
        Plan sections + existing Checklist -> visible + Checklist.
        """
        plan = (
            '# [Feature]\n\n'
            '## Context\n\nBackground.\n'
        )
        existing_body = (
            '## Description\n\nOld text\n\n'
            '## Checklist\n\n'
            '- [ ] Tests pass\n'
            '/label ~bug\n'
        )
        result = _map_plan_to_body(existing_body, plan)
        self.assertIn('## Context', result)
        self.assertIn('## Checklist', result)
        self.assertIn('- [ ] Tests pass', result)
        self.assertIn('/label ~bug', result)

    def test_empty_plan_keeps_existing_body(self):
        """No visible plan content -> keep existing MR body unchanged."""
        plan = (
            '<!-- meta\nplan-hash: abc\n-->\n'
            '# [Feature]\n\n'
        )
        existing = '## Description\n\nExisting body'
        result = _map_plan_to_body(existing, plan)
        self.assertEqual(result, existing)

    def test_no_checklist_in_mr(self):
        """MR body without Checklist -> just visible plan content."""
        plan = (
            '# [Feature]\n\n'
            '## Description\n\nNew description.\n'
        )
        result = _map_plan_to_body('## Description\n\nOld text', plan)
        self.assertIn('New description.', result)
        self.assertNotIn('Checklist', result)

    def test_extract_checklist_captures_section(self):
        """_extract_checklist grabs ## Checklist and everything after.
        '## Description\\n...\\n## Checklist\\n- [ ] Tests' -> '## Checklist...'.
        """
        body = (
            '## Description\n\nText\n\n'
            '## Checklist\n\n'
            '- [ ] Tests pass\n'
            '- [x] Reviewed\n'
            '/label ~bug\n'
            '/assign @dev\n'
        )
        checklist = _extract_checklist(body)
        self.assertIn('## Checklist', checklist)
        self.assertIn('- [ ] Tests pass', checklist)
        self.assertIn('/label ~bug', checklist)
        self.assertNotIn('## Description', checklist)

    def test_extract_checklist_empty_when_none(self):
        """No ## Checklist section -> empty string."""
        body = '## Description\n\nJust text'
        self.assertEqual(_extract_checklist(body), '')


# ---------------------------------------------------------------------------
#  update_mr — replaces PLAN.md section in an existing MR
# ---------------------------------------------------------------------------

@patch('git_hooks_impl.entry_points.sync_mr._save_mr_description')
@patch('git_hooks_impl.entry_points.sync_mr._update_local_plan_hash')
class TestUpdateMr(unittest.IsolatedAsyncioTestCase):
    """Tests for update_mr() — replaces PLAN.md section in an existing MR.

    update_mr() calls get_project_path() (from git_hooks_impl.glab) then
    glab_api_write() for the PUT.  We mock get_project_path to avoid
    the git subprocess call, and glab_api_write to avoid glab CLI.

    _update_local_plan_hash is patched at class level to prevent tests from
    re-embedding plan-hash in the real .ai/PLAN.md (tested separately in
    TestUpdateLocalPlanHash).
    _save_mr_description is patched at class level to prevent tests from
    writing to .ai/cache/<branch>/last_mr_description.md.
    """

    def _desc_from_api_call(self, mock_write):
        """Extract the description sent via glab_api_write (body_dict arg)."""
        body_dict = mock_write.call_args.args[1]
        return body_dict['description']

    @patch('git_hooks_impl.entry_points.sync_mr.get_project_path', return_value='group/productname/reponame')
    @patch('git_hooks_impl.entry_points.sync_mr.get_project_path', return_value='group/productname/reponame')
    @patch('git_hooks_impl.entry_points.sync_mr.glab_api_write', new_callable=AsyncMock)
    async def test_replaces_existing_plan_footer(self, mock_write, mock_proj, _mock_hash, _mock_save_desc):
        """Second push -> replaces the old plan-meta footer.
        Plan with ## Description -> body gets plan's visible content.
        """
        mock_write.return_value = (0, {}, '')
        old_desc = (
            '## Description\n\nSome text'
            '\n\n<!-- plan-meta\nplan-hash: aaa\nbody-hash: aaa\n-->'
        )
        plan = '# [Feature]\n\n## Description\n\nNew from plan\n'
        await update_mr(42, old_desc, plan)

        # Verify glab_api_write was called with PUT method
        mock_write.assert_called_once()
        kwargs = mock_write.call_args.kwargs
        self.assertEqual(kwargs.get('method'), 'PUT')

        # Verify the new description has plan's visible content and one footer
        new_desc = self._desc_from_api_call(mock_write)
        self.assertIn('New from plan', new_desc)
        self.assertIn('## Description', new_desc)
        self.assertEqual(new_desc.count('<!-- plan-meta'), 1)

    @patch('git_hooks_impl.entry_points.sync_mr.get_project_path', return_value='group/productname/reponame')
    @patch('git_hooks_impl.entry_points.sync_mr.get_project_path', return_value='group/productname/reponame')
    @patch('git_hooks_impl.entry_points.sync_mr.glab_api_write', new_callable=AsyncMock)
    async def test_appends_footer_when_none_exists(self, mock_write, mock_proj, _mock_hash, _mock_save_desc):
        """MR created manually without a plan footer -> plan visible content + footer.
        Body not edited (no hash) -> Python mapping replaces body with plan content.
        """
        mock_write.return_value = (0, {}, '')
        old_desc = '## Description\n\nManually written MR'
        plan = '# [Feature]\n\n## Description\n\nFrom plan\n'
        await update_mr(99, old_desc, plan)

        new_desc = self._desc_from_api_call(mock_write)
        self.assertIn('From plan', new_desc)
        footer_meta = extract_footer_meta(new_desc)
        self.assertIsNotNone(footer_meta)
        self.assertEqual(footer_meta.get('title'), '[Feature]')

    @patch('git_hooks_impl.entry_points.sync_mr.get_project_path', return_value='group/productname/reponame')
    @patch('git_hooks_impl.entry_points.sync_mr.get_project_path', return_value='group/productname/reponame')
    @patch('git_hooks_impl.entry_points.sync_mr.glab_api_write', new_callable=AsyncMock)
    async def test_replaces_plan_with_backslash_paths(self, mock_write, mock_proj, _mock_hash, _mock_save_desc):
        """PLAN.md with Windows paths (backslashes) must not break re.sub.
        '.env\\load.ps1' and 'C:\\Users\\...' contain backslashes that are
        regex escape chars — the code escapes them before re.sub.
        """
        mock_write.return_value = (0, {}, '')
        plan_with_paths = (
            '## Architecture\n\n'
            '```\n'
            r'.env\load.ps1' '\n'
            r'C:\Users\dev\AppData\Local\Programs\glab' '\n'
            '```'
        )
        old_desc = (
            '## Description\n\nText'
            '\n\n<!-- plan-meta\nplan-hash: aaa\nbody-hash: aaa\n-->'
        )
        await update_mr(55, old_desc, plan_with_paths)

        new_desc = self._desc_from_api_call(mock_write)
        self.assertIn(r'.env\load.ps1', new_desc)
        self.assertIn(r'C:\Users\dev\AppData\Local\Programs\glab', new_desc)
        # Exactly one plan-meta footer
        self.assertEqual(new_desc.count('<!-- plan-meta'), 1)

    @patch('git_hooks_impl.entry_points.sync_mr.get_project_path', return_value='group/productname/reponame')
    @patch('git_hooks_impl.entry_points.sync_mr.get_project_path', return_value='group/productname/reponame')
    @patch('git_hooks_impl.entry_points.sync_mr.glab_api_write', new_callable=AsyncMock)
    async def test_logs_error_on_glab_failure(self, mock_write, mock_proj, _mock_hash, _mock_save_desc):
        """glab_api_write PUT fails -> error is logged, no exception raised.
        glab_api_write returns rc=1 with 'connection refused' -> err() is called,
        but no exception propagates (push must not be blocked).
        """
        mock_write.return_value = (1, None, 'connection refused')
        await update_mr(50, '## Description\n\nText', 'plan content')
        mock_write.assert_called_once()


if __name__ == '__main__':
    unittest.main(verbosity=2)
