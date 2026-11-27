#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for git_hooks_impl.entry_points.commands.dump_code_quality_reference.

run()'s only direct dependency is ai_tooling_root(), mocked at the
dump_code_quality_reference import location per the Main Mock Rule. Smell
and pattern-index files are read directly from a tempdir tree the test
itself builds — not a project dependency.
"""

import io
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from git_hooks_impl.entry_points.commands import dump_code_quality_reference
from git_hooks_impl.tests._stdout_helpers import ReconfigurableStringIO


class TestDumpCodeQualityReference(unittest.TestCase):
    """run(): smell files are covered fully, in deterministic sorted order."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.refactorer_dir = os.path.join(
            self.root, 'claude', 'skills', 'orchestrator', 'roles', 'refactorer',
        )
        os.makedirs(os.path.join(self.refactorer_dir, 'smells'))
        os.makedirs(os.path.join(self.refactorer_dir, 'patterns'))
        with open(os.path.join(self.refactorer_dir, 'rules.md'), 'w', encoding='utf-8') as f:
            f.write('R1-R14 rule text\n')
        with open(os.path.join(self.refactorer_dir, 'patterns', 'ai_index.md'), 'w', encoding='utf-8') as f:
            f.write('pattern index text\n')
        # Written in reverse-alphabetical order on disk to prove glob's
        # filesystem order is not what determines output order.
        with open(os.path.join(self.refactorer_dir, 'smells', 'z_smell.md'), 'w', encoding='utf-8') as f:
            f.write('Z smell body\n')
        with open(os.path.join(self.refactorer_dir, 'smells', 'a_smell.md'), 'w', encoding='utf-8') as f:
            f.write('A smell body\n')

    @patch('git_hooks_impl.entry_points.commands.dump_code_quality_reference.ai_tooling_root')
    def test_all_smell_files_covered_regardless_of_disk_order(self, mock_ai_tooling_root):
        """Two smell files created z-then-a on disk -> both bodies appear in output."""
        mock_ai_tooling_root.return_value = self.root
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = dump_code_quality_reference.run([])
        output = stdout.getvalue()
        self.assertIn('A smell body', output)
        self.assertIn('Z smell body', output)
        self.assertEqual(result, 0)

    @patch('git_hooks_impl.entry_points.commands.dump_code_quality_reference.ai_tooling_root')
    def test_smell_files_printed_in_sorted_order(self, mock_ai_tooling_root):
        """a_smell.md heading appears before z_smell.md heading in output order."""
        mock_ai_tooling_root.return_value = self.root
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            dump_code_quality_reference.run([])
        output = stdout.getvalue()
        self.assertLess(output.index('## a_smell'), output.index('## z_smell'))

    @patch('git_hooks_impl.entry_points.commands.dump_code_quality_reference.ai_tooling_root')
    def test_pattern_index_printed_after_smells(self, mock_ai_tooling_root):
        """Pattern index section header and its body follow the smell section."""
        mock_ai_tooling_root.return_value = self.root
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            dump_code_quality_reference.run([])
        output = stdout.getvalue()
        self.assertLess(
            output.index('--- CODE SMELLS ---'),
            output.index('--- PATTERN INDEX'),
        )
        self.assertIn('pattern index text', output)

    @patch('git_hooks_impl.entry_points.commands.dump_code_quality_reference.ai_tooling_root')
    def test_no_smell_files_still_prints_headers_and_pattern_index(self, mock_ai_tooling_root):
        """Empty smells/ dir -> no crash, section headers and pattern index still print."""
        for name in os.listdir(os.path.join(self.refactorer_dir, 'smells')):
            os.remove(os.path.join(self.refactorer_dir, 'smells', name))
        mock_ai_tooling_root.return_value = self.root
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = dump_code_quality_reference.run([])
        output = stdout.getvalue()
        self.assertIn('--- CODE SMELLS ---', output)
        self.assertIn('pattern index text', output)
        self.assertEqual(result, 0)

    @patch('git_hooks_impl.entry_points.commands.dump_code_quality_reference.ai_tooling_root')
    def test_reconfigures_stdout_to_utf8_when_available(self, mock_ai_tooling_root):
        """Stdout supports reconfigure() -> run() switches it to utf-8/replace."""
        mock_ai_tooling_root.return_value = self.root
        fake_stdout = ReconfigurableStringIO()
        with redirect_stdout(fake_stdout):
            result = dump_code_quality_reference.run([])
        self.assertEqual(
            fake_stdout.reconfigure_calls, [{'encoding': 'utf-8', 'errors': 'replace'}],
        )
        self.assertEqual(result, 0)

    @patch('git_hooks_impl.entry_points.commands.dump_code_quality_reference.ai_tooling_root')
    def test_non_ascii_smell_content_does_not_raise(self, mock_ai_tooling_root):
        """Smell file containing a non-ASCII arrow -> run() completes and returns 0."""
        with open(
            os.path.join(self.refactorer_dir, 'smells', 'a_smell.md'), 'w', encoding='utf-8',
        ) as f:
            f.write('Guard clause → early return\n')
        mock_ai_tooling_root.return_value = self.root
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = dump_code_quality_reference.run([])
        self.assertIn('→', stdout.getvalue())
        self.assertEqual(result, 0)


if __name__ == '__main__':
    unittest.main()
