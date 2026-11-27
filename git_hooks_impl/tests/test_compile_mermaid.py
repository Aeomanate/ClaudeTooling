#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for git_hooks_impl.entry_points.commands.compile_mermaid.

compile_report()'s direct external dependencies are shutil.which (locates
node/npm) and subprocess.run (invokes validate.mjs, and npm install on
first use) — both mocked per the Main Mock Rule. No browser of any kind is
ever involved: validation runs mermaid.parse() under jsdom. Doc reading,
block extraction, and tempdir writes operate on real files inside tempdir
fixtures. run() is a thin wrapper around compile_report(), covered
separately by a smoke test that mocks compile_report() itself.
"""

import io
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

from git_hooks_impl.entry_points.commands import compile_mermaid


def _fake_validate_pass(cmd, **kwargs):
    """side_effect: validate.mjs reports VALID, rc=0."""
    return MagicMock(returncode=0, stdout='VALID\n', stderr='')


def _fake_validate_fail(cmd, **kwargs):
    """side_effect: validate.mjs reports INVALID, rc=1, with a parse error on stderr."""
    return MagicMock(returncode=1, stdout='INVALID\n', stderr='Parse error on line 1: bad syntax\n')


def _sequenced_side_effect(outcomes):
    """Builds a subprocess.run side_effect cycling through 'pass'/'fail' outcomes."""
    state = {'calls': 0}

    def _run(cmd, **kwargs):
        outcome = outcomes[state['calls']]
        state['calls'] += 1
        if outcome == 'pass':
            return _fake_validate_pass(cmd, **kwargs)
        return _fake_validate_fail(cmd, **kwargs)

    return _run


@patch('git_hooks_impl.entry_points.commands.compile_mermaid._ensure_validator_deps', return_value=True)
class TestCompileReport(unittest.TestCase):
    """compile_report(): extracts mermaid blocks from a doc and validates each with validate.mjs.

    _ensure_validator_deps is mocked True at the class level for every test
    here except the dedicated ones covering it directly — those don't use
    this decorator. run() is a thin print/return wrapper around
    compile_report(), covered here only by test_run_delegates_to_compile_report.
    """

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def _write_doc(self, text):
        path = os.path.join(self.root, 'doc.md')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)
        return path

    @patch('git_hooks_impl.entry_points.commands.compile_mermaid.subprocess.run')
    @patch('git_hooks_impl.entry_points.commands.compile_mermaid.shutil.which')
    def test_multi_block_all_pass_returns_0(self, mock_which, mock_run, mock_deps):
        """Two valid mermaid blocks, validator succeeds on both -> exit 0, PASS trailer."""
        doc = self._write_doc(
            '# Doc\n```mermaid\ngraph TD; A-->B;\n```\ntext\n'
            '```mermaid\ngraph TD; C-->D;\n```\n'
        )
        mock_which.return_value = 'node'
        mock_run.side_effect = _fake_validate_pass
        result, report = compile_mermaid.compile_report([doc])
        self.assertEqual(result, 0)
        self.assertIn('Found 2 mermaid block(s).', report)
        self.assertIn('All 2 blocks PASS.', report)

    @patch('git_hooks_impl.entry_points.commands.compile_mermaid.subprocess.run')
    @patch('git_hooks_impl.entry_points.commands.compile_mermaid.shutil.which')
    def test_single_block_fail_returns_zero_and_skips(self, mock_which, mock_run, mock_deps):
        """Validator reports INVALID -> exit 0 still, SKIP line with full inline error."""
        doc = self._write_doc('```mermaid\ngraph TD; A-->B;\n```\n')
        mock_which.return_value = 'node'
        mock_run.side_effect = _fake_validate_fail
        result, report = compile_mermaid.compile_report([doc])
        self.assertEqual(result, 0)
        self.assertIn('Block 1 (lines 2-2): SKIP (parse failed)', report)
        self.assertIn('Parse error on line 1: bad syntax', report)
        self.assertIn('1 of 1 blocks SKIPPED', report)

    @patch('git_hooks_impl.entry_points.commands.compile_mermaid.subprocess.run')
    @patch('git_hooks_impl.entry_points.commands.compile_mermaid.shutil.which')
    def test_mixed_pass_fail_aggregation(self, mock_which, mock_run, mock_deps):
        """One block passes, one fails -> exit 0, correct PASS/SKIP counts."""
        doc = self._write_doc(
            '```mermaid\ngraph TD; A-->B;\n```\n```mermaid\ngraph TD; C-->D;\n```\n'
        )
        mock_which.return_value = 'node'
        mock_run.side_effect = _sequenced_side_effect(['pass', 'fail'])
        result, report = compile_mermaid.compile_report([doc])
        self.assertEqual(result, 0)
        self.assertIn('1 of 2 blocks SKIPPED', report)
        self.assertIn('PASS=1.', report)

    @patch('git_hooks_impl.entry_points.commands.compile_mermaid.shutil.which')
    def test_node_not_found_returns_2(self, mock_which, mock_deps):
        """Node missing from PATH -> exit 2, no subprocess call attempted."""
        doc = self._write_doc('```mermaid\ngraph TD; A-->B;\n```\n')
        mock_which.return_value = None
        result, report = compile_mermaid.compile_report([doc])
        self.assertEqual(result, 2)
        self.assertIn('node/npm not found', report)

    @patch('git_hooks_impl.entry_points.commands.compile_mermaid.shutil.which')
    def test_deps_install_failure_returns_2(self, mock_which, mock_deps):
        """_ensure_validator_deps failing (npm install error) -> exit 2."""
        doc = self._write_doc('```mermaid\ngraph TD; A-->B;\n```\n')
        mock_which.return_value = 'node'
        mock_deps.return_value = False
        result, report = compile_mermaid.compile_report([doc])
        self.assertEqual(result, 2)

    def test_doc_not_found_returns_2(self, mock_deps):
        """Explicit doc path that doesn't exist -> exit 2."""
        missing = os.path.join(self.root, 'missing.md')
        result, report = compile_mermaid.compile_report([missing])
        self.assertEqual(result, 2)
        self.assertIn('doc not found', report)

    def test_no_arg_no_env_var_returns_2(self, mock_deps):
        """No argv and no SW_ARCH_DRD_REPO env var -> exit 2, usage printed."""
        with patch.dict(os.environ, {}, clear=True):
            result, report = compile_mermaid.compile_report([])
        self.assertEqual(result, 2)
        self.assertIn('SW_ARCH_DRD_REPO', report)

    @patch('git_hooks_impl.entry_points.commands.compile_mermaid.shutil.which')
    def test_no_mermaid_blocks_returns_0(self, mock_which, mock_deps):
        """Doc with zero mermaid blocks -> exit 0, 'Nothing to validate.'"""
        doc = self._write_doc('# Doc\nplain text, no blocks.\n')
        mock_which.return_value = 'node'
        result, report = compile_mermaid.compile_report([doc])
        self.assertEqual(result, 0)
        self.assertIn('Nothing to validate.', report)

    @patch('git_hooks_impl.entry_points.commands.compile_mermaid.shutil.which')
    def test_unterminated_block_returns_3(self, mock_which, mock_deps):
        """A mermaid block with no closing fence -> exit 3, WARN on stderr."""
        doc = self._write_doc('```mermaid\ngraph TD; A-->B;\n')
        mock_which.return_value = 'node'
        result, report = compile_mermaid.compile_report([doc])
        self.assertEqual(result, 3)
        self.assertIn('unterminated mermaid block', report)

    @patch('git_hooks_impl.entry_points.commands.compile_mermaid.shutil.which')
    def test_auto_detect_single_md_under_approved_dir(self, mock_which, mock_deps):
        """No argv, env var set, exactly one *.md under approved/ -> resolves it."""
        approved = os.path.join(self.root, 'approved')
        os.makedirs(approved)
        doc_path = os.path.join(approved, 'only.md')
        with open(doc_path, 'w', encoding='utf-8') as f:
            f.write('# Doc\nno blocks here.\n')
        mock_which.return_value = 'node'
        with patch.dict(os.environ, {'SW_ARCH_DRD_REPO': self.root}, clear=False):
            result, report = compile_mermaid.compile_report([])
        self.assertEqual(result, 0)
        self.assertIn(doc_path, report)

    def test_auto_detect_no_matches_returns_2(self, mock_deps):
        """Env var set, approved/ exists but has no *.md -> exit 2."""
        approved = os.path.join(self.root, 'approved')
        os.makedirs(approved)
        with patch.dict(os.environ, {'SW_ARCH_DRD_REPO': self.root}, clear=False):
            result, report = compile_mermaid.compile_report([])
        self.assertEqual(result, 2)
        self.assertIn('no *.md found', report)

    def test_auto_detect_multiple_matches_returns_2(self, mock_deps):
        """Env var set, approved/ has 2+ *.md -> exit 2, lists both candidates."""
        approved = os.path.join(self.root, 'approved')
        os.makedirs(approved)
        for name in ('a.md', 'b.md'):
            with open(os.path.join(approved, name), 'w', encoding='utf-8') as f:
                f.write('# doc\n')
        with patch.dict(os.environ, {'SW_ARCH_DRD_REPO': self.root}, clear=False):
            result, report = compile_mermaid.compile_report([])
        self.assertEqual(result, 2)
        self.assertIn('multiple *.md found', report)

    @patch('git_hooks_impl.entry_points.commands.compile_mermaid.compile_report')
    def test_run_delegates_to_compile_report(self, mock_compile_report, mock_deps):
        """run() prints compile_report()'s report text and returns its exit code."""
        mock_compile_report.return_value = (1, 'fake report text')
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = compile_mermaid.run(['doc.md'])
        self.assertEqual(result, 1)
        self.assertIn('fake report text', stdout.getvalue())
        mock_compile_report.assert_called_once_with(['doc.md'])


class TestEnsureValidatorDeps(unittest.TestCase):
    """_ensure_validator_deps(): lazy npm install, keyed on node_modules presence."""

    def setUp(self):
        from pathlib import Path
        self.fake_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.fake_dir, ignore_errors=True)
        self.patcher = patch('git_hooks_impl.entry_points.commands.compile_mermaid._VALIDATOR_DIR', self.fake_dir)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    @patch('git_hooks_impl.entry_points.commands.compile_mermaid.subprocess.run')
    def test_skips_install_when_deps_already_present(self, mock_run):
        """mermaid/ and jsdom/ both already dirs under node_modules -> no subprocess call."""
        (self.fake_dir / 'node_modules' / 'mermaid').mkdir(parents=True)
        (self.fake_dir / 'node_modules' / 'jsdom').mkdir(parents=True)
        lines = []
        result = compile_mermaid._ensure_validator_deps('npm', lines)
        self.assertTrue(result)
        mock_run.assert_not_called()

    @patch('git_hooks_impl.entry_points.commands.compile_mermaid.subprocess.run')
    def test_install_failure_reports_error(self, mock_run):
        """npm install returns nonzero (deps not yet present) -> False, stderr surfaced in lines."""
        mock_run.return_value = MagicMock(returncode=1, stdout='', stderr='npm ERR! network timeout\n')
        lines = []
        result = compile_mermaid._ensure_validator_deps('npm', lines)
        self.assertFalse(result)
        self.assertTrue(any('npm install failed' in line for line in lines))
        self.assertTrue(any('network timeout' in line for line in lines))


if __name__ == '__main__':
    unittest.main()
