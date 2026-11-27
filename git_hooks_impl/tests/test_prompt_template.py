#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for plan/prompt_template.py — PromptTemplate load + render + validation.

Covers R3 (missing/unused kwarg errors), B24 (braces in value not flagged),
B25 (fenced code block exclusion).

Run: python -m unittest discover -s .git-hooks/hooks/tests -t .git-hooks -p "test_prompt_template.py" -v
"""

import unittest

from git_hooks_impl.plan.prompt_template import PromptTemplate, PromptTemplateError


class TestPromptTemplateRender(unittest.TestCase):
    """PromptTemplate: placeholder substitution and validation."""

    def test_render_substitutes_all_placeholders(self):
        """All {{KEY}} placeholders replaced with supplied kwarg values."""
        tmpl = PromptTemplate('Hello {{NAME}}, you have {{COUNT}} messages.')
        result = tmpl.render(NAME='Alice', COUNT='3')
        self.assertEqual(result, 'Hello Alice, you have 3 messages.')

    def test_prompt_template_missing_placeholder_raises(self):
        """Supply kwargs missing one placeholder -> PromptTemplateError (R3)."""
        tmpl = PromptTemplate('{{A}} and {{B}}')
        with self.assertRaises(PromptTemplateError) as ctx:
            tmpl.render(A='only_a')
        self.assertIn('B', str(ctx.exception))

    def test_prompt_template_unused_kwarg_raises(self):
        """Supply a kwarg with no matching placeholder -> PromptTemplateError (R3)."""
        tmpl = PromptTemplate('{{A}} text')
        with self.assertRaises(PromptTemplateError) as ctx:
            tmpl.render(A='val', EXTRA='unused')
        self.assertIn('EXTRA', str(ctx.exception))

    def test_prompt_template_braces_in_value_not_flagged(self):
        """Substituted value contains literal {{X}} -> no error, value passed through (B24)."""
        tmpl = PromptTemplate('prefix {{CONTENT}} suffix')
        result = tmpl.render(CONTENT='value with {{X}} inside')
        self.assertEqual(result, 'prefix value with {{X}} inside suffix')

    def test_fenced_block_placeholders_excluded(self):
        """Placeholders inside ``` fences not counted as real -> no missing kwarg error (B25)."""
        text = 'Use {{REAL}} here.\n```\n{{EXAMPLE_IN_FENCE}}\n```\nDone.'
        tmpl = PromptTemplate(text)
        result = tmpl.render(REAL='value')
        self.assertIn('value', result)

    def test_render_no_placeholders_no_kwargs(self):
        """Template with no placeholders and no kwargs -> renders unchanged."""
        tmpl = PromptTemplate('Static text only.')
        result = tmpl.render()
        self.assertEqual(result, 'Static text only.')

    def test_render_empty_string_value(self):
        """Empty string value substituted correctly."""
        tmpl = PromptTemplate('{{A}}{{B}}')
        result = tmpl.render(A='', B='hello')
        self.assertEqual(result, 'hello')

    def test_error_message_lists_all_missing(self):
        """Missing-kwarg error names all unresolved placeholders."""
        tmpl = PromptTemplate('{{A}} {{B}} {{C}}')
        with self.assertRaises(PromptTemplateError) as ctx:
            tmpl.render(A='x')
        msg = str(ctx.exception)
        self.assertIn('B', msg)
        self.assertIn('C', msg)

    def test_error_message_lists_all_unused(self):
        """Unused-kwarg error names all surplus kwargs."""
        tmpl = PromptTemplate('{{A}}')
        with self.assertRaises(PromptTemplateError) as ctx:
            tmpl.render(A='x', EXTRA1='y', EXTRA2='z')
        msg = str(ctx.exception)
        self.assertIn('EXTRA1', msg)
        self.assertIn('EXTRA2', msg)

    def test_filename_preserved_on_instance(self):
        """Filename kwarg stored and appears in error messages."""
        tmpl = PromptTemplate('{{X}}', filename='my_template.md')
        with self.assertRaises(PromptTemplateError) as ctx:
            tmpl.render()
        self.assertIn('my_template.md', str(ctx.exception))


class TestPromptTemplateLoad(unittest.TestCase):
    """PromptTemplate.load() reads from prompt_templates/PlanGen/."""

    def test_load_step1_fill_body(self):
        """load('step1_fill_body.md') returns a PromptTemplate with expected placeholders."""
        tmpl = PromptTemplate.load('step1_fill_body.md')
        self.assertIsInstance(tmpl, PromptTemplate)
        # step1_fill_body.md should have MR_BODY_TEMPLATE, JIRA_CONTENT etc.
        self.assertIn('MR_BODY_TEMPLATE', tmpl._template_placeholders)
        self.assertIn('JIRA_CONTENT', tmpl._template_placeholders)

    def test_load_nonexistent_raises(self):
        """load() on a missing file raises OSError/FileNotFoundError."""
        with self.assertRaises(OSError):
            PromptTemplate.load('nonexistent_file_xyz.md')
