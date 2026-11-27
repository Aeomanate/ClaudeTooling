#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for hooks/logger.py — log/ok/warn/err real execution,
_caller_info classmethod branch.

These tests exercise the actual log functions (not silenced by module-level
patchers). _file_write is patched to prevent real file I/O, while stderr
output is captured to verify it was written.

Run:  python -m unittest discover -s .git-hooks/hooks/tests -t .git-hooks -p "test_logger.py" -v
"""

import unittest
from unittest.mock import MagicMock, patch

from git_hooks_impl.logger import (
    _console_prefix,
    _file_prefix,
    _log_context,
    config,
    console_tag,
    dbg,
    err,
    log,
    ok,
    warn,
)

# ---------------------------------------------------------------------------
#  log, ok, warn, err — real execution with _file_write patched
# ---------------------------------------------------------------------------

class TestLogFunctions(unittest.TestCase):
    """Verify log/ok/warn/err write to stderr AND call _file_write."""

    @patch('git_hooks_impl.logger._file_write')
    def test_log_writes_to_stderr_and_file(self, mock_fw):
        """log('hello') -> stderr output + _file_write called once.

        Function under test: log()
        """
        with patch('git_hooks_impl.logger.sys.stderr') as mock_stderr:
            mock_stderr.write = MagicMock()
            mock_stderr.flush = MagicMock()
            log('hello world')

        mock_fw.assert_called_once()
        file_line = mock_fw.call_args[0][0]
        self.assertIn('hello world', file_line)
        # stderr was written to (via _stderr_print)
        mock_stderr.write.assert_called()
        stderr_text = mock_stderr.write.call_args[0][0]
        self.assertIn('hello world', stderr_text)

    @patch('git_hooks_impl.logger._file_write')
    def test_ok_writes_to_stderr_and_file(self, mock_fw):
        """ok('success') -> stderr output + _file_write called once.

        Function under test: ok()
        """
        with patch('git_hooks_impl.logger.sys.stderr') as mock_stderr:
            mock_stderr.write = MagicMock()
            mock_stderr.flush = MagicMock()
            ok('success message')

        mock_fw.assert_called_once()
        file_line = mock_fw.call_args[0][0]
        self.assertIn('success message', file_line)
        mock_stderr.write.assert_called()

    @patch('git_hooks_impl.logger._file_write')
    def test_warn_writes_to_stderr_and_file(self, mock_fw):
        """warn('caution') -> stderr output + _file_write called once.

        Function under test: warn()
        """
        with patch('git_hooks_impl.logger.sys.stderr') as mock_stderr:
            mock_stderr.write = MagicMock()
            mock_stderr.flush = MagicMock()
            warn('caution note')

        mock_fw.assert_called_once()
        file_line = mock_fw.call_args[0][0]
        self.assertIn('caution note', file_line)
        mock_stderr.write.assert_called()

    @patch('git_hooks_impl.logger._file_write')
    def test_err_writes_to_stderr_and_file(self, mock_fw):
        """err('failure') -> stderr output + _file_write called once.

        Function under test: err()
        """
        with patch('git_hooks_impl.logger.sys.stderr') as mock_stderr:
            mock_stderr.write = MagicMock()
            mock_stderr.flush = MagicMock()
            err('failure occurred')

        mock_fw.assert_called_once()
        file_line = mock_fw.call_args[0][0]
        self.assertIn('failure occurred', file_line)
        mock_stderr.write.assert_called()

    @patch('git_hooks_impl.logger._file_write')
    def test_dbg_writes_file_only_not_stderr(self, mock_fw):
        """dbg('trace') -> _file_write called but NO stderr output.

        dbg() is file-only: no _stderr_print call.

        Function under test: dbg()
        """
        with patch('git_hooks_impl.logger._stderr_print') as mock_stderr_print:
            dbg('trace info')

        mock_fw.assert_called_once()
        file_line = mock_fw.call_args[0][0]
        self.assertIn('trace info', file_line)
        mock_stderr_print.assert_not_called()

    @patch('git_hooks_impl.logger._file_write')
    def test_log_includes_caller_filename(self, mock_fw):
        """log() output includes the caller's filename in the prefix.

        Called from test_logger.py -> prefix contains 'test_logger.py'.

        Function under test: log()
        """
        with patch('git_hooks_impl.logger.sys.stderr') as mock_stderr:
            mock_stderr.write = MagicMock()
            mock_stderr.flush = MagicMock()
            log('check caller')

        file_line = mock_fw.call_args[0][0]
        self.assertIn('test_logger.py', file_line)


# ---------------------------------------------------------------------------
#  _caller_info — classmethod branch
# ---------------------------------------------------------------------------

class TestCallerInfo(unittest.TestCase):
    """Verify _caller_info() detects instance methods, classmethods, and
    plain functions correctly.
    """

    def test_plain_function_caller_detected(self):
        """log() called from a plain function -> _file_write prefix has no class.

        When log() is called from module-level or a plain function (not a
        method), _caller_info returns class_name=None, so no [ClassName]
        bracket appears in the prefix.

        Function under test: _caller_info() via log()
        """
        def plain_helper():
            log('from plain function')

        with patch('git_hooks_impl.logger._file_write') as mock_fw, \
             patch('git_hooks_impl.logger.sys.stderr') as mock_stderr:
            mock_stderr.write = MagicMock()
            mock_stderr.flush = MagicMock()
            plain_helper()

        file_line = mock_fw.call_args[0][0]
        self.assertIn('[plain_helper]', file_line)
        # No class bracket between filename and function name
        self.assertNotIn('[TestCallerInfo]', file_line)

    def test_instance_method_caller_detected(self):
        """log() called from an instance method -> prefix includes [ClassName].

        _caller_info reads frame.f_locals['self'] to find the class.
        Called from TestCallerInfo.test_instance_method_caller_detected.

        Function under test: _caller_info() via log()
        """
        with patch('git_hooks_impl.logger._file_write') as mock_fw, \
             patch('git_hooks_impl.logger.sys.stderr') as mock_stderr:
            mock_stderr.write = MagicMock()
            mock_stderr.flush = MagicMock()
            log('from instance method')

        file_line = mock_fw.call_args[0][0]
        self.assertIn('[TestCallerInfo]', file_line)
        self.assertIn('[test_instance_method_caller_detected]', file_line)

    def test_classmethod_caller_detected(self):
        """log() called from a classmethod -> prefix includes class name from 'cls'.

        _caller_info reads frame.f_locals['cls'] for classmethods.

        Function under test: _caller_info() via log()
        """
        class _Helper:
            @classmethod
            def log_from_classmethod(cls):
                log('from classmethod')

        with patch('git_hooks_impl.logger._file_write') as mock_fw, \
             patch('git_hooks_impl.logger.sys.stderr') as mock_stderr:
            mock_stderr.write = MagicMock()
            mock_stderr.flush = MagicMock()
            _Helper.log_from_classmethod()

        file_line = mock_fw.call_args[0][0]
        self.assertIn('[_Helper]', file_line)
        self.assertIn('[log_from_classmethod]', file_line)

    def test_caller_info_returns_filename_with_extension(self):
        """log() called from test file -> prefix includes 'test_logger.py'.

        Function under test: _caller_info() via log()
        """
        with patch('git_hooks_impl.logger._file_write') as mock_fw, \
             patch('git_hooks_impl.logger.sys.stderr') as mock_stderr:
            mock_stderr.write = MagicMock()
            mock_stderr.flush = MagicMock()
            log('check filename')

        file_line = mock_fw.call_args[0][0]
        self.assertIn('test_logger.py', file_line)


# ---------------------------------------------------------------------------
#  _log_context — metadata prefix formatting
# ---------------------------------------------------------------------------

class TestLogContext(unittest.TestCase):
    """Verify _log_context builds correct prefix strings."""

    def test_includes_timestamp_and_filename(self):
        """Basic prefix: [timestamp] [filename] [function].

        Function under test: _log_context()
        """
        result = _log_context('module.py', None, 'my_func', '')
        self.assertIn('[module.py]', result)
        self.assertIn('[my_func]', result)

    def test_includes_class_name_when_present(self):
        """Class name present -> [class_name] appears in prefix.

        Function under test: _log_context()
        """
        result = _log_context('module.py', 'MyClass', 'my_method', '')
        self.assertIn('[MyClass]', result)


# ---------------------------------------------------------------------------
#  Split console/file formatters
# ---------------------------------------------------------------------------

class TestConsolePrefixFormat(unittest.TestCase):
    """_console_prefix returns [command] or [mr] fallback."""

    def test_command_set_returns_command_bracket(self):
        """_console_prefix('sync') -> '[sync]'."""
        self.assertEqual(_console_prefix('sync'), '[sync]')

    def test_empty_command_returns_mr_fallback(self):
        """_console_prefix('') -> '[mr]'."""
        self.assertEqual(_console_prefix(''), '[mr]')

    def test_none_like_falsy_returns_mr_fallback(self):
        """_console_prefix(None) -> '[mr]' (falsy input)."""
        self.assertEqual(_console_prefix(None), '[mr]')


class TestConsoleTag(unittest.TestCase):
    """console_tag() -> _console_prefix(config.command)."""

    def setUp(self):
        self._saved_command = config.command

    def tearDown(self):
        config.command = self._saved_command

    def test_command_set_returns_command_bracket(self):
        """config.command = 'plangen' -> console_tag() -> '[plangen]'."""
        config.command = 'plangen'
        self.assertEqual(console_tag(), '[plangen]')

    def test_empty_command_returns_mr_fallback(self):
        """config.command = '' -> console_tag() -> '[mr]'."""
        config.command = ''
        self.assertEqual(console_tag(), '[mr]')


class TestFilePrefixFormat(unittest.TestCase):
    """_file_prefix returns full [timestamp] [file] [class?] [func] [command?] prefix."""

    def test_includes_timestamp_and_filename_and_func(self):
        """Full prefix without class or command."""
        result = _file_prefix('sync_mr.py', None, 'update_mr', '')
        self.assertIn('[sync_mr.py]', result)
        self.assertIn('[update_mr]', result)

    def test_includes_class_when_present(self):
        """Class name brackets present when provided."""
        result = _file_prefix('sync_mr.py', 'MyClass', 'my_method', '')
        self.assertIn('[MyClass]', result)

    def test_includes_command_when_set(self):
        """Command bracket appended when non-empty."""
        result = _file_prefix('sync_mr.py', None, 'my_func', 'sync')
        self.assertIn('[sync]', result)

    def test_omits_command_when_empty(self):
        """No command bracket when command is empty."""
        result = _file_prefix('sync_mr.py', None, 'my_func', '')
        self.assertNotIn('[mr]', result)


class TestSplitFormatterIntegration(unittest.TestCase):
    """log/ok/warn/err use short console prefix and full file prefix."""

    @patch('git_hooks_impl.logger._file_write')
    def test_log_console_shows_command_only(self, mock_fw):
        """log() -> stderr shows [command] short prefix; file gets full prefix."""
        old_cmd = config.command
        config.command = 'plangen'
        try:
            with patch('git_hooks_impl.logger.sys.stderr') as mock_stderr:
                mock_stderr.write = MagicMock()
                mock_stderr.flush = MagicMock()
                log('building plan')
        finally:
            config.command = old_cmd

        stderr_text = mock_stderr.write.call_args[0][0]
        self.assertIn('[plangen]', stderr_text)
        self.assertIn('building plan', stderr_text)
        # Full timestamp/filename NOT in console output
        self.assertNotIn('logger.py', stderr_text)

        file_line = mock_fw.call_args[0][0]
        self.assertIn('building plan', file_line)
        # Full prefix IS in file log
        self.assertIn('[plangen]', file_line)
        self.assertIn('test_logger.py', file_line)

    @patch('git_hooks_impl.logger._file_write')
    def test_log_console_fallback_to_mr_when_no_command(self, mock_fw):
        """log() with no command set -> console shows [mr] fallback."""
        old_cmd = config.command
        config.command = ''
        try:
            with patch('git_hooks_impl.logger.sys.stderr') as mock_stderr:
                mock_stderr.write = MagicMock()
                mock_stderr.flush = MagicMock()
                log('no command set')
        finally:
            config.command = old_cmd

        stderr_text = mock_stderr.write.call_args[0][0]
        self.assertIn('[mr]', stderr_text)



# ---------------------------------------------------------------------------
#  Run all
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    unittest.main(verbosity=2)
