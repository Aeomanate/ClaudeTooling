#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for git_hooks_impl.entry_points.commands.test_timings.

run()'s direct dependency is collect_timings(), mocked at the module
import location per the Main Mock Rule - it is the only thing that
actually runs the suite, and running the real suite from inside a test
of the real suite would recurse.
"""

import contextlib
import io
import unittest
from unittest.mock import patch

from git_hooks_impl.entry_points.commands import test_timings

_FAKE_TIMINGS = [
    (0.5, 'test_a (mod.TestA)'),
    (2.5, 'test_b (mod.TestB)'),
    (1.5, 'test_c (mod.TestC)'),
]


class TestRun(unittest.TestCase):

    def _run_and_capture(self, argv=None):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = test_timings.run(argv or [])
        return result, buf.getvalue()

    @patch('git_hooks_impl.entry_points.commands.test_timings.collect_timings')
    def test_sorts_slowest_first(self, mock_collect):
        mock_collect.return_value = list(_FAKE_TIMINGS)
        result, output = self._run_and_capture()
        self.assertEqual(result, 0)
        b_pos = output.index('test_b')
        c_pos = output.index('test_c')
        a_pos = output.index('test_a')
        self.assertLess(b_pos, c_pos)
        self.assertLess(c_pos, a_pos)

    @patch('git_hooks_impl.entry_points.commands.test_timings.collect_timings')
    def test_n_argument_limits_output(self, mock_collect):
        mock_collect.return_value = list(_FAKE_TIMINGS)
        result, output = self._run_and_capture(['1'])
        self.assertEqual(result, 0)
        self.assertIn('test_b', output)
        self.assertNotIn('test_c', output)
        self.assertNotIn('test_a', output)

    @patch('git_hooks_impl.entry_points.commands.test_timings.collect_timings')
    def test_non_numeric_argument_returns_1(self, mock_collect):
        result, _ = self._run_and_capture(['not-a-number'])
        self.assertEqual(result, 1)
        mock_collect.assert_not_called()

    def test_help_flag_returns_0_without_running_suite(self):
        with patch(
            'git_hooks_impl.entry_points.commands.test_timings.collect_timings'
        ) as mock_collect:
            result, _ = self._run_and_capture(['--help'])
            self.assertEqual(result, 0)
            mock_collect.assert_not_called()


if __name__ == '__main__':
    unittest.main()
