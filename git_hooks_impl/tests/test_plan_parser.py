#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for hooks/plan_parser.py — meta block parsing,
plan/body hash computation, section formatting, hidden-block strip, and discussion parsing.

Run:  python -m unittest discover -s .git-hooks/hooks/tests -t .git-hooks -p "test_plan_parser.py" -v
"""

import unittest
from unittest.mock import patch

from git_hooks_impl.plan.parser import (
    compute_body_hash,
    compute_plan_hash,
    embed_meta,
    embed_plan_hash,
    extract_body_hash,
    extract_meta,
    extract_plan_hash,
    find_unposted_discussions,
    plan_was_edited_on_mr,
    replace_visible_body,
    strip_meta,
    visible_plan_body,
)

# ---------------------------------------------------------------------------
#  Module-level log silencing — prevent TESTS.log pollution
# ---------------------------------------------------------------------------

_log_patchers = []

def setUpModule():
    targets = [
        'git_hooks_impl.plan.parser.dbg',
    ]
    for t in targets:
        p = patch(t)
        p.start()
        _log_patchers.append(p)

def tearDownModule():
    for p in _log_patchers:
        p.stop()
    _log_patchers.clear()


# ---------------------------------------------------------------------------
#  Meta block — parsing, embedding, stripping
# ---------------------------------------------------------------------------

class TestMetaBlock(unittest.TestCase):

    def test_extract_meta_parses_all_keys(self):
        """'<!-- meta\\nplan-hash: abc\\nbody-hash: def\\n-->' -> {'plan-hash': 'abc', 'body-hash': 'def'}."""
        content = '<!-- meta\nplan-hash: abc\nbody-hash: def\n-->\n# Title'
        meta = extract_meta(content)
        self.assertEqual(meta, {'plan-hash': 'abc', 'body-hash': 'def'})

    def test_extract_meta_returns_empty_dict_without_block(self):
        """No meta block -> {}."""
        self.assertEqual(extract_meta('# Title\n## Context'), {})

    def test_extract_meta_handles_timing(self):
        """'<!-- meta\\nclaude-timing: 21.3,9.5\\n-->' -> {'claude-timing': '21.3,9.5'}."""
        content = '<!-- meta\nclaude-timing: 21.3,9.5\n-->\n# Title'
        meta = extract_meta(content)
        self.assertEqual(meta['claude-timing'], '21.3,9.5')

    def test_embed_meta_creates_block(self):
        """embed_meta('# Title', **{'plan-hash': 'abc'}) -> meta block + content."""
        result = embed_meta('# Title', **{'plan-hash': 'abc'})
        self.assertIn('<!-- meta\n', result)
        self.assertIn('plan-hash: abc', result)
        self.assertIn('-->', result)
        self.assertIn('# Title', result)

    def test_embed_meta_merges_with_existing(self):
        """Existing meta keys preserved when adding new ones.
        '<!-- meta\\ntiming: 1.0\\n-->\\n# T' + body-hash: x -> both in output.
        """
        content = '<!-- meta\ntiming: 1.0\n-->\n# T'
        result = embed_meta(content, **{'body-hash': 'x'})
        meta = extract_meta(result)
        self.assertEqual(meta['timing'], '1.0')
        self.assertEqual(meta['body-hash'], 'x')

    def test_embed_meta_overwrites_existing_key(self):
        """Updating an existing key replaces its value.
        '<!-- meta\\nplan-hash: old\\n-->' + plan-hash: new -> 'new'.
        """
        content = '<!-- meta\nplan-hash: old\n-->\n# T'
        result = embed_meta(content, **{'plan-hash': 'new'})
        meta = extract_meta(result)
        self.assertEqual(meta['plan-hash'], 'new')

    def test_embed_meta_removes_none_values(self):
        """Key with None value is removed from meta block.
        {'a': '1', 'b': None} -> only 'a' in output.
        """
        content = '<!-- meta\na: 1\nb: 2\n-->\n# T'
        result = embed_meta(content, b=None)
        meta = extract_meta(result)
        self.assertIn('a', meta)
        self.assertNotIn('b', meta)

    def test_strip_meta_removes_block(self):
        """'<!-- meta\\nplan-hash: abc\\n-->\\n# Title' -> '# Title'."""
        content = '<!-- meta\nplan-hash: abc\n-->\n# Title'
        self.assertEqual(strip_meta(content), '# Title')

    def test_strip_meta_normalizes_whitespace(self):
        """Collapses 3+ consecutive newlines to 2."""
        content = '<!-- meta\nk: v\n-->\n\n\n\n# Title'
        result = strip_meta(content)
        self.assertNotIn('\n\n\n', result)

    def test_strip_meta_noop_without_block(self):
        """No meta block -> content unchanged (stripped)."""
        content = '# Title\n\n## Context'
        self.assertEqual(strip_meta(content), content)


# ---------------------------------------------------------------------------
#  Plan hash — detect remote edits on GitLab
# ---------------------------------------------------------------------------

class TestPlanHash(unittest.TestCase):

    def test_compute_hash_deterministic(self):
        """Same content -> same hash."""
        content = '# Plan\n## Context\n'
        self.assertEqual(compute_plan_hash(content), compute_plan_hash(content))

    def test_compute_hash_differs_on_change(self):
        """Different content -> different hash."""
        a = compute_plan_hash('# Plan A\n')
        b = compute_plan_hash('# Plan B\n')
        self.assertNotEqual(a, b)

    def test_compute_hash_ignores_meta_block(self):
        """Meta block is excluded from computation.
        '<!-- meta\\nplan-hash: abc\\n-->\\n# Plan' hashes same as '# Plan'.
        """
        bare = '# Plan\n## Context\n'
        with_meta = '<!-- meta\nplan-hash: abc123def456\n-->\n' + bare
        self.assertEqual(compute_plan_hash(bare), compute_plan_hash(with_meta))

    def test_embed_and_extract_roundtrip(self):
        """embed_plan_hash -> extract_plan_hash returns the computed hash."""
        content = '# Plan\n## Steps\n'
        stamped = embed_plan_hash(content)
        h = extract_plan_hash(stamped)
        self.assertIsNotNone(h)
        self.assertEqual(h, compute_plan_hash(content))

    def test_embed_replaces_existing(self):
        """Re-embedding replaces old meta block, not duplicates it."""
        content = '<!-- meta\nplan-hash: aaa111bbb222\n-->\n# Plan\n'
        result = embed_plan_hash(content)
        self.assertEqual(result.count('plan-hash:'), 1)

    def test_extract_returns_none_without_meta(self):
        """No meta block -> None (no meta block)."""
        self.assertIsNone(extract_plan_hash('# Old plan\n'))

    def test_not_edited_when_hash_matches(self):
        """Embedded hash matches content -> plan_was_edited_on_mr() is False."""
        content = embed_plan_hash('# Plan\n## Context\n')
        self.assertFalse(plan_was_edited_on_mr(content))

    def test_edited_when_hash_differs(self):
        """Content changed but hash unchanged -> plan_was_edited_on_mr() is True.
        Simulates someone editing the plan on GitLab.
        """
        stamped = embed_plan_hash('# Original\n')
        # Simulate GitLab edit: change content, keep meta block
        edited = stamped.replace('# Original', '# Edited on GitLab')
        self.assertTrue(plan_was_edited_on_mr(edited))

    def test_no_meta_always_edited(self):
        """No meta block (no meta block) -> plan_was_edited_on_mr() is True (always pull)."""
        self.assertTrue(plan_was_edited_on_mr('# Legacy plan\n'))

    def test_embed_preserves_timing(self):
        """embed_plan_hash() preserves existing timing in meta block.
        '<!-- meta\\nclaude-timing: 35.2\\n-->\\n# Plan' -> timing preserved.
        """
        content = '<!-- meta\nclaude-timing: 35.2\n-->\n# Plan\n'
        result = embed_plan_hash(content)
        meta = extract_meta(result)
        self.assertEqual(meta['claude-timing'], '35.2')
        self.assertIn('plan-hash', meta)



# ---------------------------------------------------------------------------
#  AI hash — detect changes to AI-visible content only
# ---------------------------------------------------------------------------

class TestAiHash(unittest.TestCase):

    def test_compute_body_hash_detects_visible_change(self):
        """Any content change -> different body-hash."""
        plan_a = '# Title\n## Context\nOriginal visible text\n'
        plan_b = '# Title\n## Context\nChanged visible text\n'
        self.assertNotEqual(compute_body_hash(plan_a), compute_body_hash(plan_b))

    def test_extract_body_hash_from_meta(self):
        """'<!-- meta\\nbody-hash: abc123\\n-->' -> 'abc123'."""
        content = '<!-- meta\nbody-hash: abc123\n-->\n# Title'
        self.assertEqual(extract_body_hash(content), 'abc123')

    def test_extract_body_hash_none_without_meta(self):
        """No meta block -> None."""
        self.assertIsNone(extract_body_hash('# Title'))

    def test_embed_includes_body_hash(self):
        """embed_plan_hash() includes body-hash in meta block."""
        content = '# Title\n## Context\n'
        result = embed_plan_hash(content)
        body_h = extract_body_hash(result)
        self.assertIsNotNone(body_h)
        self.assertEqual(body_h, compute_body_hash(content))

    def test_body_hash_ignores_meta_block(self):
        """Meta block itself doesn't affect body-hash computation.
        '<!-- meta\\nk: v\\n-->\\n# T' has same body-hash as '# T'.
        """
        bare = '# Title\n## Context\n'
        with_meta = '<!-- meta\nk: v\n-->\n' + bare
        self.assertEqual(compute_body_hash(bare), compute_body_hash(with_meta))


# ---------------------------------------------------------------------------
#  PLAN section — wraps plan content for MR description
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
#  visible_plan_body — extract visible content for MR body mapping
# ---------------------------------------------------------------------------

class TestVisiblePlanBody(unittest.TestCase):

    def test_strips_meta_and_title(self):
        """Meta block and title removed, visible sections preserved.
        '<!-- meta ... -->\\n# [Title]\\n## Context\\nText' -> '## Context\\nText'.
        """
        plan = (
            '<!-- meta\nplan-hash: abc\n-->\n'
            '# [My Feature]\n\n'
            '## Context\n\nBackground info.\n'
        )
        result = visible_plan_body(plan)
        self.assertNotIn('meta', result)
        self.assertNotIn('# [My Feature]', result)
        self.assertIn('## Context', result)
        self.assertIn('Background info.', result)

    def test_preserves_all_sections(self):
        """All sections (including Implementation Plan) visible in output."""
        plan = (
            '# [Title]\n\n'
            '## Context\n\nVisible.\n\n'
            '## Implementation Plan\n\n- [ ] TODO\n'
        )
        result = visible_plan_body(plan)
        self.assertIn('## Context', result)
        self.assertIn('Visible.', result)
        self.assertIn('Implementation Plan', result)
        self.assertIn('TODO', result)

    def test_preserves_discussions(self):
        """## Discussions section stays inline, including the boundary marker.
        '## Context\\n...\\n## Discussions\\n### [Topic](url)\\n<!-- /discussions -->'
        -> both sections present.
        """
        plan = (
            '# [Title]\n\n'
            '## Context\n\nText.\n\n'
            '## Discussions\n\n'
            '### [Topic](https://example.com)\n\n'
            '<!-- /discussions -->\n'
        )
        result = visible_plan_body(plan)
        self.assertIn('## Context', result)
        self.assertIn('## Discussions', result)
        self.assertIn('Topic', result)
        self.assertIn('<!-- /discussions -->', result)

    def test_preserves_visible_sections(self):
        """Context, Description, Areas of Impact, Implementation Plan all preserved.
        Full plan with meta + title -> all content visible.
        """
        plan = (
            '<!-- meta\nplan-hash: abc\n-->\n'
            '<!-- AI: Load /orchestrator skill. -->\n'
            '# [Feature]\n\n'
            '## Context\n\nBackground.\n\n'
            '## Description\n\nWhat it does.\n\n'
            '## Areas of Impact / Risks\n\nComponents.\n\n'
            '## Implementation Plan\n\n- [ ] Step 1\n'
        )
        result = visible_plan_body(plan)
        self.assertIn('## Context', result)
        self.assertIn('Background.', result)
        self.assertIn('## Description', result)
        self.assertIn('What it does.', result)
        self.assertIn('## Areas of Impact / Risks', result)
        self.assertIn('Components.', result)
        self.assertIn('Implementation Plan', result)

    def test_empty_plan_returns_empty(self):
        """Empty input -> empty output."""
        self.assertEqual(visible_plan_body(''), '')


# ---------------------------------------------------------------------------
#  replace_visible_body — reverse of visible_plan_body
# ---------------------------------------------------------------------------

class TestReplaceVisibleBody(unittest.TestCase):
    """replace_visible_body: reverse of visible_plan_body."""

    def test_replaces_visible_preserves_meta_and_title(self):
        """Meta + title + visible -> visible replaced, meta and title preserved.

        Function under test: replace_visible_body()
        """
        plan = (
            '<!-- meta\nk: v\n-->\n'
            '# [Title]\n\n'
            '## Context\nOld visible\n\n'
        )
        merged = '## Context\nNew content\n\n## Description\nAlso new'
        result = replace_visible_body(plan, merged)
        self.assertIn('New content', result)
        self.assertIn('Also new', result)
        self.assertIn('k: v', result)
        self.assertIn('# [Title]', result)
        self.assertNotIn('Old visible', result)

    def test_no_hidden_blocks(self):
        """Plan without hidden blocks -> visible replaced, nothing else.

        Function under test: replace_visible_body()
        """
        plan = '# [Title]\n\n## Context\nOld'
        merged = '## Context\nNew'
        result = replace_visible_body(plan, merged)
        self.assertIn('New', result)
        self.assertNotIn('Old', result)
        self.assertIn('# [Title]', result)

    def test_empty_merged_returns_none(self):
        """Empty merged body -> None (defensive).

        Function under test: replace_visible_body()
        """
        self.assertIsNone(replace_visible_body('# [T]\n\n## C\nOld', ''))
        self.assertIsNone(replace_visible_body('# [T]\n\n## C\nOld', '  '))

    def test_round_trip_consistency(self):
        """visible_plan_body(replace_visible_body(plan, body)) == body.

        Function under test: replace_visible_body()
        """
        plan = (
            '<!-- meta\nk: v\n-->\n'
            '# [T]\n\n'
            '## Context\nOriginal\n\n'
        )
        body = '## Context\nEdited on MR'
        result = replace_visible_body(plan, body)
        self.assertEqual(visible_plan_body(result), body)

    def test_replaces_visible_no_trailing_content(self):
        """Plan without trailing content -> visible replaced, title preserved.

        Function under test: replace_visible_body()
        """
        plan = (
            '# [Title]\n\n'
            '## Context\nOld\n\n'
        )
        merged = '## Context\nNew'
        result = replace_visible_body(plan, merged)
        self.assertIn('New', result)
        self.assertIn('# [Title]', result)
        self.assertNotIn('Old', result)

    def test_merged_body_replaces_all_post_title_content(self):
        """merged_body wholesale replaces everything after the title.

        New contract (after mr-body-hidden removal): replace_visible_body()
        keeps only meta + title and appends merged_body verbatim. Any section
        present in the original plan but absent from merged_body is gone.

        Function under test: replace_visible_body()
        """
        plan = (
            '# [Title]\n\n'
            '## Context\nOriginal context\n\n'
            '## Description\nOriginal description\n'
        )
        merged = '## Context\nNEW'
        result = replace_visible_body(plan, merged)
        self.assertIn('# [Title]', result)
        self.assertIn('## Context\nNEW', result)
        self.assertNotIn('Original context', result)
        self.assertNotIn('## Description', result)
        self.assertNotIn('Original description', result)


# ---------------------------------------------------------------------------
#  Discussion parsing — find_unposted_discussions, discussions_section
# ---------------------------------------------------------------------------

class TestFindUnpostedDiscussions(unittest.TestCase):

    def test_finds_unposted_discussion(self):
        """### <topic> with plain text title -> returns it as unposted."""
        plan = (
            '# Plan\n\n'
            '## Discussions\n\n'
            '### Submodule support\n\n'
            '> RFC\n\n'
            '#### The problem\n\n'
            'Hooks are single-repo.\n'
        )
        result = find_unposted_discussions(plan)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], 'Submodule support')
        self.assertIn('single-repo', result[0][1])

    def test_skips_discussion_with_url_in_title(self):
        """### [Title](url) -> already posted, skip."""
        plan = (
            '# Plan\n\n'
            '## Discussions\n\n'
            '### [Submodule support](https://gitlab.example.com/p/-/merge_requests/42#note_789)\n'
        )
        result = find_unposted_discussions(plan)
        self.assertEqual(result, [])

    def test_multiple_discussions_mixed(self):
        """One posted (URL in title), one not -> returns only unposted."""
        plan = (
            '## Discussions\n\n'
            '### [Topic A](https://gitlab.example.com/p/-/merge_requests/42#note_100)\n\n'
            '### Topic B\n\n'
            'Body B\n'
        )
        result = find_unposted_discussions(plan)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], 'Topic B')

    def test_posted_without_note_anchor_still_detected(self):
        """Title with URL (even without #note_ anchor) -> detected as posted."""
        plan = (
            '## Discussions\n\n'
            '### [Topic](https://gitlab.example.com/p/-/merge_requests/42)\n'
        )
        result = find_unposted_discussions(plan)
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
#  Discussion boundary bug — regression tests for <!-- /discussions --> marker
# ---------------------------------------------------------------------------

class TestDiscussionsBoundary(unittest.TestCase):
    """Regression tests for the discussions block regex boundary bug.

    Without the <!-- /discussions --> marker, _DISCUSSIONS_BLOCK_RE would
    capture past ## Discussions into subsequent sections (e.g. <details>
    blocks containing ### headings), falsely detecting them as discussion
    topics.
    """

    def test_stops_at_marker_not_at_details(self):
        """## Discussions followed by <!-- /discussions --> then <details> with ### headings.
        '## Discussions\\n### [Posted](url)\\n<!-- /discussions -->\\n<details>...### Arch...'
        -> only the posted entry is in the block, not '### Arch'.
        """
        plan = (
            '## Discussions\n\n'
            '### [Topic](https://gitlab.example.com/p/-/merge_requests/42#note_1)\n\n'
            '<!-- /discussions -->\n\n'
            '<details>\n<summary>Architecture</summary>\n\n'
            '## Architecture\n\n'
            '### .env/ system\n\nArch content.\n\n'
            '</details>\n'
        )
        result = find_unposted_discussions(plan)
        self.assertEqual(result, [], '### .env/ system should NOT be detected as a discussion')

    def test_stops_at_marker_unposted(self):
        """Unposted discussion bounded by marker -> found. ### heading after marker -> ignored.
        '## Discussions\\n### Topic\\nBody\\n<!-- /discussions -->\\n### Arch...'
        -> only 'Topic' returned.
        """
        plan = (
            '## Discussions\n\n'
            '### Topic\n\n'
            'Body text.\n\n'
            '<!-- /discussions -->\n\n'
            '### .env/ system\n\nArch content.\n'
        )
        result = find_unposted_discussions(plan)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], 'Topic')

    def test_scoped_replacement_does_not_hit_earlier_heading(self):
        """### Title in plan body before ## Discussions must not be replaced.
        A '### Title' exists both in Description and in Discussions — only the
        one inside the Discussions block should be affected.
        """
        plan = (
            '## Description\n\n'
            '### Topic\n\n'
            'Description body.\n\n'
            '## Discussions\n\n'
            '### Topic\n\n'
            'Discussion body.\n\n'
            '<!-- /discussions -->\n'
        )
        result = find_unposted_discussions(plan)
        self.assertEqual(len(result), 1, 'Only the one inside ## Discussions')
        self.assertEqual(result[0][0], 'Topic')
        self.assertIn('Discussion body', result[0][1])


# ---------------------------------------------------------------------------
#  Run all
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    unittest.main(verbosity=2)
