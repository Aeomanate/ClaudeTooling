#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for setup.install_profiles.

~/.bashrc is never touched — _bashrc_path() is always patched to a tempfile.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from setup.install_profiles import (
    _BLOCK_BEGIN,
    _BLOCK_END,
    _strip_existing_block,
    append_to_bashrc,
    write_managed_block,
)

# ===========================================================================
#  _strip_existing_block
# ===========================================================================

class TestStripExistingBlock(unittest.TestCase):
    """_strip_existing_block: pure function, no mocks needed."""

    def test_strips_block_from_middle(self):
        """Lines outside the block are retained; block content removed."""
        lines = [
            'before\n',
            _BLOCK_BEGIN + '\n',
            'export FOO=bar\n',
            _BLOCK_END + '\n',
            'after\n',
        ]
        result = _strip_existing_block(lines)
        self.assertEqual(result, ['before\n', 'after\n'])

    def test_passthrough_when_no_block(self):
        """No managed block -> lines returned unchanged."""
        lines = ['line1\n', 'line2\n']
        self.assertEqual(_strip_existing_block(lines), lines)

    def test_strips_multiple_blocks(self):
        """Two managed blocks both removed (idempotent safety)."""
        lines = [
            _BLOCK_BEGIN + '\n', 'inside1\n', _BLOCK_END + '\n',
            'middle\n',
            _BLOCK_BEGIN + '\n', 'inside2\n', _BLOCK_END + '\n',
        ]
        result = _strip_existing_block(lines)
        self.assertEqual(result, ['middle\n'])

    def test_empty_input(self):
        """Empty line list -> empty result."""
        self.assertEqual(_strip_existing_block([]), [])


# ===========================================================================
#  append_to_bashrc
# ===========================================================================

class TestAppendToBashrc(unittest.TestCase):
    """append_to_bashrc: never writes real ~/.bashrc — _bashrc_path patched."""

    def _bashrc(self, tmp):
        return Path(os.path.join(tmp, '.bashrc'))

    def test_appends_lines_when_not_present(self):
        """Non-existent bashrc created with fence markers and content."""
        with tempfile.TemporaryDirectory() as tmp:
            bashrc = self._bashrc(tmp)
            with patch('setup.install_profiles._bashrc_path', return_value=bashrc):
                append_to_bashrc(['export X=1'])
            content = bashrc.read_text()
        self.assertIn(_BLOCK_BEGIN, content)
        self.assertIn('export X=1', content)
        self.assertIn(_BLOCK_END, content)

    def test_idempotent_when_block_already_present(self):
        """Running twice -> exactly one managed block in output."""
        with tempfile.TemporaryDirectory() as tmp:
            bashrc = self._bashrc(tmp)
            with patch('setup.install_profiles._bashrc_path', return_value=bashrc):
                append_to_bashrc(['export X=1'])
                append_to_bashrc(['export X=2'])
            content = bashrc.read_text()
        self.assertEqual(content.count(_BLOCK_BEGIN), 1)
        self.assertIn('export X=2', content)
        self.assertNotIn('export X=1', content)

    def test_preserves_existing_content_outside_block(self):
        """Pre-existing lines outside the block are retained."""
        with tempfile.TemporaryDirectory() as tmp:
            bashrc = self._bashrc(tmp)
            bashrc.write_text('# my custom line\n')
            with patch('setup.install_profiles._bashrc_path', return_value=bashrc):
                append_to_bashrc(['export Y=2'])
            content = bashrc.read_text()
        self.assertIn('# my custom line', content)
        self.assertIn('export Y=2', content)

    def test_block_has_fence_markers(self):
        """Written block always begins with BLOCK_BEGIN and ends with BLOCK_END."""
        with tempfile.TemporaryDirectory() as tmp:
            bashrc = self._bashrc(tmp)
            with patch('setup.install_profiles._bashrc_path', return_value=bashrc):
                append_to_bashrc(['export Z=3'])
            lines = bashrc.read_text().splitlines()
        begin_idx = lines.index(_BLOCK_BEGIN)
        end_idx = lines.index(_BLOCK_END)
        self.assertLess(begin_idx, end_idx)


# ===========================================================================
#  write_managed_block
# ===========================================================================

class TestWriteManagedBlock(unittest.TestCase):
    """write_managed_block: writes canonical env block — _bashrc_path patched."""

    def _bashrc(self, tmp):
        return Path(os.path.join(tmp, '.bashrc'))

    def test_writes_fence_markers(self):
        """Block always contains BLOCK_BEGIN and BLOCK_END markers."""
        with tempfile.TemporaryDirectory() as tmp:
            bashrc = self._bashrc(tmp)
            with patch('setup.install_profiles._bashrc_path', return_value=bashrc):
                write_managed_block('/src', {})
            content = bashrc.read_text()
        self.assertIn(_BLOCK_BEGIN, content)
        self.assertIn(_BLOCK_END, content)

    def test_includes_ai_tooling_src(self):
        """AI_TOOLING_SRC export line present with correct value."""
        with tempfile.TemporaryDirectory() as tmp:
            bashrc = self._bashrc(tmp)
            with patch('setup.install_profiles._bashrc_path', return_value=bashrc):
                write_managed_block('/my/ai_tooling', {})
            content = bashrc.read_text()
        self.assertIn('export AI_TOOLING_SRC="/my/ai_tooling"', content)

    def test_includes_token_entries(self):
        """JIRA_API_TOKEN, GLAB_TOKEN, ANTHROPIC_AUTH_TOKEN all written."""
        with tempfile.TemporaryDirectory() as tmp:
            bashrc = self._bashrc(tmp)
            tokens = {
                'JIRA_API_TOKEN': 'jt',
                'GLAB_TOKEN': 'gt',
                'ANTHROPIC_AUTH_TOKEN': 'ak',
            }
            with patch('setup.install_profiles._bashrc_path', return_value=bashrc):
                write_managed_block('/src', tokens)
            content = bashrc.read_text()
        self.assertIn('export JIRA_API_TOKEN="jt"', content)
        self.assertIn('export GLAB_TOKEN="gt"', content)
        self.assertIn('export ANTHROPIC_AUTH_TOKEN="ak"', content)

    def test_idempotent_replaces_existing_block(self):
        """Calling twice -> exactly one managed block with latest values."""
        with tempfile.TemporaryDirectory() as tmp:
            bashrc = self._bashrc(tmp)
            with patch('setup.install_profiles._bashrc_path', return_value=bashrc):
                write_managed_block('/src', {'GLAB_TOKEN': 'first'})
                write_managed_block('/src', {'GLAB_TOKEN': 'second'})
            content = bashrc.read_text()
        self.assertEqual(content.count(_BLOCK_BEGIN), 1)
        self.assertIn('"second"', content)
        self.assertNotIn('"first"', content)

    def test_preserves_existing_tokens_on_second_run(self):
        """Tokens present in the first write are preserved when absent from the second."""
        with tempfile.TemporaryDirectory() as tmp:
            bashrc = self._bashrc(tmp)
            first_tokens = {
                'JIRA_API_TOKEN': 'jira-val',
                'GLAB_TOKEN': 'glab-val',
                'ANTHROPIC_AUTH_TOKEN': 'anthropic-val',
            }
            second_tokens = {
                'JIRA_API_TOKEN': 'jira-new',
            }
            with patch('setup.install_profiles._bashrc_path', return_value=bashrc):
                write_managed_block('/src', first_tokens)
                write_managed_block('/src', second_tokens)
            content = bashrc.read_text()
        self.assertIn('export JIRA_API_TOKEN="jira-new"', content)
        self.assertIn('export GLAB_TOKEN="glab-val"', content)
        self.assertIn('export ANTHROPIC_AUTH_TOKEN="anthropic-val"', content)


if __name__ == '__main__':
    unittest.main()
