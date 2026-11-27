#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Pure functions for BRANCH_PLAN.md content manipulation — hashing, metadata,
footer formatting, MR-body projection and reconstruction, discussion parsing.

No I/O, no subprocess.  Logging limited to dbg() for discussion parsing.
"""

import hashlib
import re

from git_hooks_impl.logger import dbg

# ---------------------------------------------------------------------------
#  Meta block — single HTML comment holding all machine metadata
# ---------------------------------------------------------------------------

# Matches: <!-- meta\nkey: value\n...\n-->
_META_BLOCK_RE = re.compile(
    r'^<!-- meta\n(.*?)\n-->\s*$',
    re.MULTILINE | re.DOTALL,
)


def _parse_meta_lines(body):
    """Parse 'key: value' lines into a dict, preserving order.

    'a: 1\\nb: 2' -> {'a': '1', 'b': '2'}
    Lines without ': ' are ignored.
    """
    result = {}
    for line in body.splitlines():
        if ': ' in line:
            key, value = line.split(': ', 1)
            result[key.strip()] = value.strip()
    return result


def _render_meta_lines(meta):
    """Render a dict as 'key: value' lines, preserving order."""
    return '\n'.join(f'{k}: {v}' for k, v in meta.items())


def extract_meta(content):
    """Parse all key-value pairs from the meta block.

    '<!-- meta\\nclaude-timing: 21.3\\nplan-hash: abc\\n-->'
    -> {'claude-timing': '21.3', 'plan-hash': 'abc'}
    No meta block -> empty dict.
    """
    m = _META_BLOCK_RE.search(content)
    if not m:
        return {}
    return _parse_meta_lines(m.group(1))


def embed_meta(content, **values):
    """Strip old meta block, prepend new one with updated values.

    Merges values into any existing meta.  Keys with None value are removed.
    Normalizes whitespace via strip_meta for GitLab round-trip stability.

    embed_meta('# Title', **{'plan-hash': 'abc', 'body-hash': 'def'})
    -> '<!-- meta\\nplan-hash: abc\\nbody-hash: def\\n-->\\n# Title\\n'
    """
    existing = extract_meta(content)
    existing.update(values)
    meta = {k: v for k, v in existing.items() if v is not None}

    clean = strip_meta(content)

    if not meta:
        return clean + '\n' if clean and not clean.endswith('\n') else clean

    block = '<!-- meta\n' + _render_meta_lines(meta) + '\n-->'
    return f'{block}\n{clean}\n'


def strip_meta(content):
    """Remove meta block and normalize whitespace.

    Collapses 3+ consecutive newlines to 2 (one blank line) so that hashes
    survive a round-trip through GitLab, which normalizes blank lines in
    MR descriptions.

    '<!-- meta\\nplan-hash: abc\\n-->\\n# Title' -> '# Title'
    """
    content = _META_BLOCK_RE.sub('', content)
    content = re.sub(r'\n{3,}', '\n\n', content)
    return content.strip()


# ---------------------------------------------------------------------------
#  Plan hash — detect remote edits on GitLab
# ---------------------------------------------------------------------------

def compute_plan_hash(content):
    """Hash plan content (excluding metadata).

    '# Title\\n## Context' -> 'a1b2c3d4e5f6' (first 12 hex chars of SHA-256).
    """
    clean = strip_meta(content)
    return hashlib.sha256(clean.encode('utf-8')).hexdigest()[:12]


def extract_plan_hash(content):
    """Read the embedded plan-hash from meta block.

    '<!-- meta\\nplan-hash: abc123\\n-->' -> 'abc123'
    No meta block or no plan-hash key -> None (no meta block yet).
    """
    meta = extract_meta(content)
    return meta.get('plan-hash')


def embed_plan_hash(content):
    """Compute hash of content and embed/update in meta block.

    Computes both plan-hash and body-hash, preserves existing meta values
    (timing etc.).
    """
    plan_h = compute_plan_hash(content)
    body_h = compute_body_hash(content)
    return embed_meta(content, **{'plan-hash': plan_h, 'body-hash': body_h})


def plan_was_edited_on_mr(content):
    """Return True if the MR plan content was edited since last push.

    Compares the embedded hash (written at push time) against the current
    content hash.  If they differ, someone edited the plan on GitLab.

    No hash line (no meta block yet) -> True (always pull, safe default).
    """
    push_hash = extract_plan_hash(content)
    if push_hash is None:
        return True  # no hash yet — always pull
    current_hash = compute_plan_hash(content)
    return push_hash != current_hash


# ---------------------------------------------------------------------------
#  Body hash — detect changes to visible MR body content only
# ---------------------------------------------------------------------------

# compute_body_hash and compute_plan_hash are equivalent (both hash
# strip_meta(content)). Separate names mark the two semantic paths in
# status.py and sync_mr.py: plan state versus visible body state.
def compute_body_hash(content):
    """Hash the plan content that maps to the MR body.

    Strips meta block, then hashes.

    '# Title\\n## Context\\ntext' -> 'a1b2c3d4e5f6' (12 hex chars of SHA-256).
    """
    clean = strip_meta(content)
    return hashlib.sha256(clean.encode('utf-8')).hexdigest()[:12]


def extract_body_hash(content):
    """Read the embedded body-hash from meta block.

    '<!-- meta\\nbody-hash: abc123\\n-->' -> 'abc123'
    No meta block or no body-hash key -> None.
    """
    meta = extract_meta(content)
    return meta.get('body-hash')


# ---------------------------------------------------------------------------
#  Plan footer — invisible metadata carrier at the end of the MR description
# ---------------------------------------------------------------------------

# Matches: <!-- plan-meta\nkey: value\n...\n-->
# MULTILINE because _embed_body_hash appends the body-hash comment after it.
# The tag is distinct from the plan's own '<!-- meta' block so the two never
# match each other.
PLAN_FOOTER_PATTERN = r'^<!-- plan-meta\n(.*?)\n-->\s*$'

_PLAN_FOOTER_RE = re.compile(PLAN_FOOTER_PATTERN, re.MULTILINE | re.DOTALL)


def _plan_title(plan_content):
    """Return the plan title text without the leading '# ', or ''."""
    m = _TITLE_RE.search(strip_meta(plan_content))
    return m.group(0).rstrip('\n')[2:].strip() if m else ''


def plan_footer(plan_content):
    """Format the metadata footer appended to every MR description.

    Carries the plan's whole meta dict plus the title, so the pull path can
    rebuild the full plan from the footer and the visible MR body.

    Returns '' when the plan has no visible body — a footer would then claim a
    plan-hash for a body that is not the plan.
    """
    if not visible_plan_body(plan_content):
        return ''
    stamped = embed_plan_hash(plan_content)
    meta = extract_meta(stamped)
    title = _plan_title(stamped)
    if title:
        meta['title'] = title
    return '\n\n<!-- plan-meta\n' + _render_meta_lines(meta) + '\n-->'


def extract_footer_meta(description):
    """Parse the plan-meta footer from an MR description.

    Returns the key-value dict, or None when the description has no footer.
    None is the "this MR carries no plan" signal.
    """
    m = _PLAN_FOOTER_RE.search(description)
    if not m:
        return None
    return _parse_meta_lines(m.group(1))


def reconstruct_plan_content(footer_meta, visible_body):
    """Rebuild full plan content from the footer metadata and the MR body.

    Inverse of plan_footer() + visible_plan_body().  Returns None when
    footer_meta is None or visible_body is empty.
    """
    if footer_meta is None:
        return None
    meta = dict(footer_meta)
    title = meta.pop('title', '')
    stub = f'# {title}\n' if title else ''
    if meta:
        stub = embed_meta(stub, **meta)
    return replace_visible_body(stub, visible_body)


def canonical_plan(plan_content):
    """Normalize plan content to the form a pull rebuilds.

    Reconstruction defines the normal form, with hashes stamped: a pull rebuilds
    exactly this string, so reconstruct(...) == canonical_plan(local) byte for
    byte whenever neither side was edited.  Every edit-detection path depends on
    that equality.

    Returns plan_content unchanged when it has no visible body.
    """
    body = visible_plan_body(plan_content)
    if not body:
        return plan_content
    meta = extract_meta(plan_content)
    title = _plan_title(plan_content)
    if title:
        meta['title'] = title
    return embed_plan_hash(reconstruct_plan_content(meta, body))



# ---------------------------------------------------------------------------
#  visible_plan_body — extract plan content that maps to MR body
# ---------------------------------------------------------------------------

# Matches the first # heading (plan title).
_TITLE_RE = re.compile(r'^# [^\n]+\n?', re.MULTILINE)


def visible_plan_body(plan_content):
    """Extract the visible plan content that maps directly to the MR body.

    Strips in order:
    1. Meta block (<!-- meta ... -->)
    2. Title (# ... — first level-1 heading)
    3. Normalize whitespace (collapse 3+ blank lines to 2, strip edges)

    Everything else — including ## Discussions and its <!-- /discussions -->
    marker — is carried through verbatim.  This makes the mapping invertible:
    reconstruct_plan_content() rebuilds the plan from this output plus the
    footer metadata, and the rebuilt content must hash identically.

    Returns clean markdown ready for MR body.

    Example:
      Input:  '<!-- meta ... -->\\n# [Title]\\n## Context\\n...'
      Output: '## Context\\n...'
    """
    text = strip_meta(plan_content)
    text = _TITLE_RE.sub('', text, count=1)
    # Normalize whitespace: collapse 3+ blank lines to 2, strip edges
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ---------------------------------------------------------------------------
#  replace_visible_body — splice merged MR body back into BRANCH_PLAN.md
# ---------------------------------------------------------------------------


def replace_visible_body(plan_content, merged_body):
    """Replace visible plan sections with the merged MR body.

    Reverse of visible_plan_body(): takes visible content (from the
    Python mapping) and splices it back, preserving meta block and title.

    The merged_body starts with ## headings (no title, no meta) — same
    format as visible_plan_body() output.

    Returns updated plan content, or None if merged_body is empty.
    """
    if not merged_body or not merged_body.strip():
        return None

    # 1. Extract and preserve meta
    meta = extract_meta(plan_content)

    # 2. Strip meta for working copy
    clean = strip_meta(plan_content)

    # 3. Extract title (first # heading line)
    title = ''
    title_match = _TITLE_RE.search(clean)
    if title_match:
        title = title_match.group(0).rstrip('\n')

    # 4. Reassemble: title + merged body
    parts = []
    if title:
        parts.append(title)
    parts.append(merged_body.strip())

    result = '\n\n'.join(parts) + '\n'

    # 5. Re-embed metadata
    if meta:
        result = embed_meta(result, **meta)

    return result


# ---------------------------------------------------------------------------
#  Discussion parsing — ### <topic> under ## Discussions
# ---------------------------------------------------------------------------

# Parent section: ## Discussions ... up to <!-- /discussions --> marker, next ## heading, or EOF
_DISCUSSIONS_BLOCK_RE = re.compile(
    r'^## Discussions\n(.*?)(?=\n<!-- /discussions -->|\n## |\Z)',
    re.DOTALL | re.MULTILINE,
)
# Individual topic within the block: ### <title> with optional body.
# Sub-headings inside bodies must use #### (not ### — that's the entry level).
_DISCUSSION_RE = re.compile(
    r'^### ([^\n]+)\n(.*?)(?=\n### |\Z)',
    re.DOTALL | re.MULTILINE,
)
# A posted discussion has its title as a markdown link: [Title](url)
_POSTED_TITLE_RE = re.compile(r'^\[([^\]]+)\]\((https?://[^\)]+)\)$')


def find_unposted_discussions(plan_content):
    """Find ### <topic> entries under ## Discussions not yet posted.

    A discussion is posted when its title is a markdown link: ### [Title](url).
    Plain-text titles are unposted. Returns list of (title, body) tuples.
    """
    block_m = _DISCUSSIONS_BLOCK_RE.search(plan_content)
    if not block_m:
        return []
    block = block_m.group(1)
    discussions = []
    for m in _DISCUSSION_RE.finditer(block):
        title = m.group(1).strip()
        body = m.group(2).strip()
        if _POSTED_TITLE_RE.match(title):
            dbg(f'Discussion already posted: {title}')
            continue
        discussions.append((title, body))
    return discussions


# Patterns that indicate session-internal history pollution in discussion bodies.
_DISCUSSION_FORBIDDEN_RES = [
    re.compile(r'\bcommit \d+\b', re.IGNORECASE),
    re.compile(r'\bPhase [A-Z]\b'),
    re.compile(r'\(this turn\)', re.IGNORECASE),
    re.compile(r'\bwe then\b', re.IGNORECASE),
    re.compile(r'\bpreviously\b', re.IGNORECASE),
    re.compile(r'\(NEW\)'),
    re.compile(r'\bwe decided after\b', re.IGNORECASE),
    re.compile(r'\bsee Q\d+\b', re.IGNORECASE),
    re.compile(r'\bper task #\d+\b', re.IGNORECASE),
]


def validate_discussions(plan_content):
    """Validate ## Discussions entries against PW-6 body discipline.

    Returns list of (title, violation_type) strings. Empty list = clean.
    Violations:
    - 'empty-body': body is blank or contains only an MR-comment URL.
    - 'forbidden-pattern: <pattern>': body contains session-internal history.
    """
    block_m = _DISCUSSIONS_BLOCK_RE.search(plan_content)
    if not block_m:
        return []
    block = block_m.group(1)
    violations = []
    for m in _DISCUSSION_RE.finditer(block):
        title = m.group(1).strip()
        body = m.group(2).strip()
        # Skip already-posted entries — their bodies are stripped to just the URL.
        if _POSTED_TITLE_RE.match(title):
            continue
        # Empty body: blank or only an http(s) link line.
        body_no_links = re.sub(r'https?://\S+', '', body).strip()
        if not body_no_links:
            violations.append((title, 'empty-body'))
            continue
        for pattern in _DISCUSSION_FORBIDDEN_RES:
            match = pattern.search(body)
            if match:
                violations.append((title, f'forbidden-pattern: {match.group(0)!r}'))
                break
    return violations
