#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for claude/hooks/resume_after_compact.py."""

import os
import tempfile
import unittest

from claude.hooks.precompact import _sanitize_branch as _precompact_sanitize_branch
from claude.hooks.resume_after_compact import _parse_state, _sanitize_branch


class TestParseState(unittest.TestCase):

    def test_parses_full_state_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'session_state.md')
            with open(path, 'w', encoding='utf-8') as f:
                f.write(
                    'Role: refactorer\n'
                    'Workflow: convergence\n'
                    'Phase: 4\n'
                    'Step: 4.2\n'
                    'Note: [Orchestration: refactorer / convergence, state kept]\n'
                )
            fields = _parse_state(path)
            self.assertEqual(fields['role'], 'refactorer')
            self.assertEqual(fields['workflow'], 'convergence')
            self.assertEqual(fields['phase'], '4')
            self.assertEqual(fields['step'], '4.2')

    def test_parses_state_without_step(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'session_state.md')
            with open(path, 'w', encoding='utf-8') as f:
                f.write('Role: gitter\nWorkflow: precommit\nPhase: 3\n')
            fields = _parse_state(path)
            self.assertNotIn('step', fields)

    def test_missing_required_field_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'session_state.md')
            with open(path, 'w', encoding='utf-8') as f:
                f.write('Role: gitter\n')
            self.assertIsNone(_parse_state(path))

    def test_missing_file_returns_none(self):
        self.assertIsNone(_parse_state('/no/such/session_state.md'))


class TestSanitizeBranch(unittest.TestCase):

    def test_matches_precompact_sanitization(self):
        # Must match claude.hooks.precompact._sanitize_branch exactly, or
        # the write and read sides look in different directories.
        for branch in ('feature/foo-bar', 'main', 'a/b/c-d.e', ''):
            self.assertEqual(_sanitize_branch(branch), _precompact_sanitize_branch(branch))


if __name__ == '__main__':
    unittest.main()
