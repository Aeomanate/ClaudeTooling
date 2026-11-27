#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for prompt_templates/plan_template.md — structural assertions.

Verifies section ordering and that Architecture is not wrapped in <details>.

Run: python -m unittest discover -s .git-hooks/hooks/tests -t .git-hooks -p "test_plan_template.py" -v
"""

import os
import unittest

_TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'prompt_templates',
    'plan_template.md',
)


def _load_template_lines():
    with open(_TEMPLATE_PATH, encoding='utf-8') as f:
        return f.readlines()


class TestPlanTemplateStructure(unittest.TestCase):
    """Structural assertions on plan_template.md."""

    def setUp(self):
        self._lines = _load_template_lines()
        self._text = ''.join(self._lines)

    def _line_number(self, pattern):
        """Return 1-based line number of first line containing pattern, or None."""
        for i, line in enumerate(self._lines, 1):
            if pattern in line:
                return i
        return None

    def test_architecture_not_inside_details(self):
        """## Architecture must NOT be inside a <details> block."""
        arch_line = self._line_number('## Architecture')
        self.assertIsNotNone(arch_line, '## Architecture section not found')
        # Check 10 lines before Architecture for a <details> open tag
        start = max(0, arch_line - 11)
        preceding = self._lines[start:arch_line - 1]
        details_opens = [line for line in preceding if '<details>' in line]
        self.assertEqual(
            details_opens, [],
            f'## Architecture appears inside a <details> block. Found: {details_opens}',
        )

    def test_architecture_section_present(self):
        """Template contains ## Architecture heading."""
        self.assertIn('## Architecture', self._text)

    def test_discussions_section_present(self):
        """Template contains <!-- /discussions --> marker."""
        self.assertIn('<!-- /discussions -->', self._text)
