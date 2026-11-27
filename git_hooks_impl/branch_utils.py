#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Branch name parsing and MR body hash utilities.

Extracted from sync_mr.py to break the circular dependency between
sync_mr and extract_plan — both modules need parse_branch(), and
status needs body_was_edited(), but neither should depend on the other.
"""

import hashlib
import os
import re

from git_hooks_impl.logger import dbg, log, warn
from git_hooks_impl.plan.parser import PLAN_FOOTER_PATTERN
from git_hooks_impl.utils import PLAN_FILE

# Body hash — detects if someone edited the visible MR body on GitLab.
# Embedded as the last line of the MR description.
_BODY_HASH_RE = re.compile(r'<!-- body-hash: ([a-f0-9]+) -->')

# Captures ## Checklist section only — stops at the next ## heading.
_CHECKLIST_RE = re.compile(
    r'^## Checklist\n.*?(?=\n## |\Z)',
    re.DOTALL | re.MULTILINE,
)


def parse_branch(branch):
    """Parse the branch name and return (template, jira_ticket).

    Recognised branch formats:
      private/<username>/<description>                -> default template, no Jira
      <swimlane>/fixes/[TICKET_]<description>         -> fix template
      <swimlane>/features/[TICKET_]<description>      -> feature template
      <swimlane>/devices/<description>                -> default template
      <swimlane>/docs/[TICKET_]<description>          -> documentation template
      <swimlane>/documentation/[TICKET_]<description> -> documentation template
      <anything else>                                 -> default template + warning
    """
    # private/<username>/<description>
    if re.match(r'^private/[^/]+/.+', branch):
        log('Branch type: private  ->  default template')
        return 'default', ''

    branch_match = re.match(r'^[a-z]+/(fixes|features|devices|docs|documentation)/(.+)$', branch)
    if branch_match:
        branch_type = branch_match.group(1)
        name        = branch_match.group(2)

        type_map = {
            'fixes':         'fix',
            'features':      'feature',
            'devices':       'default',
            'docs':          'documentation',
            'documentation': 'documentation',
        }
        template = type_map[branch_type]
        log(f'Branch type: {branch_type}  ->  {template} template')

        ticket_match = re.match(r'^([A-Za-z]+-\d+)_', name)
        if ticket_match:
            jira_ticket = ticket_match.group(1).upper()
            log(f'Jira ticket: {jira_ticket}')
            return template, jira_ticket

        warn('No Jira ticket in branch name. '
             'Adding one (e.g. PROJECTNAME-1234_) enables AI-assisted MR description and title.')
        return template, ''

    warn(f"Branch '{branch}' does not follow naming conventions.")
    warn('  Recognised formats:')
    warn('    private/<username>/<description>')
    warn('    <swimlane>/fixes/[PROJ-1234_]<description>         ->  Fix template')
    warn('    <swimlane>/features/[PROJ-1234_]<description>      ->  Feature template')
    warn('    <swimlane>/devices/<description>                   ->  Default template')
    warn('    <swimlane>/docs/[PROJ-1234_]<description>          ->  Documentation template')
    warn('  Example: productname/fixes/PROJECTNAME-1234_my_fix')
    warn('  Example: productname/fixes/PROJECTNAME-1234_my_fix')
    warn('  Using Default template.')
    return 'default', ''


def read_plan():
    """Read .ai/PLAN.md. Returns content string, empty if file is missing."""
    if not os.path.isfile(PLAN_FILE):
        warn(f'No {PLAN_FILE} found — PLAN.md section will be empty')
        return ''
    with open(PLAN_FILE, encoding='utf-8') as f:
        content = f.read()
    log(f'PLAN.md loaded ({len(content)} chars)')
    return content


def _strip_body_hash(text):
    """Remove the body-hash comment from text."""
    return _BODY_HASH_RE.sub('', text).rstrip()


def _clean_body(desc):
    """Strip the plan-meta footer and body-hash comment from MR description.

    Returns the human-visible body text only.
    """
    text = re.sub(PLAN_FOOTER_PATTERN, '', desc, flags=re.MULTILINE | re.DOTALL)
    text = _strip_body_hash(text)
    return text.rstrip()


def visible_body_for_reconstruction(description):
    """Return the MR body text usable to reconstruct plan content.

    _clean_body() output minus the ## Checklist section — the footer must
    already be gone (via _clean_body) before the Checklist regex runs, since
    the footer has no '## ' heading and would otherwise be swallowed by the
    Checklist match's lookahead.
    """
    text = _clean_body(description)
    return _CHECKLIST_RE.sub('', text).rstrip()


def _compute_mr_body_hash(body_text):
    """Hash the visible MR body text (12 hex chars of SHA-256).

    'Description text here' -> 'a1b2c3d4e5f6'
    """
    return hashlib.sha256(body_text.strip().encode('utf-8')).hexdigest()[:12]


def body_was_edited(current_desc):
    """Check if the MR body was manually edited since last push.

    Returns (was_edited: bool, clean_body: str).
    """
    clean = _clean_body(current_desc)
    m = _BODY_HASH_RE.search(current_desc)
    if not m:
        # No hash stored (first push) — treat as not edited
        return False, clean
    stored_hash = m.group(1)
    current_hash = _compute_mr_body_hash(clean)
    edited = stored_hash != current_hash
    if edited:
        dbg(f'Body was edited on GitLab (stored={stored_hash}, current={current_hash})')
    else:
        dbg('Body not edited since last push')
    return edited, clean


def _embed_body_hash(desc):
    """Append a body-hash comment to the MR description.

    Computes hash from the clean body (excluding managed sections).
    """
    clean = _clean_body(desc)
    body_hash = _compute_mr_body_hash(clean)
    # Strip any existing hash, then append new one
    desc = _strip_body_hash(desc).rstrip()
    return f'{desc}\n<!-- body-hash: {body_hash} -->'
