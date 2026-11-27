#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""MR creation logic — used on the first push of a branch.

MR body is derived from the generated PLAN.md via visible_plan_body()
(same deterministic mapping used on every subsequent push). Jira data
and labels arrive via PlanContext from the plan generation pipeline —
no re-fetching.
"""

import re
import webbrowser

from git_hooks_impl.glab import get_project_path, glab_api_write
from git_hooks_impl.logger import dbg, err, log, ok
from git_hooks_impl.plan.parser import visible_plan_body
from git_hooks_impl.templates import basic_fill_template, template_skeleton
from git_hooks_impl.utils import TARGET_BRANCH


def _extract_summary_from_plan_title(plan_content, jira_ticket):
    """Extract the Jira summary from the plan's title line.

    Plan title format: # [[PROJECTNAME-1234] Fix race condition in auth module]
    Outer brackets = title marker, inner [TICKET] = Jira convention.
    Also handles legacy format without outer brackets.

    Returns the summary text ('Fix race condition in auth module') or ''
    if the title doesn't match the expected pattern.
    """
    if not plan_content or not jira_ticket:
        return ''
    first_line = plan_content.lstrip().split('\n', 1)[0]
    if first_line.startswith('# [['):
        inner = first_line[3:-1]
    elif first_line.startswith('# '):
        inner = first_line[2:]
    else:
        return ''
    prefix = f'[{jira_ticket}] '
    if inner.startswith(prefix):
        return inner[len(prefix):].strip()
    return ''


def mr_title(branch, jira_ticket, jira_summary_line):
    """Build the MR title.

    With Jira summary:  '[PROJECTNAME-1234] Fix race condition'
    With ticket only:   '[PROJECTNAME-1234] Deep auth investigation'
    Without ticket:     'Deep auth investigation'
    """
    tail = branch.rsplit('/', 1)[-1]
    # Strip ticket prefix and convert underscores to spaces
    description = re.sub(r'^[A-Za-z]+-\d+_', '', tail).replace('_', ' ')
    description = tail if not description else description[0].upper() + description[1:]

    if jira_ticket and jira_summary_line:
        return f'[{jira_ticket}] {jira_summary_line}'
    if jira_ticket:
        return f'[{jira_ticket}] {description}'
    return description


def _extract_mr_url(response):
    """Extract MR URL from API response dict.

    Pure function — returns the URL string or ''.
    """
    if response and isinstance(response, dict):
        return response.get('web_url', '')
    return ''


async def create_mr(branch, template, jira_ticket, plan_content, plan_footer,
                    username, jira_summary_line='', labels=None, assignees=None):
    """Create a new draft MR for the branch.

    MR body = visible_plan_body(plan_content) — same mapping used on every
    subsequent push. Falls back to basic_fill_template when plan has no
    visible content, in which case plan_footer is omitted from the
    description (a footer would claim a plan-hash for a body that isn't
    the plan).

    jira_summary_line, labels, assignees are optional — when provided (from
    PlanContext via cmd_new), they avoid redundant template_skeleton() and
    Jira CLI calls. When omitted (from cmd_sync_mr first-push path),
    defaults trigger fallback: summary parsed from plan title, labels/
    assignees fetched from template_skeleton().
    """
    # Labels/assignees: prefer explicit (from PlanContext), fall back to template
    if labels is None or assignees is None:
        skeleton, fallback_labels, fallback_assignees = template_skeleton(
            template, jira_ticket)
        if labels is None:
            labels = fallback_labels
        if assignees is None:
            assignees = fallback_assignees
    else:
        skeleton = None

    # MR body from plan — same stripping as every subsequent push
    body = visible_plan_body(plan_content)
    body_from_plan = bool(body)
    if not body:
        if skeleton is None:
            skeleton, _, _ = template_skeleton(template, jira_ticket)
        body = basic_fill_template(skeleton, jira_summary_line)
    dbg(f"Body source: {'plan' if body_from_plan else 'basic fill'}")

    # Jira summary for title: prefer explicit, fall back to plan title
    if not jira_summary_line:
        jira_summary_line = _extract_summary_from_plan_title(
            plan_content, jira_ticket)

    full_desc = body + (plan_footer if body_from_plan else '')
    title     = mr_title(branch, jira_ticket, jira_summary_line)

    log(f'Creating MR: "{title}"')
    if labels:
        log(f"Labels: {', '.join(labels)}")
    if assignees:
        dbg(f"Template quick-action assignees (not passed to API): "
            f"{', '.join(assignees)}")
    dbg(f'Description length: {len(full_desc)} chars')

    project_path = await get_project_path()
    if not project_path:
        err('Could not determine project path — skipping MR creation')
        return

    api_path = f"projects/{project_path.replace('/', '%2F')}/merge_requests"
    payload = {
        'source_branch': branch,
        'target_branch': TARGET_BRANCH,
        'title': f'Draft: {title}',
        'description': full_desc,
    }
    if labels:
        payload['labels'] = ','.join(labels)

    exit_code, response, stderr = await glab_api_write(api_path, payload)

    mr_url = _extract_mr_url(response)
    if exit_code == 0 and mr_url:
        ok(f'Draft MR created: {mr_url}')
        webbrowser.open(mr_url)
    else:
        err('MR creation failed or produced unexpected output:')
        if stderr:
            for line in stderr.splitlines():
                err(f'  {line}')
