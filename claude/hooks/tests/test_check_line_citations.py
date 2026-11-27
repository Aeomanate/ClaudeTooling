#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for claude/hooks/check_line_citations.py.

The hook is fail-open by design: every code path returns 0.
"""

import unittest
from unittest.mock import mock_open, patch

from claude.hooks.check_line_citations import _find_citation_lines, _is_excluded, main


# ===========================================================================
#  _find_citation_lines
# ===========================================================================

class TestFindCitationLines(unittest.TestCase):

    def test_no_citation_returns_empty(self):
        """No file:line-shaped token anywhere -> []."""
        result = _find_citation_lines(['plain line\n', 'another line\n'])
        self.assertEqual(result, [])

    def test_single_citation_returns_its_line_number(self):
        """One line contains a file:line citation -> that 1-indexed line number."""
        result = _find_citation_lines(
            ['plain\n', 'see etw_service.cpp:59-62 for details\n', 'plain\n'])
        self.assertEqual(result, [2])

    def test_multiple_citations_returns_all_line_numbers(self):
        """Several lines contain a citation -> all their 1-indexed line numbers."""
        lines = [
            'foo.hpp:12\n',
            'plain\n',
            'a claim (bar.py:5,9) here\n',
            'main.cpp:100-120 also\n',
        ]
        result = _find_citation_lines(lines)
        self.assertEqual(result, [1, 3, 4])

    def test_bare_path_without_line_number_does_not_count(self):
        """A bare file path with no trailing :digits is not a citation."""
        result = _find_citation_lines(['see docs/service.md for the full picture\n'])
        self.assertEqual(result, [])

    def test_prose_colon_without_digits_does_not_count(self):
        """An ordinary sentence colon is not mistaken for a citation."""
        result = _find_citation_lines(['Note: this behavior is intentional\n'])
        self.assertEqual(result, [])


# ===========================================================================
#  _is_excluded
# ===========================================================================

class TestIsExcluded(unittest.TestCase):

    def test_ordinary_doc_path_not_excluded(self):
        """A normal repo doc path is checked."""
        self.assertFalse(_is_excluded('docs/service.md'))

    def test_claude_dir_segment_excluded(self):
        """Any path with a 'claude' directory component is excluded."""
        self.assertTrue(_is_excluded('claude/skills/orchestrator/rules/delegation.md'))
        self.assertTrue(_is_excluded('.claude/some/nested/file.md'))

    def test_cache_dir_segment_excluded(self):
        """Any path with a 'cache' directory component is excluded."""
        self.assertTrue(_is_excluded('.ai/cache/agents/gitter/output.md'))

    def test_branch_plan_file_excluded(self):
        """The branch plan file itself is excluded, regardless of leading path."""
        self.assertTrue(_is_excluded('.ai/BRANCH_PLAN.md'))
        self.assertTrue(_is_excluded('C:/repo/.ai/BRANCH_PLAN.md'))

    def test_other_ai_dir_file_not_excluded(self):
        """A file under .ai/ that is neither BRANCH_PLAN.md nor under cache/ is checked."""
        self.assertFalse(_is_excluded('.ai/notes/design.md'))

    def test_backslash_path_normalized(self):
        """Windows-style backslash paths are normalized before matching."""
        self.assertTrue(_is_excluded('C:\\repo\\claude\\hooks\\check_em_dash.py'))
        self.assertTrue(_is_excluded('C:\\repo\\.ai\\BRANCH_PLAN.md'))


# ===========================================================================
#  main()
# ===========================================================================

class TestMain(unittest.TestCase):

    def test_malformed_json_returns_0_no_print(self):
        """Malformed stdin JSON -> returns 0, never prints."""
        with patch('claude.hooks.check_line_citations.json.load', side_effect=ValueError), \
             patch('builtins.print') as mock_print:
            result = main()
        self.assertEqual(result, 0)
        mock_print.assert_not_called()

    def test_wrong_tool_name_returns_0(self):
        """tool_name outside (Edit, Write) -> returns 0, never reads a file."""
        event = {'tool_name': 'Read', 'tool_input': {'file_path': '/x.md'}}
        with patch('claude.hooks.check_line_citations.json.load', return_value=event), \
             patch('claude.hooks.check_line_citations.os.path.isfile') as mock_isfile, \
             patch('builtins.print') as mock_print:
            result = main()
        self.assertEqual(result, 0)
        mock_isfile.assert_not_called()
        mock_print.assert_not_called()

    def test_missing_file_path_returns_0(self):
        """Event has no file_path -> returns 0."""
        event = {'tool_name': 'Edit', 'tool_input': {}}
        with patch('claude.hooks.check_line_citations.json.load', return_value=event), \
             patch('builtins.print') as mock_print:
            result = main()
        self.assertEqual(result, 0)
        mock_print.assert_not_called()

    def test_extension_not_checked_returns_0(self):
        """File extension outside _CHECKED_EXTENSIONS -> returns 0, never touches disk."""
        event = {'tool_name': 'Edit', 'tool_input': {'file_path': '/x.json'}}
        with patch('claude.hooks.check_line_citations.json.load', return_value=event), \
             patch('claude.hooks.check_line_citations.os.path.isfile') as mock_isfile, \
             patch('builtins.print') as mock_print:
            result = main()
        self.assertEqual(result, 0)
        mock_isfile.assert_not_called()
        mock_print.assert_not_called()

    def test_excluded_path_returns_0_before_disk_check(self):
        """A path under an excluded directory segment -> returns 0, never touches disk."""
        event = {'tool_name': 'Edit', 'tool_input': {'file_path': 'claude/hooks/check_em_dash.py'}}
        with patch('claude.hooks.check_line_citations.json.load', return_value=event), \
             patch('claude.hooks.check_line_citations.os.path.isfile') as mock_isfile, \
             patch('builtins.print') as mock_print:
            result = main()
        self.assertEqual(result, 0)
        mock_isfile.assert_not_called()
        mock_print.assert_not_called()

    def test_branch_plan_path_excluded(self):
        """.ai/BRANCH_PLAN.md -> returns 0, never touches disk."""
        event = {'tool_name': 'Write', 'tool_input': {'file_path': '.ai/BRANCH_PLAN.md'}}
        with patch('claude.hooks.check_line_citations.json.load', return_value=event), \
             patch('claude.hooks.check_line_citations.os.path.isfile') as mock_isfile, \
             patch('builtins.print') as mock_print:
            result = main()
        self.assertEqual(result, 0)
        mock_isfile.assert_not_called()
        mock_print.assert_not_called()

    def test_file_not_on_disk_returns_0(self):
        """os.path.isfile is False -> returns 0, never opens the file."""
        event = {'tool_name': 'Edit', 'tool_input': {'file_path': 'docs/service.md'}}
        with patch('claude.hooks.check_line_citations.json.load', return_value=event), \
             patch('claude.hooks.check_line_citations.os.path.isfile', return_value=False), \
             patch('builtins.open') as mock_open_fn, \
             patch('builtins.print') as mock_print:
            result = main()
        self.assertEqual(result, 0)
        mock_open_fn.assert_not_called()
        mock_print.assert_not_called()

    def test_file_open_oserror_returns_0_no_print(self):
        """Reading the file raises OSError -> returns 0, never prints."""
        event = {'tool_name': 'Edit', 'tool_input': {'file_path': 'docs/service.md'}}
        with patch('claude.hooks.check_line_citations.json.load', return_value=event), \
             patch('claude.hooks.check_line_citations.os.path.isfile', return_value=True), \
             patch('builtins.open', side_effect=OSError), \
             patch('builtins.print') as mock_print:
            result = main()
        self.assertEqual(result, 0)
        mock_print.assert_not_called()

    def test_no_citations_found_returns_0_no_print(self):
        """File reads clean -> returns 0, never prints."""
        event = {'tool_name': 'Edit', 'tool_input': {'file_path': 'docs/service.md'}}
        content = 'ServiceEventSink::OnSourceStopped logs a warning.\n'
        with patch('claude.hooks.check_line_citations.json.load', return_value=event), \
             patch('claude.hooks.check_line_citations.os.path.isfile', return_value=True), \
             patch('builtins.open', mock_open(read_data=content)), \
             patch('builtins.print') as mock_print:
            result = main()
        self.assertEqual(result, 0)
        mock_print.assert_not_called()

    def test_reports_hits_never_rewrites_file(self):
        """Citation hits found -> single print, file is never opened for write."""
        event = {'tool_name': 'Write', 'tool_input': {'file_path': 'docs/service.md'}}
        content = 'plain\nsee etw_service.cpp:59-62\nplain\nsee main.cpp:484-487\n'
        mocked_open = mock_open(read_data=content)
        with patch('claude.hooks.check_line_citations.json.load', return_value=event), \
             patch('claude.hooks.check_line_citations.os.path.isfile', return_value=True), \
             patch('builtins.open', mocked_open), \
             patch('builtins.print') as mock_print:
            result = main()
        self.assertEqual(result, 0)
        mock_print.assert_called_once_with(
            '[check_line_citations] docs/service.md: file:line citation on '
            'line(s) 2, 4 - STYLE-9 NO-LINE-CITATIONS: name the file, class, '
            'or function instead.'
        )
        mocked_open.assert_called_once()

    def test_reports_truncated_hits_with_more_suffix(self):
        """More than 10 hits -> only first 10 listed, with a '(+N more)' suffix."""
        event = {'tool_name': 'Edit', 'tool_input': {'file_path': 'docs/big.md'}}
        content = ''.join(f'foo.cpp:{i}\n' for i in range(1, 13))
        with patch('claude.hooks.check_line_citations.json.load', return_value=event), \
             patch('claude.hooks.check_line_citations.os.path.isfile', return_value=True), \
             patch('builtins.open', mock_open(read_data=content)), \
             patch('builtins.print') as mock_print:
            result = main()
        self.assertEqual(result, 0)
        mock_print.assert_called_once_with(
            '[check_line_citations] docs/big.md: file:line citation on line(s) '
            '1, 2, 3, 4, 5, 6, 7, 8, 9, 10 (+2 more) - STYLE-9 NO-LINE-CITATIONS: '
            'name the file, class, or function instead.'
        )


if __name__ == '__main__':
    unittest.main()
