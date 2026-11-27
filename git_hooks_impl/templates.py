#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""MR template loading and filling — parse .gitlab/ templates, extract labels/
assignees, and provide basic (non-AI) template fill.
"""

import os
import re
from pathlib import Path

# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))


def _resolve_templates_dir() -> Path:
    """Locate consumer's MR template dir.

    When invoked from a git hook, GIT_WORK_TREE is set by git to the
    consumer's project root. Outside hooks (e.g., tests, CLI), fall
    back to current working directory.
    """
    root = os.environ.get('GIT_WORK_TREE') or os.getcwd()
    return Path(root) / '.gitlab' / 'merge_request_templates'


_TEMPLATES_DIR = _resolve_templates_dir()

# Maps template name -> filename (Default is capitalized on disk)
_TEMPLATE_FILES = {
    'fix':           'fix.md',
    'feature':       'feature.md',
    'documentation': 'documentation.md',
    'default':       'Default.md',
}

# Matches description placeholders: (Add a description...), (Meaningful description...), etc.
_PLACEHOLDER_RE = re.compile(r'\((?:Add |Meaningful |A brief )[^)]+\)')


# ---------------------------------------------------------------------------
#  Template parsing
# ---------------------------------------------------------------------------

def _parse_template(text):
    """Parse a GitLab MR template file, separating body from quick actions.

    Strips:
      /draft           — hook uses glab --draft flag instead
      /label <name>    — extracted into labels list
      /assign @<user>  — extracted into assignees list

    Returns (body, labels, assignees).
    """
    labels = []
    assignees = []
    body_lines = []

    for line in text.splitlines():
        stripped = line.strip()
        if stripped == '/draft':
            continue
        if stripped.startswith('/label '):
            labels.append(stripped[len('/label '):].strip())
            continue
        if stripped.startswith('/assign '):
            assignees.append(stripped[len('/assign '):].strip())
            continue
        body_lines.append(line)

    body = '\n'.join(body_lines).strip()
    return body, labels, assignees


def _fallback_skeleton(template, jira_ticket=''):
    """Minimal hardcoded fallback when .gitlab/merge_request_templates/ is missing.

    Safety net for shallow clones or detached worktrees.
    Just section headings — no placeholder hints.
    """
    jira_block = ''
    if template == 'fix':
        if jira_ticket:
            jira_url = f'https://jira.companyname.io/browse/{jira_ticket}'
            jira_block = f'\n{jira_url}\n'
        return (
            f'## Bug description\n{jira_block}\n'
            '## Areas of impact\n'
        )
    return (
        '## Description\n\n'
        '## Areas of impact\n'
    )


def template_skeleton(template, jira_ticket=''):
    """Load MR template from .gitlab/merge_request_templates/ for the given type.

    Returns (body, labels, assignees):
      body      — template text with /draft, /label, /assign stripped
      labels    — list of labels extracted from /label lines
      assignees — list of usernames extracted from /assign lines

    If the file doesn't exist, returns a minimal fallback skeleton.
    Replaces [Jira Ticket Link] placeholder with the actual Jira URL if ticket provided.
    """
    filename = _TEMPLATE_FILES.get(template, 'Default.md')
    filepath = os.path.join(_TEMPLATES_DIR, filename)

    if not os.path.isfile(filepath):
        return _fallback_skeleton(template, jira_ticket), [], []

    with open(filepath, encoding='utf-8') as f:
        text = f.read()

    body, labels, assignees = _parse_template(text)

    # Inject Jira link if ticket provided
    if jira_ticket and '[Jira Ticket Link]' in body:
        jira_url = f'https://jira.companyname.io/browse/{jira_ticket}'
        body = body.replace('[Jira Ticket Link]', jira_url, 1)

    return body, labels, assignees


def basic_fill_template(skeleton, jira_sum):
    """Fill template sections without AI — insert Jira summary into the
    first description placeholder.

    Uses _PLACEHOLDER_RE to match parenthesized description placeholders
    from any template (works regardless of wording changes in .gitlab/ files).
    Returns the skeleton with the first match replaced.
    """
    if not jira_sum:
        return skeleton
    # Replace only the first description placeholder, leave others (Areas of impact)
    return _PLACEHOLDER_RE.sub(jira_sum, skeleton, count=1)
