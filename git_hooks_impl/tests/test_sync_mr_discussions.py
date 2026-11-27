#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for hooks/sync_mr.py — building the merge-request discussion
thread URL, posting unposted PLAN.md discussions to GitLab
(_post_discussions), and AI-visible content-change detection used to
skip redundant AI calls.

Run:  python -m unittest discover -s .git-hooks/hooks/tests -t .git-hooks -p "test_sync_mr_discussions.py" -v
"""

import os
import tempfile
import unittest
from unittest.mock import patch

# Silence all logging — tests that verify log calls use their own @patch
_log_patchers = [
    patch('git_hooks_impl.entry_points.sync_mr.log'),
    patch('git_hooks_impl.entry_points.sync_mr.warn'),
    patch('git_hooks_impl.entry_points.sync_mr.err'),
    patch('git_hooks_impl.entry_points.sync_mr.dbg'),
    patch('git_hooks_impl.entry_points.sync_mr.ok'),
    # branch_utils is exercised indirectly via sync_mr — silence its logging too
    patch('git_hooks_impl.branch_utils.log'),
    patch('git_hooks_impl.branch_utils.warn'),
    patch('git_hooks_impl.branch_utils.dbg'),
    # plan_parser uses dbg() for discussion parsing
    patch('git_hooks_impl.plan.parser.dbg'),
]


def setUpModule():
    for p in _log_patchers:
        p.start()


def tearDownModule():
    for p in _log_patchers:
        p.stop()

import shutil

from git_hooks_impl.entry_points.sync_mr import (
    _body_content_changed,
    _build_thread_url,
    _post_discussions,
    update_mr,
)
from git_hooks_impl.plan.parser import embed_meta, embed_plan_hash

# ---------------------------------------------------------------------------
#  Discussion thread posting — 5 tests
# ---------------------------------------------------------------------------


class TestBuildThreadUrl(unittest.TestCase):

    @patch('git_hooks_impl.entry_points.sync_mr.GITLAB_HOST', 'gitlab.companyname.com')
    def test_with_note_id(self):
        """API result with notes[0].id -> URL with #note_ anchor."""
        url = _build_thread_url('group/productname/reponame', 42, {'notes': [{'id': 789}]})
        url = _build_thread_url('group/productname/reponame', 42, {'notes': [{'id': 789}]})
        self.assertEqual(url, 'https://gitlab.companyname.com/group/productname/reponame/-/merge_requests/42#note_789')
        self.assertEqual(url, 'https://gitlab.companyname.com/group/productname/reponame/-/merge_requests/42#note_789')

    @patch('git_hooks_impl.entry_points.sync_mr.GITLAB_HOST', 'gitlab.companyname.com')
    def test_without_notes(self):
        """API result without notes -> URL without anchor."""
        url = _build_thread_url('group/productname/reponame', 42, {'id': 'abc'})
        url = _build_thread_url('group/productname/reponame', 42, {'id': 'abc'})
        self.assertEqual(url, 'https://gitlab.companyname.com/group/productname/reponame/-/merge_requests/42')
        self.assertEqual(url, 'https://gitlab.companyname.com/group/productname/reponame/-/merge_requests/42')

    @patch('git_hooks_impl.entry_points.sync_mr.GITLAB_HOST', 'gitlab.companyname.com')
    def test_empty_notes_list(self):
        """API result with empty notes list -> URL without anchor."""
        url = _build_thread_url('group/productname/reponame', 42, {'notes': []})
        url = _build_thread_url('group/productname/reponame', 42, {'notes': []})
        self.assertEqual(url, 'https://gitlab.companyname.com/group/productname/reponame/-/merge_requests/42')
        self.assertEqual(url, 'https://gitlab.companyname.com/group/productname/reponame/-/merge_requests/42')


class TestPostDiscussions(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.plan_file = os.path.join(self.tmp, 'PLAN.md')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    @patch('git_hooks_impl.entry_points.sync_mr.glab_api_post')
    @patch('git_hooks_impl.entry_points.sync_mr.get_project_path', return_value='group/productname/reponame')
    @patch('git_hooks_impl.entry_points.sync_mr.get_project_path', return_value='group/productname/reponame')
    async def test_posts_and_embeds_url_in_title(self, mock_proj, mock_post):
        """Unposted discussion -> API call + body stripped + URL in title."""
        plan = (
            '# Plan\n\n'
            '## Discussions\n\n'
            '### Submodule support\n\n'
            '> RFC body here\n\n'
            'Hooks are single-repo.\n'
        )
        with open(self.plan_file, 'w') as f:
            f.write(plan)
        mock_post.return_value = {'notes': [{'id': 789}]}

        with patch('git_hooks_impl.entry_points.sync_mr.PLAN_FILE', self.plan_file):
            result = await _post_discussions(42, plan)

        mock_post.assert_called_once()
        # URL should be embedded in the title: ### [Title](url)
        self.assertIn('### [Submodule support]', result)
        self.assertIn('#note_789', result)
        # Original body should be gone
        self.assertNotIn('RFC body here', result)
        self.assertNotIn('single-repo', result)
        # PLAN.md on disk should match
        with open(self.plan_file) as f:
            saved = f.read()
        self.assertIn('#note_789', saved)
        self.assertNotIn('RFC body here', saved)

    @patch('git_hooks_impl.entry_points.sync_mr.glab_api_post')
    @patch('git_hooks_impl.entry_points.sync_mr.get_project_path', return_value='group/productname/reponame')
    @patch('git_hooks_impl.entry_points.sync_mr.get_project_path', return_value='group/productname/reponame')
    async def test_preserves_content_outside_discussions_block(self, mock_proj, mock_post):
        """Content after ## Discussions block (next ## heading) is preserved."""
        plan = (
            '## Discussions\n\n'
            '### Topic A\n\n'
            'Long body for A.\n\n'
            '## Other section\n\nKept intact.\n'
        )
        with open(self.plan_file, 'w') as f:
            f.write(plan)
        mock_post.return_value = {'notes': [{'id': 100}]}

        with patch('git_hooks_impl.entry_points.sync_mr.PLAN_FILE', self.plan_file):
            result = await _post_discussions(42, plan)

        self.assertNotIn('Long body for A', result)
        self.assertIn('Kept intact.', result)

    @patch('git_hooks_impl.entry_points.sync_mr.glab_api_post')
    @patch('git_hooks_impl.entry_points.sync_mr.get_project_path', return_value='group/productname/reponame')
    @patch('git_hooks_impl.entry_points.sync_mr.get_project_path', return_value='group/productname/reponame')
    async def test_no_note_id_falls_back_to_mr_url(self, mock_proj, mock_post):
        """API returns no notes -> link points to MR without #note_ anchor."""
        plan = (
            '## Discussions\n\n'
            '### Topic\n\n'
            'Body.\n'
        )
        with open(self.plan_file, 'w') as f:
            f.write(plan)
        mock_post.return_value = {'id': 'abc'}  # no 'notes' key

        with patch('git_hooks_impl.entry_points.sync_mr.PLAN_FILE', self.plan_file):
            result = await _post_discussions(42, plan)

        self.assertIn('### [Topic]', result)
        self.assertIn('merge_requests/42)', result)
        self.assertNotIn('#note_', result)
        self.assertNotIn('Body.', result)

    @patch('git_hooks_impl.entry_points.sync_mr.glab_api_post')
    @patch('git_hooks_impl.entry_points.sync_mr.get_project_path', return_value='group/productname/reponame')
    @patch('git_hooks_impl.entry_points.sync_mr.get_project_path', return_value='group/productname/reponame')
    async def test_already_posted_discussions_not_reposted(self, mock_proj, mock_post):
        """Posted discussion (URL in title) -> no API call, no changes."""
        plan = (
            '## Discussions\n\n'
            '### [Topic A](https://gitlab.example.com/p/-/merge_requests/42#note_100)\n\n'
            '## Other section\n\nBody.\n'
        )
        with open(self.plan_file, 'w') as f:
            f.write(plan)

        with patch('git_hooks_impl.entry_points.sync_mr.PLAN_FILE', self.plan_file):
            result = await _post_discussions(42, plan)

        mock_post.assert_not_called()
        self.assertEqual(result, plan)


# ---------------------------------------------------------------------------
#  AI content change detection — skip AI when AI-visible plan unchanged
# ---------------------------------------------------------------------------

class TestBodyContentChanged(unittest.IsolatedAsyncioTestCase):

    async def test_changed_when_no_hash(self):
        """No body-hash in content -> changed=True (first push)."""
        self.assertTrue(_body_content_changed('# Plan\n## Steps'))

    async def test_unchanged_when_hash_matches(self):
        """embed_plan_hash() sets body-hash, content not edited -> changed=False."""
        plan = embed_plan_hash('# Plan\n## Steps')
        self.assertFalse(_body_content_changed(plan))

    async def test_changed_when_visible_content_edited(self):
        """body-hash embedded, then visible content modified -> changed=True."""
        plan = embed_plan_hash('# Plan\n## Old steps')
        # Simulate user edit: change visible content, meta block stays
        edited = plan.replace('Old steps', 'New steps with detail')
        self.assertTrue(_body_content_changed(edited))

    async def test_unchanged_ignores_timing(self):
        """Timing-only change doesn't trigger changed.
        embed_plan_hash() -> add timing to meta -> body-hash still matches.
        """
        plan = embed_plan_hash('# Plan\n## Steps')
        with_timing = embed_meta(plan, **{'claude-timing': '35.2'})
        self.assertFalse(_body_content_changed(with_timing))

    async def test_visible_change_uses_python_mapping(self):
        """Body not edited + visible content changed -> Python mapping, glab_api_write called."""
        plan_original = (
            '# Plan\n## Context\nOriginal visible\n'
        )
        plan_stamped = embed_plan_hash(plan_original)
        plan_edited = plan_stamped.replace('Original visible', 'Changed visible content')
        desc = '## Description\n\nText'
        with patch('git_hooks_impl.entry_points.sync_mr.get_project_path', return_value='group/productname/reponame'), \
        with patch('git_hooks_impl.entry_points.sync_mr.get_project_path', return_value='group/productname/reponame'), \
             patch('git_hooks_impl.entry_points.sync_mr.glab_api_write', return_value=(0, {}, '')) as mock_write, \
             patch('git_hooks_impl.entry_points.sync_mr._update_local_plan_hash'), \
             patch('git_hooks_impl.entry_points.sync_mr._save_mr_description'):
            await update_mr(42, desc, plan_edited)
        mock_write.assert_called_once()

    async def test_python_mapping_when_body_not_edited(self):
        """Body not edited -> Python mapping, glab_api_write called."""
        plan = embed_plan_hash('# Plan\n## Context\n\nSame')
        desc = '## Description\n\nText'
        with patch('git_hooks_impl.entry_points.sync_mr.get_project_path', return_value='group/productname/reponame'), \
        with patch('git_hooks_impl.entry_points.sync_mr.get_project_path', return_value='group/productname/reponame'), \
             patch('git_hooks_impl.entry_points.sync_mr.glab_api_write', return_value=(0, {}, '')) as mock_write, \
             patch('git_hooks_impl.entry_points.sync_mr._update_local_plan_hash'), \
             patch('git_hooks_impl.entry_points.sync_mr._save_mr_description'):
            await update_mr(42, desc, plan)
        mock_write.assert_called_once()

    async def test_writes_divergent_artifact_when_body_edited_on_gitlab(self):
        """Body-hash mismatch -> writes .divergent artifact, glab_api_write NOT called."""
        plan = '# Plan\n## Context\nText'
        # Body with mismatched hash -> body_was_edited returns True
        desc = '## Description\n\nEdited on GitLab\n<!-- body-hash: 000000000000 -->'
        with tempfile.TemporaryDirectory() as tmp, \
             patch('git_hooks_impl.entry_points.sync_mr._CACHE_DIR', tmp), \
             patch('git_hooks_impl.entry_points.sync_mr.get_project_path', return_value='group/productname/reponame'), \
             patch('git_hooks_impl.entry_points.sync_mr.get_project_path', return_value='group/productname/reponame'), \
             patch('git_hooks_impl.entry_points.sync_mr.glab_api_write') as mock_write, \
             patch('git_hooks_impl.entry_points.sync_mr._update_local_plan_hash'), \
             patch('git_hooks_impl.entry_points.sync_mr._save_mr_description'):
            await update_mr(42, desc, plan, branch='productname/fixes/PROJECTNAME-1_fix')
            await update_mr(42, desc, plan, branch='productname/fixes/PROJECTNAME-1_fix')
        mock_write.assert_not_called()

    async def test_force_overwrites_edited_body(self):
        """force=True on a body-hash mismatch -> glab_api_write called."""
        plan = embed_plan_hash('# Plan\n## Context\n\nLocal')
        desc = '## Description\n\nEdited on GitLab\n<!-- body-hash: 000000000000 -->'
        with tempfile.TemporaryDirectory() as tmp, \
             patch('git_hooks_impl.entry_points.sync_mr._CACHE_DIR', tmp), \
             patch('git_hooks_impl.entry_points.sync_mr.get_project_path', return_value='group/productname/reponame'), \
             patch('git_hooks_impl.entry_points.sync_mr.get_project_path', return_value='group/productname/reponame'), \
             patch('git_hooks_impl.entry_points.sync_mr.glab_api_write', return_value=(0, {}, '')) as mock_write, \
             patch('git_hooks_impl.entry_points.sync_mr._update_local_plan_hash'), \
             patch('git_hooks_impl.entry_points.sync_mr._save_mr_description'):
            await update_mr(42, desc, plan, branch='productname/fixes/PROJECTNAME-1_fix',
            await update_mr(42, desc, plan, branch='productname/fixes/PROJECTNAME-1_fix',
                            force=True)
        mock_write.assert_called_once()

    async def test_force_still_saves_divergent_artifact(self):
        """force=True preserves the overwritten remote body on disk."""
        plan = embed_plan_hash('# Plan\n## Context\n\nLocal')
        desc = '## Description\n\nEdited on GitLab\n<!-- body-hash: 000000000000 -->'
        with tempfile.TemporaryDirectory() as tmp, \
             patch('git_hooks_impl.entry_points.sync_mr._CACHE_DIR', tmp), \
             patch('git_hooks_impl.entry_points.sync_mr.get_project_path', return_value='group/productname/reponame'), \
             patch('git_hooks_impl.entry_points.sync_mr.get_project_path', return_value='group/productname/reponame'), \
             patch('git_hooks_impl.entry_points.sync_mr.glab_api_write', return_value=(0, {}, '')), \
             patch('git_hooks_impl.entry_points.sync_mr._update_local_plan_hash'), \
             patch('git_hooks_impl.entry_points.sync_mr._save_mr_description'):
            await update_mr(42, desc, plan, branch='productname/fixes/PROJECTNAME-1_fix',
            await update_mr(42, desc, plan, branch='productname/fixes/PROJECTNAME-1_fix',
                            force=True)
            # Assert inside the context — the temp dir is removed on exit.
            saved = os.path.join(tmp, 'productname_fixes_productname1_fix',
            saved = os.path.join(tmp, 'productname_fixes_productname1_fix',
                                 'last_mr_description.divergent')
            self.assertTrue(os.path.isfile(saved))
            with open(saved, encoding='utf-8') as handle:
                self.assertIn('Edited on GitLab', handle.read())


if __name__ == '__main__':
    unittest.main(verbosity=2)
