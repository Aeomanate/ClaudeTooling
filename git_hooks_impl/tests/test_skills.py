#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for setup.skills.

_link_flat_directory and _link_directory_recursive are mocked — no real symlinks created.
prompt_yn and banner print functions are always mocked — no interactive prompts in tests.
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from setup.skills import (
    PruneStatError,
    _link_claude_tree,
    _prune_stale_targets,
    cmd_setup_user_global,
)

# ---------------------------------------------------------------------------
#  Module-level silencing
# ---------------------------------------------------------------------------

_log_patchers = []

def setUpModule():
    for t in (
        'setup.skills.prompt_yn',
        'setup.skills._print_preflight_warning',
        'setup.skills._print_merge_instruction',
        'builtins.print',
    ):
        p = patch(t)
        p.start()
        _log_patchers.append(p)

def tearDownModule():
    for p in _log_patchers:
        p.stop()
    _log_patchers.clear()


# ===========================================================================
#  cmd_setup_user_global
# ===========================================================================

class TestSetupUserGlobal(unittest.TestCase):
    """cmd_setup_user_global: checks for claude/ dir, prompts, links."""

    def test_returns_1_when_claude_src_missing(self):
        """claude/ source tree absent -> returns 1, no linking."""
        with tempfile.TemporaryDirectory() as tmp:
            result = cmd_setup_user_global(ai_tooling_src=tmp)
        self.assertEqual(result, 1)

    def test_aborts_on_no(self):
        """User declines confirmation -> returns 1, _link_claude_tree not called."""
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, 'claude'))
            with patch('setup.skills.prompt_yn', return_value=False), \
                 patch('setup.skills._link_claude_tree') as mock_link:
                result = cmd_setup_user_global(ai_tooling_src=tmp)
        self.assertEqual(result, 1)
        mock_link.assert_not_called()

    def test_calls_link_claude_tree_on_confirmation(self):
        """User confirms -> _link_claude_tree called once, returns 0."""
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, 'claude'))
            with patch('setup.skills.prompt_yn', return_value=True), \
                 patch('setup.skills._link_claude_tree') as mock_link, \
                 patch('setup.skills._prune_stale_targets', return_value=([], [])), \
                 patch('setup.skills._update_claude_settings_env'):
                result = cmd_setup_user_global(ai_tooling_src=tmp)
        self.assertEqual(result, 0)
        mock_link.assert_called_once()

    def test_link_claude_tree_receives_correct_paths(self):
        """_link_claude_tree called with (claude_src, user_claude) where claude_src = ai_tooling/claude."""
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, 'claude'))
            with patch('setup.skills.prompt_yn', return_value=True), \
                 patch('setup.skills._link_claude_tree') as mock_link, \
                 patch('setup.skills._prune_stale_targets', return_value=([], [])), \
                 patch('setup.skills._update_claude_settings_env'):
                cmd_setup_user_global(ai_tooling_src=tmp)
        args = mock_link.call_args[0]
        self.assertTrue(args[0].endswith('claude') or 'claude' in args[0])

    def test_prune_stat_error_warns_and_skips_cleanup(self):
        """_prune_stale_targets raising PruneStatError -> stderr warning, cleanup skipped, still returns 0."""
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, 'claude'))
            with patch('setup.skills.prompt_yn', return_value=True) as mock_prompt, \
                 patch('setup.skills._link_claude_tree'), \
                 patch('setup.skills._prune_stale_targets',
                       side_effect=PruneStatError('cannot stat target file')), \
                 patch('setup.skills._update_claude_settings_env'), \
                 patch('builtins.print') as mock_print:
                result = cmd_setup_user_global(ai_tooling_src=tmp)
        self.assertEqual(result, 0)
        mock_prompt.assert_called_once()
        stderr_calls = [
            c for c in mock_print.call_args_list
            if c.kwargs.get('file') is sys.stderr
        ]
        self.assertTrue(any('cannot stat target file' in str(c.args) for c in stderr_calls))


# ===========================================================================
#  _link_claude_tree — mocked linking
# ===========================================================================

class TestLinkClaudeTree(unittest.TestCase):
    """_link_claude_tree: links agents/, skills/, hooks/ subdirs."""

    def test_calls_link_flat_directory_for_agents(self):
        """agents/ source dir -> _link_flat_directory called."""
        with tempfile.TemporaryDirectory() as tmp:
            claude_src = os.path.join(tmp, 'claude_src')
            user_claude = os.path.join(tmp, 'user_claude')
            os.makedirs(os.path.join(claude_src, 'agents'))
            with patch('setup.skills._link_flat_directory') as mock_flat, \
                 patch('setup.skills._link_directory_recursive') as mock_rec:
                mock_flat.return_value = (0, 0)
                mock_rec.return_value = (0, 0)
                _link_claude_tree(claude_src, user_claude)
        calls = [str(c) for c in mock_flat.call_args_list]
        self.assertTrue(any('agents' in c for c in calls))

    def test_calls_link_directory_recursive_for_skills(self):
        """skills/ source dir -> _link_directory_recursive called."""
        with tempfile.TemporaryDirectory() as tmp:
            claude_src = os.path.join(tmp, 'claude_src')
            user_claude = os.path.join(tmp, 'user_claude')
            os.makedirs(os.path.join(claude_src, 'skills'))
            with patch('setup.skills._link_flat_directory') as mock_flat, \
                 patch('setup.skills._link_directory_recursive') as mock_rec:
                mock_flat.return_value = (0, 0)
                mock_rec.return_value = (0, 0)
                _link_claude_tree(claude_src, user_claude)
        calls = [str(c) for c in mock_rec.call_args_list]
        self.assertTrue(any('skills' in c for c in calls))

    def test_skips_absent_subdirs(self):
        """Source dir with no agents/skills/hooks subdirs -> no calls."""
        with tempfile.TemporaryDirectory() as tmp:
            claude_src = os.path.join(tmp, 'empty_src')
            user_claude = os.path.join(tmp, 'user_claude')
            os.makedirs(claude_src)
            with patch('setup.skills._link_flat_directory') as mock_flat, \
                 patch('setup.skills._link_directory_recursive') as mock_rec:
                _link_claude_tree(claude_src, user_claude)
        mock_flat.assert_not_called()
        mock_rec.assert_not_called()


# ===========================================================================
#  _prune_stale_targets — real files, real inodes, real tempdir
# ===========================================================================

class TestPruneStaleTargets(unittest.TestCase):
    """_prune_stale_targets: three-zone stale artifact detection."""

    def _make_linked(self, src_path, dst_path):
        """Create src_path and hard-link it to dst_path."""
        os.makedirs(os.path.dirname(src_path), exist_ok=True)
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        with open(src_path, 'w') as f:
            f.write('content')
        os.link(src_path, dst_path)

    def _make_unlinked(self, dst_path, content='user content'):
        """Create dst_path with no hard-link relationship to any source file."""
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        with open(dst_path, 'w') as f:
            f.write(content)

    def test_orphan_agent_file_caught(self):
        """agents/ orphan file (orchestrator- prefix, inode not in source) is returned."""
        with tempfile.TemporaryDirectory() as tmp:
            claude_src = os.path.join(tmp, 'src', 'claude')
            user_claude = os.path.join(tmp, 'dst')
            os.makedirs(os.path.join(claude_src, 'agents'))
            os.makedirs(os.path.join(user_claude, 'agents'))
            # Orphan in target — inode not in source agents/
            self._make_unlinked(os.path.join(user_claude, 'agents', 'orchestrator-old.md'))
            files, dirs = _prune_stale_targets(claude_src, user_claude)
        self.assertEqual(len(files), 1)
        self.assertIn('orchestrator-old.md', files[0][0])
        self.assertEqual(files[0][1], 'orchestrator-prefixed file in agents/, no live source inode match')
        self.assertEqual(dirs, [])

    def test_user_agent_file_not_caught(self):
        """agents/ file without orchestrator- prefix is never flagged."""
        with tempfile.TemporaryDirectory() as tmp:
            claude_src = os.path.join(tmp, 'src', 'claude')
            user_claude = os.path.join(tmp, 'dst')
            os.makedirs(os.path.join(claude_src, 'agents'))
            os.makedirs(os.path.join(user_claude, 'agents'))
            self._make_unlinked(os.path.join(user_claude, 'agents', 'my-custom-agent.md'))
            files, dirs = _prune_stale_targets(claude_src, user_claude)
        self.assertEqual(files, [])
        self.assertEqual(dirs, [])

    def test_linked_agent_file_not_caught(self):
        """agents/ file with matching source inode is NOT flagged even with prefix."""
        with tempfile.TemporaryDirectory() as tmp:
            claude_src = os.path.join(tmp, 'src', 'claude')
            user_claude = os.path.join(tmp, 'dst')
            src_file = os.path.join(claude_src, 'agents', 'orchestrator-active.md')
            dst_file = os.path.join(user_claude, 'agents', 'orchestrator-active.md')
            self._make_linked(src_file, dst_file)
            files, dirs = _prune_stale_targets(claude_src, user_claude)
        self.assertEqual(files, [])
        self.assertEqual(dirs, [])

    def test_orphan_hook_file_caught(self):
        """hooks/ orphan file (orchestrator- prefix, inode not in source) is returned."""
        with tempfile.TemporaryDirectory() as tmp:
            claude_src = os.path.join(tmp, 'src', 'claude')
            user_claude = os.path.join(tmp, 'dst')
            os.makedirs(os.path.join(claude_src, 'hooks'))
            os.makedirs(os.path.join(user_claude, 'hooks'))
            self._make_unlinked(os.path.join(user_claude, 'hooks', 'orchestrator-old-hook.sh'))
            files, dirs = _prune_stale_targets(claude_src, user_claude)
        self.assertEqual(len(files), 1)
        self.assertIn('orchestrator-old-hook.sh', files[0][0])
        self.assertEqual(files[0][1], 'orchestrator-prefixed file in hooks/, no live source inode match')
        self.assertEqual(dirs, [])

    def test_orphan_skills_dir_caught(self):
        """skills/ subdir absent from source and containing only ai_tooling files is flagged."""
        with tempfile.TemporaryDirectory() as tmp:
            claude_src = os.path.join(tmp, 'src', 'claude')
            user_claude = os.path.join(tmp, 'dst')
            # Source skills has only 'orchestrator/active/'
            src_active = os.path.join(claude_src, 'skills', 'orchestrator', 'active')
            dst_active = os.path.join(user_claude, 'skills', 'orchestrator', 'active')
            src_file = os.path.join(src_active, 'rules.md')
            dst_file = os.path.join(dst_active, 'rules.md')
            self._make_linked(src_file, dst_file)
            # Target also has an orphan subdir 'orchestrator/stale/' not in source
            dst_stale = os.path.join(user_claude, 'skills', 'orchestrator', 'stale')
            stale_file = os.path.join(dst_stale, 'old-rules.md')
            # stale_file must have inode in source for dir to be deletable
            src_stale_file = os.path.join(claude_src, 'skills', 'orchestrator', 'stale-old', 'old-rules.md')
            self._make_linked(src_stale_file, stale_file)
            files, dirs = _prune_stale_targets(claude_src, user_claude)
        self.assertEqual(files, [])
        self.assertEqual(len(dirs), 1)
        self.assertTrue(dirs[0][0].endswith('stale') or 'stale' in dirs[0][0])
        self.assertEqual(dirs[0][1], 'orphan subdirectory, no source counterpart')

    def test_skills_dir_with_user_file_not_caught(self):
        """skills/ orphan subdir containing a user file (inode not in source) is NOT flagged."""
        with tempfile.TemporaryDirectory() as tmp:
            claude_src = os.path.join(tmp, 'src', 'claude')
            user_claude = os.path.join(tmp, 'dst')
            os.makedirs(os.path.join(claude_src, 'skills'))
            # Target has a subdir not in source, but it contains a user file
            dst_stale = os.path.join(user_claude, 'skills', 'orphan-dir')
            self._make_unlinked(os.path.join(dst_stale, 'user-notes.md'))
            files, dirs = _prune_stale_targets(claude_src, user_claude)
        self.assertEqual(files, [])
        self.assertEqual(dirs, [])

    def test_empty_zones_return_empty(self):
        """All three source dirs absent -> returns ([], [])."""
        with tempfile.TemporaryDirectory() as tmp:
            claude_src = os.path.join(tmp, 'src', 'claude')
            user_claude = os.path.join(tmp, 'dst')
            os.makedirs(claude_src)
            os.makedirs(user_claude)
            files, dirs = _prune_stale_targets(claude_src, user_claude)
        self.assertEqual(files, [])
        self.assertEqual(dirs, [])

    def test_prune_called_after_link_in_cmd_setup(self):
        """cmd_setup_user_global calls _prune_stale_targets after _link_claude_tree."""
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, 'claude'))
            call_order = []
            with patch('setup.skills.prompt_yn', return_value=True), \
                 patch('setup.skills._link_claude_tree', side_effect=lambda *a: call_order.append('link')), \
                 patch('setup.skills._prune_stale_targets', return_value=([], [])) as mock_prune, \
                 patch('setup.skills._update_claude_settings_env'):
                mock_prune.side_effect = lambda *a: call_order.append('prune') or ([], [])
                cmd_setup_user_global(ai_tooling_src=tmp)
        self.assertEqual(call_order, ['link', 'prune'])


if __name__ == '__main__':
    unittest.main()
