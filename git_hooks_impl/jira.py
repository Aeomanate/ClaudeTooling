#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Jira CLI wrapper — fetch ticket summaries and Jira connection constants.
"""

import re
import time

from git_hooks_impl.logger import log, warn
from git_hooks_impl.utils import find_tool, run_async

# Strip ANSI escape sequences that jira CLI emits even when piped
_ANSI_ESCAPE_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')


def strip_ansi(text):
    """Remove ANSI escape sequences from text.

    Jira CLI emits terminal formatting (colors, bold) even when stdout
    is piped.  These codes pollute AI prompts and appear in generated plans.
    """
    return _ANSI_ESCAPE_RE.sub('', text)


# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------

JIRA_VERSION = '1.7.0'
JIRA_SERVER  = 'https://companyname-eng.atlassian.net'
JIRA_PAT_URL = 'https://eng.jira.companyname.com/jira/for-you'


# ---------------------------------------------------------------------------
#  Jira CLI helpers
# ---------------------------------------------------------------------------

async def jira_summary(jira_ticket):
    """Fetch Jira ticket and return (summary_line, full_content).
    summary_line is the issue title (e.g. '[Profile Switching] Fix ...').
    Returns ('', '') on failure.
    """
    if not find_tool('jira'):
        warn("'jira' not found — Jira info will be skipped. Run: mr setup")
        return '', ''
    log(f'Fetching Jira {jira_ticket}...')
    t0 = time.time()
    exit_code, content, stderr = await run_async(['jira', 'issue', 'view', jira_ticket])
    elapsed = time.time() - t0
    if exit_code != 0:
        is_html_response = "invalid character '<'" in stderr
        if is_html_response:
            warn(f'Jira returned HTML instead of JSON for {jira_ticket} — '
                 'check jira config (installation: Local), '
                 'JIRA_API_TOKEN expiry, or VPN connection')
        else:
            warn(f'jira issue view {jira_ticket} failed '
                 f'(exit_code={exit_code}, {elapsed:.1f}s): {stderr.strip()}')
        return '', ''
    if not content.strip():
        warn(f'jira issue view {jira_ticket} returned empty output ({elapsed:.1f}s)')
        return '', ''
    content = strip_ansi(content)
    log(f'Jira fetched ({elapsed:.1f}s)')
    # jira issue view outputs markdown — the summary is the first # header line
    header_match = re.search(r'^\s*#\s+(.+)$', content, re.MULTILINE)
    summary = header_match.group(1).strip() if header_match else ''
    if not summary:
        warn("Could not extract summary from Jira output (no '# ' header found)")
    return summary, content
