#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for git_hooks_impl.entry_points.commands.registry.

registry.run() has no external dependencies of its own — it only reads the
module-level REGISTRY dict and dispatches to whichever callable is stored
there, so tests substitute REGISTRY directly instead of mocking a function.
"""

import io
import unittest
from contextlib import redirect_stderr
from unittest.mock import MagicMock, patch

from git_hooks_impl.entry_points.commands import registry


class TestRegistryRunKnownCommand(unittest.TestCase):
    """run(): a registered name dispatches to its callable with argv."""

    @patch.dict(registry.REGISTRY, {
        'lint': {'callable': MagicMock(return_value=0), 'audience': 'dev', 'help': 'run lint'},
    }, clear=True)
    def test_known_command_forwards_argv_and_returns_its_code(self):
        """Registered name -> its callable is invoked with argv, exit code passed through."""
        registry.REGISTRY['lint']['callable'].return_value = 3
        result = registry.run('lint', ['--fix'])
        registry.REGISTRY['lint']['callable'].assert_called_once_with(['--fix'])
        self.assertEqual(result, 3)


class TestRegistryRunUnknownCommand(unittest.TestCase):
    """run(): an unknown name prints the registry listing to stderr and returns 1."""

    @patch.dict(registry.REGISTRY, {}, clear=True)
    def test_unknown_command_with_empty_registry_returns_1(self):
        """No commands registered -> returns 1, notes the empty registry on stderr."""
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = registry.run('missing', [])
        self.assertEqual(result, 1)
        self.assertIn('No commands registered yet.', stderr.getvalue())

    @patch.dict(registry.REGISTRY, {
        'lint': {'callable': MagicMock(), 'audience': 'dev', 'help': 'dev-only lint'},
        'setup': {'callable': MagicMock(), 'audience': 'user', 'help': 'user-facing setup'},
    }, clear=True)
    def test_unknown_command_lists_both_audiences_on_stderr(self):
        """Unknown name with a populated registry -> both dev and user groups listed."""
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = registry.run('missing', [])
        output = stderr.getvalue()
        self.assertEqual(result, 1)
        self.assertIn('dev:', output)
        self.assertIn('user:', output)
        self.assertIn('lint', output)
        self.assertIn('setup', output)


class TestRegistryRunNoName(unittest.TestCase):
    """run(None, ...): 'mr script' with no name is a deliberate listing request, not an error."""

    @patch.dict(registry.REGISTRY, {
        'lint': {'callable': MagicMock(), 'audience': 'dev', 'help': 'run lint'},
    }, clear=True)
    def test_no_name_lists_commands_and_returns_0(self):
        """No name at all -> prints the listing, returns 0 (not 1 - not a mistake)."""
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = registry.run(None, [])
        self.assertEqual(result, 0)
        self.assertIn('lint', stderr.getvalue())

    @patch.dict(registry.REGISTRY, {
        'lint': {'callable': MagicMock(), 'audience': 'dev', 'help': 'run lint'},
    }, clear=True)
    def test_no_name_does_not_print_unknown_command_line(self):
        """No name -> no 'Unknown script command' line (that's only for a real bad name)."""
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            registry.run(None, [])
        self.assertNotIn('Unknown script command', stderr.getvalue())


if __name__ == '__main__':
    unittest.main()
