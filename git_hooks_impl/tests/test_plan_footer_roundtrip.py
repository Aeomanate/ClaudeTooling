#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Round-trip guard tests for the plan-footer projection: plan content maps to
an MR description via the real create_mr()/update_mr() assembly, and the
pull path must reconstruct byte-identical plan content from that description.

Run:  python -m unittest discover -s .git-hooks/hooks/tests -t .git-hooks -p "test_plan_footer_roundtrip.py" -v
"""

import unittest

from git_hooks_impl.branch_utils import body_was_edited, visible_body_for_reconstruction
from git_hooks_impl.plan.parser import (
    canonical_plan,
    extract_footer_meta,
    plan_footer,
    plan_was_edited_on_mr,
    reconstruct_plan_content,
    visible_plan_body,
)
from git_hooks_impl.tests.utils import build_full_mr_description


class TestPlanFooterRoundtrip(unittest.TestCase):

    def test_round_trip_exact(self):
        """Canonical plan -> description -> reconstructed plan, byte-identical."""
        plan = (
            '# My Feature\n\n'
            '## Context\n\nBackground.\n\n'
            '## Implementation Plan\n\n- [ ] Step 1\n'
        )
        desc = build_full_mr_description(plan)

        footer_meta = extract_footer_meta(desc)
        body = visible_body_for_reconstruction(desc)
        reconstructed = reconstruct_plan_content(footer_meta, body)

        self.assertEqual(reconstructed, canonical_plan(plan))
        self.assertFalse(plan_was_edited_on_mr(reconstructed))

    def test_non_canonical_input_converges(self):
        """Title not on line 1, no blank line after it -> canonical_plan()
        fixes both, is idempotent, and still round-trips exactly.
        """
        raw = 'Some preamble line\n# Title\n## Context\ntext\n'
        canon1 = canonical_plan(raw)
        canon2 = canonical_plan(canon1)
        self.assertEqual(canon1, canon2)

        desc = build_full_mr_description(canon1)
        footer_meta = extract_footer_meta(desc)
        body = visible_body_for_reconstruction(desc)
        reconstructed = reconstruct_plan_content(footer_meta, body)

        self.assertEqual(reconstructed, canon1)

    def test_no_footer_without_plan_body(self):
        """Empty visible body -> no footer, no footer meta on pull."""
        self.assertEqual(visible_plan_body(''), '')
        self.assertEqual(plan_footer(''), '')
        self.assertIsNone(extract_footer_meta(''))

    def test_checklist_containment_round_trip(self):
        """Existing MR ## Checklist survives push/pull/push unchanged and
        never leaks into the reconstructed plan content.
        """
        plan = '# Feature\n\n## Context\n\nBackground.\n'
        existing_body = '## Description\n\nSome text\n\n## Checklist\n- [ ] Item one'

        desc1 = build_full_mr_description(plan, clean_body=existing_body)
        self.assertEqual(desc1.count('## Checklist'), 1)

        footer_meta = extract_footer_meta(desc1)
        body = visible_body_for_reconstruction(desc1)
        reconstructed = reconstruct_plan_content(footer_meta, body)
        self.assertNotIn('## Checklist', reconstructed)

        edited, clean_body2 = body_was_edited(desc1)
        self.assertFalse(edited)
        desc2 = build_full_mr_description(plan, clean_body=clean_body2)

        self.assertEqual(desc2.count('## Checklist'), 1)
        self.assertEqual(desc2, desc1)

    def test_meta_passthrough(self):
        """A non-standard meta key (e.g. claude-timing) survives the round trip."""
        plan = '<!-- meta\nclaude-timing: 21.3,9.5\n-->\n# Feature\n\n## Context\n\nText.\n'
        desc = build_full_mr_description(plan)

        footer_meta = extract_footer_meta(desc)
        self.assertEqual(footer_meta.get('claude-timing'), '21.3,9.5')

        body = visible_body_for_reconstruction(desc)
        reconstructed = reconstruct_plan_content(footer_meta, body)
        self.assertIn('claude-timing: 21.3,9.5', reconstructed)

    def test_discussions_rendered_once(self):
        """The description contains exactly one ## Discussions section."""
        plan = (
            '# Feature\n\n'
            '## Context\n\nText.\n\n'
            '## Discussions\n\n'
            '### Topic\n\nBody.\n\n'
            '<!-- /discussions -->\n'
        )
        desc = build_full_mr_description(plan)
        self.assertEqual(desc.count('## Discussions'), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
