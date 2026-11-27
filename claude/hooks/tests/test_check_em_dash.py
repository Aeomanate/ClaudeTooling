#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for claude/hooks/check_em_dash.py.

The hook is fail-open by design: every code path returns 0.
"""

import unittest
from unittest.mock import mock_open, patch

from claude.hooks.check_em_dash import _extract_file_path, _replace_em_dashes, main

_EM_DASH = chr(0x2014)


# ===========================================================================
#  _replace_em_dashes
# ===========================================================================

class TestReplaceEmDashes(unittest.TestCase):

    def test_no_em_dash_returns_empty_and_leaves_lines_unchanged(self):
        """No em dash anywhere -> [], lines untouched."""
        lines = ['plain line\n', 'another line\n']
        result = _replace_em_dashes(lines)
        self.assertEqual(result, [])
        self.assertEqual(lines, ['plain line\n', 'another line\n'])

    def test_single_em_dash_replaces_it_and_returns_its_line_number(self):
        """One line contains an em dash -> replaced with '-', that 1-indexed line number returned."""
        lines = ['plain\n', f'has{_EM_DASH}dash\n', 'plain\n']
        result = _replace_em_dashes(lines)
        self.assertEqual(result, [2])
        self.assertEqual(lines, ['plain\n', 'has-dash\n', 'plain\n'])

    def test_multiple_em_dashes_replaces_all_and_returns_all_line_numbers(self):
        """Several lines contain an em dash -> all replaced, all 1-indexed line numbers returned."""
        lines = [f'{_EM_DASH}\n', 'plain\n', f'a{_EM_DASH}b\n', f'{_EM_DASH}end\n']
        result = _replace_em_dashes(lines)
        self.assertEqual(result, [1, 3, 4])
        self.assertEqual(lines, ['-\n', 'plain\n', 'a-b\n', '-end\n'])

    def test_em_dash_mid_line_vs_whole_line(self):
        """Em dash embedded mid-line and a line that is only an em dash both count and get replaced."""
        lines = [f'word{_EM_DASH}word\n', _EM_DASH, 'no dash here\n']
        result = _replace_em_dashes(lines)
        self.assertEqual(result, [1, 2])
        self.assertEqual(lines, ['word-word\n', '-', 'no dash here\n'])


# ===========================================================================
#  _extract_file_path
# ===========================================================================

class TestExtractFilePath(unittest.TestCase):

    def test_normal_event_returns_file_path(self):
        """tool_input.file_path present -> that path."""
        event = {'tool_input': {'file_path': '/some/file.py'}}
        self.assertEqual(_extract_file_path(event), '/some/file.py')

    def test_missing_tool_input_returns_none(self):
        """No tool_input key at all -> None."""
        event = {'tool_name': 'Edit'}
        self.assertIsNone(_extract_file_path(event))

    def test_tool_input_without_file_path_key_returns_none(self):
        """tool_input present but has no file_path key -> None."""
        event = {'tool_input': {'other_key': 'value'}}
        self.assertIsNone(_extract_file_path(event))


# ===========================================================================
#  main()
# ===========================================================================

class TestMain(unittest.TestCase):

    def test_malformed_json_returns_0_no_print(self):
        """Malformed stdin JSON -> returns 0, never prints."""
        with patch('claude.hooks.check_em_dash.json.load', side_effect=ValueError), \
             patch('builtins.print') as mock_print:
            result = main()
        self.assertEqual(result, 0)
        mock_print.assert_not_called()

    def test_wrong_tool_name_returns_0(self):
        """tool_name outside (Edit, Write) -> returns 0, never reads a file."""
        event = {'tool_name': 'Read', 'tool_input': {'file_path': '/x.py'}}
        with patch('claude.hooks.check_em_dash.json.load', return_value=event), \
             patch('claude.hooks.check_em_dash.os.path.isfile') as mock_isfile, \
             patch('builtins.print') as mock_print:
            result = main()
        self.assertEqual(result, 0)
        mock_isfile.assert_not_called()
        mock_print.assert_not_called()

    def test_missing_file_path_returns_0(self):
        """Event has no file_path -> returns 0."""
        event = {'tool_name': 'Edit', 'tool_input': {}}
        with patch('claude.hooks.check_em_dash.json.load', return_value=event), \
             patch('builtins.print') as mock_print:
            result = main()
        self.assertEqual(result, 0)
        mock_print.assert_not_called()

    def test_extension_not_checked_returns_0(self):
        """File extension outside _CHECKED_EXTENSIONS -> returns 0, never touches disk."""
        event = {'tool_name': 'Edit', 'tool_input': {'file_path': '/x.txt'}}
        with patch('claude.hooks.check_em_dash.json.load', return_value=event), \
             patch('claude.hooks.check_em_dash.os.path.isfile') as mock_isfile, \
             patch('builtins.print') as mock_print:
            result = main()
        self.assertEqual(result, 0)
        mock_isfile.assert_not_called()
        mock_print.assert_not_called()

    def test_file_not_on_disk_returns_0(self):
        """os.path.isfile is False -> returns 0, never opens the file."""
        event = {'tool_name': 'Edit', 'tool_input': {'file_path': '/x.py'}}
        with patch('claude.hooks.check_em_dash.json.load', return_value=event), \
             patch('claude.hooks.check_em_dash.os.path.isfile', return_value=False), \
             patch('builtins.open') as mock_open_fn, \
             patch('builtins.print') as mock_print:
            result = main()
        self.assertEqual(result, 0)
        mock_open_fn.assert_not_called()
        mock_print.assert_not_called()

    def test_file_open_oserror_returns_0_no_print(self):
        """Reading the file raises OSError -> returns 0, never prints."""
        event = {'tool_name': 'Edit', 'tool_input': {'file_path': '/x.py'}}
        with patch('claude.hooks.check_em_dash.json.load', return_value=event), \
             patch('claude.hooks.check_em_dash.os.path.isfile', return_value=True), \
             patch('builtins.open', side_effect=OSError), \
             patch('builtins.print') as mock_print:
            result = main()
        self.assertEqual(result, 0)
        mock_print.assert_not_called()

    def test_file_open_unicode_decode_error_returns_0_no_print(self):
        """Reading the file raises UnicodeDecodeError -> returns 0, never prints."""
        event = {'tool_name': 'Edit', 'tool_input': {'file_path': '/x.py'}}
        decode_error = UnicodeDecodeError('utf-8', b'\xff', 0, 1, 'bad byte')
        with patch('claude.hooks.check_em_dash.json.load', return_value=event), \
             patch('claude.hooks.check_em_dash.os.path.isfile', return_value=True), \
             patch('builtins.open', side_effect=decode_error), \
             patch('builtins.print') as mock_print:
            result = main()
        self.assertEqual(result, 0)
        mock_print.assert_not_called()

    def test_replaces_hits_and_reports_correct_line_list_and_file_path(self):
        """Em dash hits found -> file rewritten, single print with the file path and line list."""
        event = {'tool_name': 'Write', 'tool_input': {'file_path': '/proj/notes.md'}}
        content = f'plain\n{_EM_DASH} bad\nplain\n{_EM_DASH} also bad\n'
        mocked_open = mock_open(read_data=content)
        with patch('claude.hooks.check_em_dash.json.load', return_value=event), \
             patch('claude.hooks.check_em_dash.os.path.isfile', return_value=True), \
             patch('builtins.open', mocked_open), \
             patch('builtins.print') as mock_print:
            result = main()
        self.assertEqual(result, 0)
        mock_print.assert_called_once_with(
            '[check_em_dash] /proj/notes.md: replaced em dash with "-" on line(s) 2, 4')
        write_handle = mocked_open()
        write_handle.writelines.assert_called_once_with(
            ['plain\n', '- bad\n', 'plain\n', '- also bad\n'])

    def test_reports_truncated_hits_with_more_suffix(self):
        """More than 10 hits -> only first 10 listed, with a '(+N more)' suffix."""
        event = {'tool_name': 'Edit', 'tool_input': {'file_path': '/proj/big.py'}}
        content = ''.join(f'{_EM_DASH}\n' for _ in range(12))
        with patch('claude.hooks.check_em_dash.json.load', return_value=event), \
             patch('claude.hooks.check_em_dash.os.path.isfile', return_value=True), \
             patch('builtins.open', mock_open(read_data=content)), \
             patch('builtins.print') as mock_print:
            result = main()
        self.assertEqual(result, 0)
        mock_print.assert_called_once_with(
            '[check_em_dash] /proj/big.py: replaced em dash with "-" on line(s) '
            '1, 2, 3, 4, 5, 6, 7, 8, 9, 10 (+2 more)')

    def test_write_oserror_still_reports_hits(self):
        """Write-back raises OSError -> hits still reported, main still returns 0."""
        event = {'tool_name': 'Edit', 'tool_input': {'file_path': '/proj/notes.md'}}
        content = f'{_EM_DASH}\n'
        with patch('claude.hooks.check_em_dash.json.load', return_value=event), \
             patch('claude.hooks.check_em_dash.os.path.isfile', return_value=True), \
             patch('builtins.open', mock_open(read_data=content)) as mocked_open, \
             patch('builtins.print') as mock_print:
            mocked_open.return_value.writelines.side_effect = OSError
            result = main()
        self.assertEqual(result, 0)
        mock_print.assert_called_once_with(
            '[check_em_dash] /proj/notes.md: replaced em dash with "-" on line(s) 1')


if __name__ == '__main__':
    unittest.main()
