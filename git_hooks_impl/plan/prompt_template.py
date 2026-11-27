#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""PromptTemplate — load + render prompt template files with placeholder validation.

Raises PromptTemplateError when:
- A {{PLACEHOLDER}} in the template was not supplied as a kwarg (missing substitution).
- A kwarg was supplied but no matching {{PLACEHOLDER}} exists in the template (unused kwarg).

The check is performed on the TEMPLATE text (pre-render), not the rendered output,
so substituted values that happen to contain literal '{{' are fine (B24).

Fenced code blocks (``` ... ```) in the template are excluded from the placeholder
check — documentation examples that show '{{X}}' syntax are not treated as real
placeholders (B25).
"""

import os
import re


class PromptTemplateError(Exception):
    """Raised on placeholder mismatch during render()."""


_PROMPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'prompt_templates',
    'PlanGen',
)

# Matches {{ IDENTIFIER }} placeholders (upper or lower, underscores allowed).
_PLACEHOLDER_RE = re.compile(r'\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}')

# Matches fenced code blocks: opening ``` (optional lang) through closing ```.
_FENCED_BLOCK_RE = re.compile(r'```[^\n]*\n.*?```', re.DOTALL)


def _strip_fenced_blocks(text: str) -> str:
    """Replace fenced code block contents with empty fences for placeholder scanning."""
    return _FENCED_BLOCK_RE.sub('```\n```', text)


class PromptTemplate:
    """Immutable loaded prompt template with validated render."""

    def __init__(self, text: str, filename: str = ''):
        self._text = text
        self._filename = filename

        # Pre-compute the set of placeholder names in the template (outside fences).
        scannable = _strip_fenced_blocks(text)
        self._template_placeholders = frozenset(
            m.group(1) for m in _PLACEHOLDER_RE.finditer(scannable)
        )

    @classmethod
    def load(cls, filename: str) -> 'PromptTemplate':
        """Load a template from prompt_templates/PlanGen/<filename>."""
        path = os.path.join(_PROMPTS_DIR, filename)
        with open(path, encoding='utf-8') as f:
            text = f.read()
        return cls(text, filename=filename)

    def render(self, **kwargs) -> str:
        """Substitute all {{KEY}} placeholders with kwargs values.

        Raises PromptTemplateError when:
        - A template placeholder has no matching kwarg.
        - A kwarg has no matching template placeholder.
        """
        missing = self._template_placeholders - kwargs.keys()
        unused = kwargs.keys() - self._template_placeholders

        if missing or unused:
            parts = []
            if missing:
                parts.append(f'missing kwargs for placeholders: {sorted(missing)}')
            if unused:
                parts.append(f'kwargs with no matching placeholder: {sorted(unused)}')
            raise PromptTemplateError(
                f"PromptTemplate({self._filename!r}): {'; '.join(parts)}"
            )

        result = self._text
        for key, value in kwargs.items():
            result = result.replace('{{' + key + '}}', str(value))
        return result
