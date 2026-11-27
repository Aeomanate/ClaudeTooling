#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for hooks/sync_mr.py — read_plan() (reads .ai/PLAN.md from disk)
and cmd_sync_mr(), the full pre-push/`mr sync` hook orchestrator: branch
detection, glab discovery, MR creation vs update, the push-if-needed logic
(pushing the branch before creating an MR only from the `mr sync` CLI path,
never from the pre-push hook path), and the various early-exit/skip paths.

Run:  python -m unittest discover -s .git-hooks/hooks/tests -t .git-hooks -p "test_sync_mr_flow.py" -v
"""

import json
import os
import tempfile
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
    # plan_parser uses dbg() for discussion parsing
    patch('git_hooks_impl.plan.parser.dbg'),
    # plan_cache, plan_merge — called by sync_mr functions
    patch('git_hooks_impl.plan.cache.log'),
    patch('git_hooks_impl.plan.cache.warn'),
    patch('git_hooks_impl.plan.cache.dbg'),
    patch('git_hooks_impl.plan.cache.ok'),
    patch('git_hooks_impl.plan.merge.log'),
    patch('git_hooks_impl.plan.merge.warn'),
    patch('git_hooks_impl.plan.merge.dbg'),
    patch('git_hooks_impl.entry_points.extract_plan.log'),
    patch('git_hooks_impl.entry_points.extract_plan.warn'),
    patch('git_hooks_impl.entry_points.extract_plan.err'),
    patch('git_hooks_impl.entry_points.extract_plan.dbg'),
    patch('git_hooks_impl.entry_points.extract_plan.ok'),
    patch('git_hooks_impl.utils.dbg'),
    # first_push.create_mr is called by sync_mr — silence its log/dbg/err calls
    patch('git_hooks_impl.first_push.log'),
    patch('git_hooks_impl.first_push.dbg'),
    patch('git_hooks_impl.first_push.err'),
    # glab.get_project_path warns on run_async failure
    patch('git_hooks_impl.glab.warn'),
]


def setUpModule():
    for p in _log_patchers:
        p.start()


def tearDownModule():
    for p in _log_patchers:
        p.stop()

import shutil

from git_hooks_impl.branch_utils import read_plan
from git_hooks_impl.entry_points.sync_mr import cmd_sync_mr
from git_hooks_impl.logger import config
from git_hooks_impl.plan.parser import canonical_plan

# ---------------------------------------------------------------------------
#  read_plan — reads .ai/PLAN.md from disk
# ---------------------------------------------------------------------------

class TestReadPlan(unittest.TestCase):

    @patch('git_hooks_impl.branch_utils.os.path.isfile', return_value=False)
    def test_returns_empty_when_file_missing(self, mock_isfile):
        """No .ai/PLAN.md on disk -> empty string, MR sync uses defaults."""
        self.assertEqual(read_plan(), '')

    @patch('builtins.open', unittest.mock.mock_open(read_data='# Plan\n- Step 1'))
    @patch('git_hooks_impl.branch_utils.os.path.isfile', return_value=True)
    def test_returns_file_content(self, mock_isfile):
        """Existing PLAN.md -> full content returned for MR embedding."""
        content = read_plan()
        self.assertIn('# Plan', content)
        self.assertIn('- Step 1', content)


# ---------------------------------------------------------------------------
#  cmd_sync_mr — full hook orchestration (mocked subprocess)
# ---------------------------------------------------------------------------

class TestSyncMrFlow(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._cache_patcher = patch(
            'git_hooks_impl.plan.cache._CACHE_DIR',
            os.path.join(self.tmp, 'cache'))
        self._cache_patcher.start()
        # _is_delete_push reads sys.stdin via os.read — mock to avoid I/O
        self._delete_push_patcher = patch(
            'git_hooks_impl.entry_points.sync_mr._is_delete_push', return_value=False)
        self._delete_push_patcher.start()
        # _save_cache reads PLAN_FILE from disk — mock to avoid side effects
        self._save_cache_patcher = patch('git_hooks_impl.entry_points.sync_mr._save_cache')
        self._save_cache_patcher.start()
        # cmd_sync_mr() canonicalizes the local plan and writes it back to
        # PLAN_FILE — redirect to a throwaway path so tests never touch the
        # real .ai/BRANCH_PLAN.md on disk.
        self._plan_file_patcher = patch(
            'git_hooks_impl.entry_points.sync_mr.PLAN_FILE',
            os.path.join(self.tmp, 'BRANCH_PLAN.md'))
        self._plan_file_patcher.start()

    def tearDown(self):
        self._plan_file_patcher.stop()
        self._save_cache_patcher.stop()
        self._delete_push_patcher.stop()
        self._cache_patcher.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    @patch('git_hooks_impl.entry_points.sync_mr.find_tool', return_value='/usr/bin/glab')
    @patch('git_hooks_impl.entry_points.sync_mr.run')
    async def test_skips_master_branch(self, mock_run, mock_which):
        """Pushing to master -> no MR sync."""
        mock_run.return_value = (0, 'master\n', '')
        result = await cmd_sync_mr()
        self.assertEqual(result, 0)
        # Only git rev-parse should have been called
        self.assertEqual(mock_run.call_count, 1)

    @patch('git_hooks_impl.entry_points.sync_mr.find_tool', return_value='/usr/bin/glab')
    @patch('git_hooks_impl.entry_points.sync_mr.run')
    async def test_skips_detached_head(self, mock_run, mock_which):
        """Detached HEAD (rebase, CI) -> no MR sync, never block push."""
        mock_run.return_value = (0, 'HEAD\n', '')
        result = await cmd_sync_mr()
        self.assertEqual(result, 0)

    @patch('git_hooks_impl.entry_points.sync_mr.find_tool', return_value='')
    async def test_skips_when_glab_not_found(self, mock_which):
        """No glab installed -> graceful skip, exit 0 (never block push)."""
        result = await cmd_sync_mr()
        self.assertEqual(result, 0)

    @patch('git_hooks_impl.entry_points.sync_mr.plan_check_dialog', return_value=True)
    @patch('git_hooks_impl.entry_points.sync_mr.create_mr')
    @patch('git_hooks_impl.entry_points.sync_mr.current_user', new_callable=AsyncMock, return_value='dev')
    @patch('git_hooks_impl.entry_points.sync_mr.find_tool', return_value='/usr/bin/glab')
    @patch('git_hooks_impl.entry_points.sync_mr.run')
    async def test_creates_mr_when_none_exists(self, mock_run, mock_which,
                                          mock_user, mock_create, mock_dlg):
        """First push -> glab mr list returns [] -> create_mr() is called."""
        mock_run.side_effect = [
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),   # git rev-parse
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),   # git rev-parse
            (0, '', ''),                             # glab auth status
            (0, '[]', ''),                           # glab mr list -> empty
        ]
        with patch('git_hooks_impl.entry_points.sync_mr.read_plan', return_value='plan text'):
            await cmd_sync_mr()

        mock_create.assert_called_once()
        args = mock_create.call_args.args
        self.assertEqual(args[0], 'productname/fixes/PROJECTNAME-1_fix')  # branch
        self.assertEqual(args[0], 'productname/fixes/PROJECTNAME-1_fix')  # branch
        self.assertEqual(args[1], 'fix')                     # template
        self.assertEqual(args[2], 'PROJECTNAME-1')                  # jira_ticket
        self.assertEqual(args[3], canonical_plan('plan text'))  # plan_content
        self.assertEqual(args[5], 'dev')                     # username

    @patch.object(config, 'command', 'sync')
    @patch('git_hooks_impl.entry_points.sync_mr.plan_check_dialog', return_value=True)
    @patch('git_hooks_impl.entry_points.sync_mr.create_mr')
    @patch('git_hooks_impl.entry_points.sync_mr.current_user', new_callable=AsyncMock, return_value='dev')
    @patch('git_hooks_impl.entry_points.sync_mr.find_tool', return_value='/usr/bin/glab')
    @patch('git_hooks_impl.entry_points.sync_mr.run_async', new_callable=AsyncMock, return_value=(0, '', ''))
    @patch('git_hooks_impl.entry_points.sync_mr.run')
    async def test_cli_sync_pushes_branch_absent_on_remote_before_creating_mr(
            self, mock_run, mock_run_async, mock_which, mock_user, mock_create, mock_dlg):
        """`mr sync` (config.command == 'sync'), branch not on remote -> push then create_mr."""
        mock_run.side_effect = [
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),   # git rev-parse
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),   # git rev-parse
            (0, '[]', ''),                           # glab mr list -> empty
            (0, '', ''),                             # git ls-remote --heads -> empty, not on remote
            (0, '', ''),                             # git push -u origin <branch>
        ]
        with patch('git_hooks_impl.entry_points.sync_mr.read_plan', return_value='plan text'):
            result = await cmd_sync_mr()

        self.assertEqual(result, 0)
        push_calls = [c for c in mock_run.call_args_list if c.args[0][:2] == ['git', 'push']]
        self.assertEqual(len(push_calls), 1)
        mock_create.assert_called_once()

    @patch.object(config, 'command', 'sync')
    @patch('git_hooks_impl.entry_points.sync_mr.plan_check_dialog', return_value=True)
    @patch('git_hooks_impl.entry_points.sync_mr.create_mr')
    @patch('git_hooks_impl.entry_points.sync_mr.current_user', new_callable=AsyncMock, return_value='dev')
    @patch('git_hooks_impl.entry_points.sync_mr.find_tool', return_value='/usr/bin/glab')
    @patch('git_hooks_impl.entry_points.sync_mr.run_async', new_callable=AsyncMock, return_value=(0, '', ''))
    @patch('git_hooks_impl.entry_points.sync_mr.run')
    async def test_cli_sync_skips_push_when_branch_already_on_remote(
            self, mock_run, mock_run_async, mock_which, mock_user, mock_create, mock_dlg):
        """`mr sync`, branch already on remote -> no push, create_mr only."""
        mock_run.side_effect = [
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),                       # git rev-parse
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),                       # git rev-parse
            (0, '[]', ''),                                               # glab mr list -> empty
            (0, 'abc123\trefs/heads/productname/fixes/PROJECTNAME-1_fix\n', ''),  # git ls-remote -> present
            (0, 'abc123\trefs/heads/productname/fixes/PROJECTNAME-1_fix\n', ''),  # git ls-remote -> present
        ]
        with patch('git_hooks_impl.entry_points.sync_mr.read_plan', return_value='plan text'):
            result = await cmd_sync_mr()

        self.assertEqual(result, 0)
        push_calls = [c for c in mock_run.call_args_list if c.args[0][:2] == ['git', 'push']]
        self.assertEqual(len(push_calls), 0)
        mock_create.assert_called_once()

    @patch.object(config, 'command', 'sync-mr')
    @patch('git_hooks_impl.entry_points.sync_mr.plan_check_dialog', return_value=True)
    @patch('git_hooks_impl.entry_points.sync_mr.create_mr')
    @patch('git_hooks_impl.entry_points.sync_mr.current_user', new_callable=AsyncMock, return_value='dev')
    @patch('git_hooks_impl.entry_points.sync_mr.find_tool', return_value='/usr/bin/glab')
    @patch('git_hooks_impl.entry_points.sync_mr.run_async', new_callable=AsyncMock, return_value=(0, '', ''))
    @patch('git_hooks_impl.entry_points.sync_mr.run')
    async def test_hook_path_never_pushes_even_when_branch_absent(
            self, mock_run, mock_run_async, mock_which, mock_user, mock_create, mock_dlg):
        """Pre-push hook (config.command == 'sync-mr') -> never self-pushes, git is already pushing."""
        mock_run.side_effect = [
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),   # git rev-parse
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),   # git rev-parse
            (0, '[]', ''),                           # glab mr list -> empty
        ]
        with patch('git_hooks_impl.entry_points.sync_mr.read_plan', return_value='plan text'):
            result = await cmd_sync_mr()

        self.assertEqual(result, 0)
        push_calls = [c for c in mock_run.call_args_list if c.args[0][:2] == ['git', 'push']]
        self.assertEqual(len(push_calls), 0)
        mock_create.assert_called_once()

    @patch('git_hooks_impl.entry_points.sync_mr.plan_check_dialog', return_value=True)
    @patch('git_hooks_impl.entry_points.sync_mr._save_base', new_callable=AsyncMock)
    @patch('git_hooks_impl.entry_points.sync_mr._post_discussions', new_callable=AsyncMock)
    @patch('git_hooks_impl.entry_points.sync_mr.update_mr', new_callable=AsyncMock)
    @patch('git_hooks_impl.entry_points.sync_mr.current_user', new_callable=AsyncMock, return_value='dev')
    @patch('git_hooks_impl.entry_points.sync_mr.find_tool', return_value='/usr/bin/glab')
    @patch('git_hooks_impl.entry_points.sync_mr.run_async', new_callable=AsyncMock, return_value=(0, '', ''))
    @patch('git_hooks_impl.entry_points.sync_mr.run')
    async def test_updates_mr_when_one_exists(self, mock_run, mock_run_async, mock_which,
                                         mock_user, mock_update, mock_post_disc,
                                         mock_save_base, mock_dlg):
        """Second push -> discussions posted FIRST, then update_mr with enriched content."""
        existing_mrs = json.dumps([{
            'iid': 42,
            'title': 'Existing MR',
            'description': '## Description\n\nOld text',
        }])
        mock_run.side_effect = [
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),    # git rev-parse
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),    # git rev-parse
            (0, existing_mrs, ''),                    # glab mr list -> one open
        ]
        # _post_discussions returns enriched content (with markers/links)
        mock_post_disc.return_value = 'enriched plan'
        with patch('git_hooks_impl.entry_points.sync_mr.read_plan', return_value='updated plan'):
            await cmd_sync_mr()

        # Discussions posted first with the canonicalized local content
        mock_post_disc.assert_called_once_with(42, canonical_plan('updated plan'))
        # update_mr gets the enriched content (with markers) from _post_discussions
        mock_update.assert_called_once_with(
            42,
            '## Description\n\nOld text',
            'enriched plan',
            branch='productname/fixes/PROJECTNAME-1_fix',
            branch='productname/fixes/PROJECTNAME-1_fix',
            force=False,
        )

    @patch('git_hooks_impl.entry_points.sync_mr.update_mr')
    @patch('git_hooks_impl.entry_points.sync_mr.current_user', new_callable=AsyncMock, return_value='dev')
    @patch('git_hooks_impl.entry_points.sync_mr.find_tool', return_value='/usr/bin/glab')
    @patch('git_hooks_impl.entry_points.sync_mr.run')
    async def test_skips_update_when_no_local_plan(self, mock_run, mock_which,
                                              mock_user, mock_update):
        """Existing MR but no local PLAN.md -> leave MR description unchanged."""
        existing_mrs = json.dumps([{
            'iid': 42,
            'title': 'Existing MR',
            'description': '## Description\n\nOld text',
        }])
        mock_run.side_effect = [
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),
            (0, '', ''),
            (0, existing_mrs, ''),
        ]
        with patch('git_hooks_impl.entry_points.sync_mr.read_plan', return_value=''):
            await cmd_sync_mr()

        mock_update.assert_not_called()

    @patch('git_hooks_impl.entry_points.sync_mr.create_mr')
    @patch('git_hooks_impl.entry_points.sync_mr.current_user', new_callable=AsyncMock, return_value='dev')
    @patch('git_hooks_impl.entry_points.sync_mr.find_tool', return_value='/usr/bin/glab')
    @patch('git_hooks_impl.entry_points.sync_mr.run')
    async def test_creates_mr_without_plan_section_when_no_local_plan(self, mock_run,
                                                                 mock_which,
                                                                 mock_user,
                                                                 mock_create):
        """No MR and no local PLAN.md -> create MR with empty plan_section string."""
        mock_run.side_effect = [
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),
            (0, '', ''),
            (0, '[]', ''),
        ]
        with patch('git_hooks_impl.entry_points.sync_mr.read_plan', return_value=''):
            await cmd_sync_mr()

        mock_create.assert_called_once()
        plan_section_arg = mock_create.call_args.args[4]
        self.assertEqual(plan_section_arg, '')

    @patch('git_hooks_impl.entry_points.sync_mr.current_user', new_callable=AsyncMock, return_value='')
    @patch('git_hooks_impl.entry_points.sync_mr.find_tool', return_value='/usr/bin/glab')
    @patch('git_hooks_impl.entry_points.sync_mr.run')
    async def test_never_blocks_push_on_auth_failure(self, mock_run, mock_which, mock_user):
        """Auth failure -> warns but continues, returns 0 (push proceeds)."""
        mock_run.side_effect = [
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),  # git rev-parse
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),  # git rev-parse
            (1, '', 'auth failed'),                 # glab auth status (warn, continue)
            (1, '', 'no MR'),                        # glab mr list
        ]
        with patch('git_hooks_impl.entry_points.sync_mr.read_plan', return_value=''), \
             patch('git_hooks_impl.entry_points.sync_mr.create_mr'):
            result = await cmd_sync_mr()
        self.assertEqual(result, 0)

    @patch('git_hooks_impl.entry_points.sync_mr.plan_check_dialog', return_value=True)
    @patch('git_hooks_impl.entry_points.sync_mr.update_mr', new_callable=AsyncMock)
    @patch('git_hooks_impl.entry_points.sync_mr.create_mr', new_callable=AsyncMock)
    @patch('git_hooks_impl.entry_points.sync_mr.current_user', new_callable=AsyncMock, return_value='dev')
    @patch('git_hooks_impl.entry_points.sync_mr.find_tool', return_value='/usr/bin/glab')
    @patch('git_hooks_impl.entry_points.sync_mr.run_async', new_callable=AsyncMock, return_value=(0, '', ''))
    @patch('git_hooks_impl.entry_points.sync_mr.run')
    async def test_skips_when_multiple_open_mrs(self, mock_run, mock_run_async, mock_which,
                                           mock_user, mock_create, mock_update,
                                           mock_dlg):
        """Multiple open MRs for same branch -> skip, never block push."""
        two_mrs = json.dumps([
            {'iid': 42, 'title': 'MR one', 'description': ''},
            {'iid': 43, 'title': 'MR two', 'description': ''},
        ])
        mock_run.side_effect = [
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),
            (0, two_mrs, ''),
        ]
        with patch('git_hooks_impl.entry_points.sync_mr.read_plan', return_value='plan'):
            result = await cmd_sync_mr()

        self.assertEqual(result, 0)
        mock_create.assert_not_called()
        mock_update.assert_not_called()

    @patch.dict(os.environ, {}, clear=False)
    @patch('git_hooks_impl.entry_points.sync_mr.plan_check_dialog', return_value=False)
    @patch('git_hooks_impl.entry_points.sync_mr.current_user', new_callable=AsyncMock, return_value='dev')
    @patch('git_hooks_impl.entry_points.sync_mr.find_tool', return_value='/usr/bin/glab')
    @patch('git_hooks_impl.entry_points.sync_mr.run')
    async def test_aborts_when_plan_dialog_declined(self, mock_run, mock_which,
                                               mock_user, mock_dlg):
        """User clicks 'Abort' in plan check dialog -> returns 1, no MR work done."""
        mock_run.side_effect = [
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),     # git rev-parse
            (0, 'productname/fixes/PROJECTNAME-1_fix\n', ''),     # git rev-parse
        ]
        with patch('git_hooks_impl.entry_points.sync_mr.read_plan', return_value='plan text'):
            result = await cmd_sync_mr()
        self.assertEqual(result, 1)
        # Only git rev-parse should have been called — no auth check or MR list
        self.assertEqual(mock_run.call_count, 1)

    @patch('git_hooks_impl.entry_points.sync_mr.find_tool', return_value='/usr/bin/glab')
    @patch('git_hooks_impl.entry_points.sync_mr.run')
    async def test_skips_when_branch_is_empty(self, mock_run, mock_which):
        """Git rev-parse returns empty string -> graceful skip."""
        mock_run.return_value = (0, '\n', '')
        result = await cmd_sync_mr()
        self.assertEqual(result, 0)
        self.assertEqual(mock_run.call_count, 1)

    @patch('git_hooks_impl.entry_points.sync_mr.find_tool', return_value='/usr/bin/glab')
    @patch('git_hooks_impl.entry_points.sync_mr.run')
    async def test_skips_main_branch(self, mock_run, mock_which):
        """Pushing to main -> no MR sync (same as master)."""
        mock_run.return_value = (0, 'main\n', '')
        result = await cmd_sync_mr()
        self.assertEqual(result, 0)
        self.assertEqual(mock_run.call_count, 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
