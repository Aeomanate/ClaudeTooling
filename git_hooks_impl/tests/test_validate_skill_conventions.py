#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for git_hooks_impl.entry_points.commands.validate_skill_conventions.

Each `_check_*` function's only external dependency is the filesystem, tested
against a real tempdir fixture tree per the Main Mock Rule (no mocking of
glob.glob/open — these are the function's own I/O over test-controlled
files, not calls to another module). run()'s direct dependencies are
project_root(), subprocess.check_output(), and the `_check_*` functions
reached through the module-level `_CHECKS` tuple — all mocked at the
validate_skill_conventions import location.
"""

import io
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from git_hooks_impl.entry_points.commands import validate_skill_conventions


def _write(root, rel_path, content):
    """Writes content to root/rel_path, creating parent dirs. rel_path uses '/'."""
    full_path = os.path.join(root, *rel_path.split('/'))
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, 'w', encoding='utf-8') as f:
        f.write(content)


class TestCheckHeadingsRolesScopeOnly(unittest.TestCase):
    """_check_headings scans roles/**/workflow.md only, not shared/rules/workflow.md."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        # VIOLATION lines carry the absolute, OS-native path (not relpath'd), so
        # assertions match on the OS-native join rather than a literal '/'.
        self._shared_workflow = os.path.join(
            'shared', 'rules', 'workflow.md'
        )
        self._fixer_workflow = os.path.join('roles', 'fixer', 'workflow.md')

    def test_bad_heading_under_shared_rules_is_not_flagged(self):
        """shared/rules/workflow.md with a non-## first heading -> not in scope, not flagged."""
        _write(
            self.root,
            'claude/skills/orchestrator/shared/rules/workflow.md',
            '# Workflow Rules\n\nBody text.\n',
        )
        result = validate_skill_conventions._check_headings(self.root)
        self.assertFalse(any(self._shared_workflow in line for line in result))

    def test_same_defect_under_roles_is_flagged(self):
        """roles/<role>/workflow.md with the same non-## first heading -> flagged."""
        _write(
            self.root,
            'claude/skills/orchestrator/roles/fixer/workflow.md',
            '# Fixer Workflow\n\nBody text.\n',
        )
        result = validate_skill_conventions._check_headings(self.root)
        matches = [line for line in result if self._fixer_workflow in line]
        self.assertEqual(len(matches), 1)
        self.assertTrue(matches[0].startswith('VIOLATION: '))

    def test_both_present_only_roles_file_is_flagged(self):
        """Both files defective in the same tree -> only the roles/ one appears."""
        _write(
            self.root,
            'claude/skills/orchestrator/shared/rules/workflow.md',
            '# Workflow Rules\n\nBody text.\n',
        )
        _write(
            self.root,
            'claude/skills/orchestrator/roles/fixer/workflow.md',
            '# Fixer Workflow\n\nBody text.\n',
        )
        result = validate_skill_conventions._check_headings(self.root)
        self.assertTrue(any(self._fixer_workflow in line for line in result))
        self.assertFalse(any(self._shared_workflow in line for line in result))

    def test_correct_heading_reports_clean(self):
        """roles/<role>/workflow.md starting with '## ' -> CLEAN, no violation."""
        _write(
            self.root,
            'claude/skills/orchestrator/roles/fixer/workflow.md',
            '## Fixer Workflow\n\nBody text.\n',
        )
        result = validate_skill_conventions._check_headings(self.root)
        self.assertTrue(any('CLEAN' in line for line in result))
        self.assertFalse(any(line.startswith('VIOLATION: ') for line in result))

    def test_skill_validation_role_is_excluded(self):
        """roles/skill-validation/workflow.md defect is excluded regardless of heading."""
        _write(
            self.root,
            'claude/skills/orchestrator/roles/skill-validation/workflow.md',
            '# Skill Validation\n\nBody text.\n',
        )
        result = validate_skill_conventions._check_headings(self.root)
        self.assertFalse(any('skill-validation' in line for line in result))


class TestCheckLinks(unittest.TestCase):
    """_check_links flags ../ cross-references and bare-filename link text."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_cross_dir_link_is_flagged(self):
        """A '](../' cross-directory reference -> VIOLATION with detail line."""
        _write(
            self.root,
            'claude/skills/orchestrator/roles/fixer/rules.md',
            'See [other rules](../refactorer/rules.md) for details.\n',
        )
        result = validate_skill_conventions._check_links(self.root)
        self.assertTrue(any('Found ../ cross-references' in line for line in result))
        self.assertTrue(any('rules.md:1:' in line for line in result))

    def test_bare_filename_link_text_is_flagged(self):
        """Link text that is a bare '[file.md](...)' -> VIOLATION."""
        _write(
            self.root,
            'claude/skills/orchestrator/roles/fixer/rules.md',
            'See [workflow.md](./workflow.md) for details.\n',
        )
        result = validate_skill_conventions._check_links(self.root)
        self.assertTrue(any('bare filename link texts' in line for line in result))

    def test_clean_tree_reports_clean(self):
        """No ../ refs, no bare filename link text -> CLEAN for both sub-checks."""
        _write(
            self.root,
            'claude/skills/orchestrator/roles/fixer/rules.md',
            'See [fixer rules](./rules.md) for details.\n',
        )
        result = validate_skill_conventions._check_links(self.root)
        self.assertTrue(any('All links follow conventions' in line for line in result))

    def test_dangling_link_in_agent_file_is_flagged(self):
        """A dangling .md link target inside claude/agents/ -> VIOLATION.

        claude/agents/ sits outside the skill tree; _check_link_targets
        must scan it too, not just claude/skills/orchestrator/.
        """
        _write(
            self.root,
            'claude/agents/orchestrator-persistent-fixer.md',
            'See [missing file](./does-not-exist.md) for details.\n',
        )
        result = validate_skill_conventions._check_links(self.root)
        self.assertTrue(any('dangling link target' in line for line in result))


class TestCheckStructure(unittest.TestCase):
    """_check_structure flags roles missing rules.md or workflow.md."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_missing_rules_file_is_flagged(self):
        """A role dir with workflow.md but no rules.md -> MISSING for rules.md."""
        _write(
            self.root, 'claude/skills/orchestrator/roles/coder/workflow.md', '## Coder\n',
        )
        result = validate_skill_conventions._check_structure(self.root)
        self.assertTrue(any('MISSING: coder/rules.md' in line for line in result))

    def test_present_rules_and_workflow_report_ok(self):
        """A role dir with both files -> OK for each."""
        _write(
            self.root, 'claude/skills/orchestrator/roles/coder/rules.md', '# Coder Rules\n',
        )
        _write(
            self.root, 'claude/skills/orchestrator/roles/coder/workflow.md', '## Coder\n',
        )
        result = validate_skill_conventions._check_structure(self.root)
        self.assertTrue(any('OK: coder/rules.md' in line for line in result))
        self.assertTrue(any('OK: coder/workflow.md' in line for line in result))


class TestCheckInlineCommands(unittest.TestCase):
    """_check_inline_commands flags raw multi-flag commands in ```bash blocks."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_raw_command_outside_allow_list_is_flagged(self):
        """A bare 'python -m ...' line in a ```bash block -> VIOLATION."""
        _write(
            self.root,
            'claude/skills/orchestrator/roles/fixer/rules.md',
            '```bash\npython -m unittest discover git_hooks_impl/tests\n```\n',
        )
        result = validate_skill_conventions._check_inline_commands(self.root)
        self.assertTrue(any('VIOLATION:' in line for line in result))

    def test_validated_trailing_comment_is_exempt(self):
        """A raw command line ending with a 'VALIDATED' comment -> not flagged."""
        _write(
            self.root,
            'claude/skills/orchestrator/roles/fixer/rules.md',
            '```bash\npython -m unittest discover git_hooks_impl/tests  # VALIDATED: exempt\n```\n',
        )
        result = validate_skill_conventions._check_inline_commands(self.root)
        self.assertTrue(any('CLEAN' in line for line in result))
        self.assertFalse(any('VIOLATION:' in line for line in result))

    def test_allow_listed_prefix_is_not_flagged(self):
        """An 'mr ...' command line -> matches the allow-list, not flagged."""
        _write(
            self.root,
            'claude/skills/orchestrator/roles/fixer/rules.md',
            '```bash\nmr verify\n```\n',
        )
        result = validate_skill_conventions._check_inline_commands(self.root)
        self.assertTrue(any('CLEAN' in line for line in result))


class TestCheckHistoryNarrative(unittest.TestCase):
    """_check_history_narrative flags STYLE-2 pollution patterns."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_forbidden_pattern_is_counted_as_violation(self):
        """'(NEW)' marker text -> FAIL with a violation count of 1."""
        _write(
            self.root,
            'claude/skills/orchestrator/roles/fixer/rules.md',
            'This rule (NEW) tightens validation.\n',
        )
        result = validate_skill_conventions._check_history_narrative(self.root)
        self.assertTrue(result[0].startswith('FAIL: 1 history-narrative violation'))

    def test_exempt_style_file_is_not_counted(self):
        """shared/rules/style.md may reference the pattern text as an example -> excluded."""
        _write(
            self.root,
            'claude/skills/orchestrator/shared/rules/style.md',
            'Example of a forbidden marker: (NEW).\n',
        )
        result = validate_skill_conventions._check_history_narrative(self.root)
        self.assertTrue(result[0].startswith('PASS:'))

    def test_validated_marker_line_is_not_counted(self):
        """A line carrying '<!-- VALIDATED -->' is a known false positive -> excluded."""
        _write(
            self.root,
            'claude/skills/orchestrator/roles/fixer/rules.md',
            'This rule (NEW) tightens validation. <!-- VALIDATED -->\n',
        )
        result = validate_skill_conventions._check_history_narrative(self.root)
        self.assertTrue(result[0].startswith('PASS:'))


class TestCheckPaths(unittest.TestCase):
    """_check_paths flags stale 'orchestrator/scripts/' source directives in .sh files."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_stale_source_directive_is_flagged(self):
        """A 'source .../orchestrator/scripts/x.sh' line -> VIOLATION."""
        _write(
            self.root,
            'claude/skills/orchestrator/shared/scripts/run.sh',
            '#!/bin/bash\nsource ~/.claude/skills/orchestrator/scripts/helpers.sh\n',
        )
        result = validate_skill_conventions._check_paths(self.root)
        self.assertTrue(any('VIOLATION:' in line for line in result))

    def test_clean_script_reports_clean(self):
        """No stale source directive -> CLEAN."""
        _write(
            self.root,
            'claude/skills/orchestrator/shared/scripts/run.sh',
            '#!/bin/bash\necho hello\n',
        )
        result = validate_skill_conventions._check_paths(self.root)
        self.assertTrue(any('CLEAN' in line for line in result))


class TestCheckAgentInstructions(unittest.TestCase):
    """_check_agent_instructions flags agent-instructions/*.md missing a required section."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_missing_section_is_flagged(self):
        """A file missing '## Scope' -> VIOLATION naming the missing section."""
        _write(
            self.root,
            'claude/skills/orchestrator/roles/fixer/agent-instructions/example.md',
            '## Purpose\nx\n## Inputs\nx\n## Output Format\nx\n## Rules\nx\n',
        )
        result = validate_skill_conventions._check_agent_instructions(self.root)
        self.assertTrue(any('VIOLATION:' in line and 'Scope' in line for line in result))

    def test_all_five_sections_present_reports_clean(self):
        """A file with all 5 sections -> CLEAN, no VIOLATION line."""
        _write(
            self.root,
            'claude/skills/orchestrator/roles/fixer/agent-instructions/example.md',
            '## Purpose\nx\n## Inputs\nx\n## Output Format\nx\n## Rules\nx\n## Scope\nx\n',
        )
        result = validate_skill_conventions._check_agent_instructions(self.root)
        self.assertTrue(any('CLEAN' in line for line in result))
        self.assertFalse(any('VIOLATION:' in line for line in result))

    def test_no_agent_instructions_files_reports_clean(self):
        """No agent-instructions/*.md anywhere -> CLEAN, zero files."""
        os.makedirs(os.path.join(self.root, 'claude', 'skills', 'orchestrator'))
        result = validate_skill_conventions._check_agent_instructions(self.root)
        self.assertTrue(any('CLEAN' in line for line in result))


class TestRunViolationCounting(unittest.TestCase):
    """run() sums both violation-line shapes into the total count."""

    @patch('git_hooks_impl.entry_points.commands.validate_skill_conventions.subprocess.check_output')
    @patch('git_hooks_impl.entry_points.commands.validate_skill_conventions.project_root')
    def test_bare_detail_line_and_prefixed_line_both_count(
        self, mock_project_root, mock_check_output
    ):
        """One 'file.ext:line:' detail line (check_links shape) plus one
        'VIOLATION: ' prefixed line (check_headings/inline_commands/paths shape)
        -> total violation count is 2, not 1.
        """
        mock_project_root.return_value = tempfile.mkdtemp()
        mock_check_output.return_value = 'main\n'
        fake_checks = (
            lambda root: ['### Check: bare-shape', '  roles/x/rules.md:3:some text'],
            lambda root: ['### Check: prefixed-shape', 'VIOLATION: roles/y/workflow.md bad heading'],
        )
        with patch(
            'git_hooks_impl.entry_points.commands.validate_skill_conventions._CHECKS',
            fake_checks,
        ):
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = validate_skill_conventions.run([])
        self.assertIn('Total violation categories: 2', stdout.getvalue())
        self.assertEqual(result, 1)

    @patch('git_hooks_impl.entry_points.commands.validate_skill_conventions.subprocess.check_output')
    @patch('git_hooks_impl.entry_points.commands.validate_skill_conventions.project_root')
    def test_no_violation_lines_reports_all_clean_and_returns_0(
        self, mock_project_root, mock_check_output
    ):
        """Checks reporting only CLEAN lines -> zero total, ALL CLEAN, returns 0."""
        mock_project_root.return_value = tempfile.mkdtemp()
        mock_check_output.return_value = 'main\n'
        fake_checks = (
            lambda root: ['### Check: clean-one', '  CLEAN: nothing found'],
        )
        with patch(
            'git_hooks_impl.entry_points.commands.validate_skill_conventions._CHECKS',
            fake_checks,
        ):
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = validate_skill_conventions.run([])
        output = stdout.getvalue()
        self.assertIn('Total violation categories: 0', output)
        self.assertIn('Status: ALL CLEAN', output)
        self.assertEqual(result, 0)


if __name__ == '__main__':
    unittest.main()
