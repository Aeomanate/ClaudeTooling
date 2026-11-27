#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for claude/hooks/precompact.py."""

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from claude.hooks.precompact import (
    _sanitize_branch,
    find_last_status_line,
    main,
    write_session_state,
)


def _write_transcript(path, lines):
    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(line + '\n' for line in lines)


class TestFindLastStatusLine(unittest.TestCase):

    def test_no_status_line_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'transcript.jsonl')
            _write_transcript(path, [
                '{"message": {"content": [{"type": "text", "text": "hello"}]}}',
            ])
            self.assertIsNone(find_last_status_line(path))

    def test_finds_status_line_with_phase_and_step(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'transcript.jsonl')
            _write_transcript(path, [
                '{"message": {"content": [{"type": "text", "text": '
                '"[Orchestration: refactorer / convergence \\u2014 '
                'Phase 4 Step 4.2, state kept]"}]}}',
            ])
            match = find_last_status_line(path)
            self.assertIsNotNone(match)
            self.assertEqual(match.group(1).strip(), 'refactorer')
            self.assertEqual(match.group(2).strip(), 'convergence')
            self.assertEqual(match.group(3), '4')
            self.assertEqual(match.group(4), '4.2')

    def test_finds_status_line_without_step(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'transcript.jsonl')
            _write_transcript(path, [
                '{"message": {"content": [{"type": "text", "text": '
                '"[Orchestration: gitter / precommit \\u2014 Phase 3, state kept]"}]}}',
            ])
            match = find_last_status_line(path)
            self.assertIsNotNone(match)
            self.assertIsNone(match.group(4))

    def test_uses_most_recent_status_line(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'transcript.jsonl')
            _write_transcript(path, [
                '{"message": {"content": [{"type": "text", "text": '
                '"[Orchestration: coder / review \\u2014 Phase 1, state kept]"}]}}',
                '{"message": {"content": [{"type": "text", "text": '
                '"[Orchestration: coder / review \\u2014 Phase 2 Step 2.3, state kept]"}]}}',
            ])
            match = find_last_status_line(path)
            self.assertEqual(match.group(3), '2')

    def test_missing_transcript_file_returns_none(self):
        self.assertIsNone(find_last_status_line('/no/such/transcript.jsonl'))

    def test_malformed_json_lines_are_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'transcript.jsonl')
            _write_transcript(path, [
                'not json at all',
                '{"message": {"content": [{"type": "text", "text": '
                '"[Orchestration: fixer / bugfix \\u2014 Phase 5, state kept]"}]}}',
            ])
            match = find_last_status_line(path)
            self.assertIsNotNone(match)
            self.assertEqual(match.group(1).strip(), 'fixer')


class TestSanitizeBranch(unittest.TestCase):

    def test_matches_git_hooks_impl_convention(self):
        # Must match git_hooks_impl/plan/cache.py's _sanitize_branch_name
        # exactly - this hook can't import that module (see the docstring
        # on _sanitize_branch), so the algorithm is duplicated, not shared.
        self.assertEqual(_sanitize_branch('private/oziuz/ai_plan'), 'private_oziuz_ai_plan')
        self.assertEqual(_sanitize_branch('orchestrator-subagent-rewrite'), 'orchestrator_subagent_rewrite')
        self.assertEqual(_sanitize_branch('Feature/MyBranch'), 'feature_mybranch')

    def test_empty_branch_falls_back(self):
        self.assertEqual(_sanitize_branch(''), 'unknown')


class TestWriteSessionState(unittest.TestCase):

    def test_writes_state_file_under_ai_cache(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, 'transcript.jsonl')
            _write_transcript(path, [
                '{"message": {"content": [{"type": "text", "text": '
                '"[Orchestration: refactorer / convergence \\u2014 '
                'Phase 4 Step 4.2, state kept]"}]}}',
            ])
            match = find_last_status_line(path)
            state_path = write_session_state(root, 'my_branch', match, match.group(0))

            expected = os.path.join(root, '.ai', 'cache', 'my_branch', 'session_state.md')
            self.assertEqual(state_path, expected)
            self.assertTrue(os.path.isfile(expected))

            with open(expected, encoding='utf-8') as f:
                content = f.read()
            self.assertIn('Role: refactorer', content)
            self.assertIn('Workflow: convergence', content)
            self.assertIn('Phase: 4', content)
            self.assertIn('Step: 4.2', content)

    def test_omits_step_line_when_no_step_captured(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, 'transcript.jsonl')
            _write_transcript(path, [
                '{"message": {"content": [{"type": "text", "text": '
                '"[Orchestration: gitter / precommit \\u2014 Phase 3, state kept]"}]}}',
            ])
            match = find_last_status_line(path)
            state_path = write_session_state(root, 'my_branch', match, match.group(0))
            with open(state_path, encoding='utf-8') as f:
                content = f.read()
            self.assertNotIn('Step:', content)


class TestMain(unittest.TestCase):
    """main()'s direct dependencies are stdin, os.path.isdir, and _git."""

    def _stdin(self, transcript_path):
        return json.dumps({'transcript_path': transcript_path})

    @patch('claude.hooks.precompact._git')
    @patch('claude.hooks.precompact.os.path.isdir', return_value=True)
    def test_skips_write_on_default_branch(self, mock_isdir, mock_git):
        with tempfile.TemporaryDirectory() as root:
            transcript = os.path.join(root, 't.jsonl')
            _write_transcript(transcript, [
                '{"message": {"content": [{"type": "text", "text": '
                '"[Orchestration: gitter / precommit \\u2014 Phase 3, state kept]"}]}}',
            ])
            with patch('json.load', return_value={'transcript_path': transcript}),                  patch('os.getcwd', return_value=root):
                    def git_side_effect(*args):
                        if args == ('rev-parse', '--abbrev-ref', 'HEAD'):
                            return 'master'
                        return ''
                    mock_git.side_effect = git_side_effect
                    result = main()
            self.assertEqual(result, 0)
            # os.path.isdir itself is patched above (for the ".git" check
            # inside main()); os.path.exists is a different function and
            # sees the real filesystem, so it's the right check here.
            self.assertFalse(os.path.exists(os.path.join(root, '.ai')))

    @patch('claude.hooks.precompact._git')
    @patch('claude.hooks.precompact.os.path.isdir', return_value=True)
    def test_writes_state_on_non_default_branch(self, mock_isdir, mock_git):
        with tempfile.TemporaryDirectory() as root:
            transcript = os.path.join(root, 't.jsonl')
            _write_transcript(transcript, [
                '{"message": {"content": [{"type": "text", "text": '
                '"[Orchestration: gitter / precommit \\u2014 Phase 3, state kept]"}]}}',
            ])
            with patch('json.load', return_value={'transcript_path': transcript}),                  patch('os.getcwd', return_value=root):
                    def git_side_effect(*args):
                        if args == ('rev-parse', '--abbrev-ref', 'HEAD'):
                            return 'feature-branch'
                        if args == ('symbolic-ref', '--short', 'refs/remotes/origin/HEAD'):
                            return 'origin/master'
                        return ''
                    mock_git.side_effect = git_side_effect
                    result = main()
            self.assertEqual(result, 0)
            expected = os.path.join(root, '.ai', 'cache', 'featurebranch', 'session_state.md')
            self.assertTrue(os.path.isfile(expected))


if __name__ == '__main__':
    unittest.main()
