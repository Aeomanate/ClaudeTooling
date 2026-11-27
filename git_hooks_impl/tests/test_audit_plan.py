#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for git_hooks_impl.entry_points.commands.audit_plan.

run()'s only direct dependency is project_root(), mocked at the audit_plan
import location per the Main Mock Rule. The three checks it assembles
(audit_sections, check_plan_paths, check_stale_refs) each have their own
test file exercising their pure functions directly - these tests confirm
audit_plan wires them together into one report and one exit code, not
their individual logic again.
"""

import contextlib
import io
import os
import tempfile
import unittest
from unittest.mock import patch

from git_hooks_impl.entry_points.commands import audit_plan


def _write_plan(root, text):
    ai_dir = os.path.join(root, '.ai')
    os.makedirs(ai_dir, exist_ok=True)
    with open(os.path.join(ai_dir, 'BRANCH_PLAN.md'), 'w', encoding='utf-8') as f:
        f.write(text)


class TestRun(unittest.TestCase):

    def _run_and_capture(self, argv=None):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = audit_plan.run(argv or [])
        return result, buf.getvalue()

    def test_missing_plan_returns_1(self):
        with tempfile.TemporaryDirectory() as root, patch(
            'git_hooks_impl.entry_points.commands.audit_plan.project_root',
            return_value=root,
        ):
            result, output = self._run_and_capture()
        self.assertEqual(result, 1)
        self.assertIn('not found', output)

    def test_clean_plan_returns_0(self):
        with tempfile.TemporaryDirectory() as root:
            _write_plan(root, '## Section One\n\ncontent here\n')
            with patch(
                'git_hooks_impl.entry_points.commands.audit_plan.project_root',
                return_value=root,
            ):
                result, output = self._run_and_capture()
        self.assertEqual(result, 0)
        self.assertIn('ALL CLEAN', output)

    def test_empty_section_is_reported_and_fails(self):
        with tempfile.TemporaryDirectory() as root:
            _write_plan(root, '## Section One\n\n## Section Two\n\ncontent\n')
            with patch(
                'git_hooks_impl.entry_points.commands.audit_plan.project_root',
                return_value=root,
            ):
                result, output = self._run_and_capture()
        self.assertEqual(result, 1)
        self.assertIn('EMPTY', output)

    def test_missing_path_is_reported_and_fails(self):
        with tempfile.TemporaryDirectory() as root:
            _write_plan(root, '## Section\n\nSee `tools/does_not_exist.py` for details.\n')
            with patch(
                'git_hooks_impl.entry_points.commands.audit_plan.project_root',
                return_value=root,
            ):
                result, output = self._run_and_capture()
        self.assertEqual(result, 1)
        self.assertIn('MISSING: tools/does_not_exist.py', output)

    def test_bare_link_text_is_reported_and_fails(self):
        with tempfile.TemporaryDirectory() as root:
            _write_plan(root, '## Section\n\nSee [somefile.md](somefile.md) for details.\n')
            with patch(
                'git_hooks_impl.entry_points.commands.audit_plan.project_root',
                return_value=root,
            ):
                result, output = self._run_and_capture()
        self.assertEqual(result, 1)
        self.assertIn('Bare filename link texts', output)

    def test_custom_pattern_argument_is_checked(self):
        with tempfile.TemporaryDirectory() as root:
            _write_plan(root, '## Section\n\nTicket PROJECTNAME-1234 is referenced here.\n')
            with patch(
                'git_hooks_impl.entry_points.commands.audit_plan.project_root',
                return_value=root,
            ):
                result, output = self._run_and_capture([r'PROJECTNAME-\d+'])
        self.assertEqual(result, 1)
        self.assertIn("Custom: 'PROJECTNAME-\\d+'", output)

    def test_decisions_log_is_excluded_from_stale_ref_checks(self):
        with tempfile.TemporaryDirectory() as root:
            _write_plan(
                root,
                '## Section\n\ncontent\n\n'
                '## Decisions Log\n\nSee [somefile.md](somefile.md) here.\n',
            )
            with patch(
                'git_hooks_impl.entry_points.commands.audit_plan.project_root',
                return_value=root,
            ):
                result, output = self._run_and_capture()
        self.assertEqual(result, 0)
        self.assertIn('ALL CLEAN', output)

    def test_help_flag_returns_0_without_reading_plan(self):
        with patch(
            'git_hooks_impl.entry_points.commands.audit_plan.project_root',
        ) as mock_root:
            result, _ = self._run_and_capture(['--help'])
        self.assertEqual(result, 0)
        mock_root.assert_not_called()


if __name__ == '__main__':
    unittest.main()
