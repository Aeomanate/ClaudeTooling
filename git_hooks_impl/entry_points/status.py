#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""mr status — show plan/MR sync state at a glance.

Compares local .ai/PLAN.md against the MR's embedded copy to report
whether the plan is synced, modified locally, modified on the MR, or
diverged.  No writes, no AI calls.
"""

import difflib
import json
import os
import sys

from git_hooks_impl.branch_utils import body_was_edited, visible_body_for_reconstruction
from git_hooks_impl.logger import bold_red, cyan, dim, green, warn
from git_hooks_impl.plan.parser import (
    compute_body_hash,
    compute_plan_hash,
    extract_body_hash,
    extract_footer_meta,
    extract_plan_hash,
    reconstruct_plan_content,
    strip_meta,
)
from git_hooks_impl.utils import PLAN_FILE, TARGET_BRANCH, run, run_async

# ---------------------------------------------------------------------------
#  Sync state labels
# ---------------------------------------------------------------------------

_STATE_SYNCED     = 'synced'
_STATE_LOCAL      = 'modified locally (not yet pushed)'
_STATE_REMOTE     = 'modified on MR (not yet pulled)'
_STATE_DIVERGED   = 'diverged (both sides edited)'
_STATE_NEW        = 'new (never pushed)'


def _content_state(local_hash, mr_hash, mr_stored_hash):
    """Determine sync state by comparing local content against MR content.

    Primary check: local_hash vs mr_hash (actual content comparison).
    Direction: mr_stored_hash (from MR's meta block, set at push time)
    is the reliable anchor — it never gets re-embedded locally.

    If mr_stored_hash == mr_hash: MR untouched since push → local edited.
    If mr_stored_hash != mr_hash: MR was edited on GitLab.
    """
    if mr_stored_hash is None:
        return _STATE_NEW

    if local_hash == mr_hash:
        return _STATE_SYNCED

    # Content differs — use MR's stored hash to determine direction.
    # MR stored hash is reliable: set at push time, not re-embedded locally.
    mr_changed = (mr_hash != mr_stored_hash)
    local_changed = (local_hash != mr_stored_hash)

    if local_changed and mr_changed:
        return _STATE_DIVERGED
    if local_changed:
        return _STATE_LOCAL
    if mr_changed:
        return _STATE_REMOTE

    # Both match MR stored but differ from each other — shouldn't happen,
    # but treat as diverged to be safe
    return _STATE_DIVERGED


def _local_only_state(stored_hash, current_hash):
    """Fallback when no MR is available — compare stored vs computed locally.

    None stored hash means the plan was never pushed (no meta block).
    """
    if stored_hash is None:
        return _STATE_NEW
    if stored_hash == current_hash:
        return _STATE_SYNCED
    return _STATE_LOCAL


# ---------------------------------------------------------------------------
#  MR fetching
# ---------------------------------------------------------------------------

async def _fetch_mr(branch_name):
    """Fetch the open MR for branch_name via glab.

    Returns (mr_data_dict, error_string).
    On success: (dict with iid/title/state/description, None).
    On failure: (None, human-readable reason).
    """
    exit_code, stdout, stderr = await run_async([
        'glab', 'mr', 'list',
        '--source-branch', branch_name,
        '--output', 'json',
    ])

    if exit_code != 0:
        return None, f'glab failed (exit_code={exit_code}): {stderr.strip()}'

    if not stdout.strip():
        return None, 'none'

    try:
        parsed = json.loads(stdout)
    except (json.JSONDecodeError, ValueError) as exception:
        return None, f'invalid JSON from glab: {exception}'

    if not isinstance(parsed, list):
        parsed = [parsed] if isinstance(parsed, dict) and parsed.get('iid') else []

    open_mrs = [mr for mr in parsed if isinstance(mr, dict) and mr.get('iid')]

    if len(open_mrs) == 0:
        return None, 'none'
    if len(open_mrs) > 1:
        return None, f'multiple MRs ({len(open_mrs)})'

    return open_mrs[0], None


def _mr_display(mr_data):
    """Format MR line: !42 "title" (draft/opened)."""
    iid = mr_data.get('iid', '?')
    title = mr_data.get('title', '')
    state = 'draft' if mr_data.get('draft') else mr_data.get('state', 'opened')
    return f'!{iid} "{title}" ({state})'


# ---------------------------------------------------------------------------
#  Diff formatting
# ---------------------------------------------------------------------------

def _format_diff(mr_plan_content, local_plan_content):
    """Generate a colorized unified diff between MR and local plan content.

    Both inputs are stripped of meta blocks before diffing.
    Returns the formatted diff string, or empty string if identical.
    """
    mr_lines = strip_meta(mr_plan_content).splitlines(keepends=True)
    local_lines = strip_meta(local_plan_content).splitlines(keepends=True)

    diff_lines = list(difflib.unified_diff(
        mr_lines, local_lines,
        fromfile='MR', tofile='local',
    ))

    if not diff_lines:
        return ''

    result = []
    for line in diff_lines:
        stripped = line.rstrip('\n')
        if stripped.startswith('+++') or stripped.startswith('---'):
            result.append(dim(stripped))
        elif stripped.startswith('@@'):
            result.append(cyan(stripped))
        elif stripped.startswith('+'):
            result.append(green(stripped))
        elif stripped.startswith('-'):
            result.append(bold_red(stripped))
        else:
            result.append(dim(stripped))

    return '\n'.join(result)


# ---------------------------------------------------------------------------
#  Main command
# ---------------------------------------------------------------------------

def _count_lines(output):
    """Count non-empty lines in git log output."""
    return len(output.strip().splitlines()) if output.strip() else 0


def _print_scope(branch_name):
    """Print commit scope: commits ahead of master and push state."""
    _, tracking_out, _ = run(['git', 'rev-parse', '--abbrev-ref',
                              f'{branch_name}@{{upstream}}'])
    has_upstream = tracking_out.strip() and 'error' not in tracking_out.lower()

    _, commits_out, _ = run(['git', 'log', '--oneline',
                             f'{TARGET_BRANCH}..HEAD'])
    commit_count = _count_lines(commits_out)

    if has_upstream:
        _, unpushed_out, _ = run(['git', 'log', '--oneline',
                                  f'{tracking_out.strip()}..HEAD'])
        unpushed = _count_lines(unpushed_out)
        pushed = commit_count - unpushed
        push_info = f', {pushed} pushed / {unpushed} local'
    else:
        push_info = ', not pushed'

    print(f'Scope:  {commit_count} commits ahead of {TARGET_BRANCH}{push_info}')


def _print_status(diff_output, status_lines, branch_name):
    """Print diff first, then status summary, then commit scope."""
    if diff_output:
        try:
            sys.stdout.buffer.write((diff_output + '\n').encode('utf-8'))
            sys.stdout.buffer.flush()
        except AttributeError:
            print(diff_output)
    for line in status_lines:
        print(line)
    _print_scope(branch_name)


async def _gather_status_data(branch_name):
    """Gather all data needed for status display.

    I/O: reads plan file, fetches MR via glab, extracts plan from MR.
    Returns a dict with keys:
        branch, has_plan, local_content,
        local_plan_hash, local_body_hash, stored_plan_hash, stored_body_hash,
        mr_data, mr_error, mr_plan_content.
    """
    data = {
        'branch': branch_name,
        'has_plan': False,
        'local_content': None,
        'local_plan_hash': None, 'local_body_hash': None,
        'stored_plan_hash': None, 'stored_body_hash': None,
        'mr_data': None, 'mr_error': None,
        'mr_plan_content': None,
    }

    if not os.path.isfile(PLAN_FILE):
        return data

    data['has_plan'] = True
    with open(PLAN_FILE, encoding='utf-8') as f:
        data['local_content'] = f.read()

    data['local_plan_hash'] = compute_plan_hash(data['local_content'])
    data['local_body_hash'] = compute_body_hash(data['local_content'])
    data['stored_plan_hash'] = extract_plan_hash(data['local_content'])
    data['stored_body_hash'] = extract_body_hash(data['local_content'])

    data['mr_data'], data['mr_error'] = await _fetch_mr(branch_name)

    if data['mr_data'] is not None:
        description = data['mr_data'].get('description', '') or ''
        footer_meta = extract_footer_meta(description)
        body = visible_body_for_reconstruction(description)
        data['mr_plan_content'] = reconstruct_plan_content(footer_meta, body)

    return data


def _format_status_output(data):
    """Format status display lines and diff output from gathered data.

    Pure formatting: no I/O, no network calls.
    Returns (status_lines, diff_output).
    """
    status_lines = [f"Branch: {data['branch']}"]
    diff_output = ''

    if not data['has_plan']:
        status_lines.append('Plan:   no plan file')
        return status_lines, diff_output

    local_plan_hash = data['local_plan_hash']
    local_body_hash = data['local_body_hash']
    stored_plan_hash = data['stored_plan_hash']
    stored_body_hash = data['stored_body_hash']
    mr_data = data['mr_data']
    mr_error = data['mr_error']
    mr_plan_content = data['mr_plan_content']

    if mr_error and mr_error != 'none':
        if 'glab failed' in mr_error or 'invalid JSON' in mr_error:
            status_lines.append(f'MR:     offline ({mr_error})')
        else:
            status_lines.append(f'MR:     {mr_error}')
        status_lines.append(f'Plan:   {_local_only_state(stored_plan_hash, local_plan_hash)}')
        status_lines.append(f'Body:   {_local_only_state(stored_body_hash, local_body_hash)}')
        return status_lines, diff_output

    if mr_data is None:
        status_lines.append('MR:     none')
        status_lines.append(f'Plan:   {_local_only_state(stored_plan_hash, local_plan_hash)}')
        status_lines.append(f'Body:   {_local_only_state(stored_body_hash, local_body_hash)}')
        return status_lines, diff_output

    status_lines.append(f'MR:     {_mr_display(mr_data)}')

    if mr_plan_content is None:
        status_lines.append(f'Plan:   {_local_only_state(stored_plan_hash, local_plan_hash)}')
        status_lines.append(f'Body:   {_local_only_state(stored_body_hash, local_body_hash)}')
        return status_lines, diff_output

    # Plan state
    mr_plan_hash = compute_plan_hash(mr_plan_content)
    mr_stored_plan_hash = extract_plan_hash(mr_plan_content)
    plan_state = _content_state(local_plan_hash, mr_plan_hash, mr_stored_plan_hash)
    status_lines.append(f'Plan:   {plan_state}')

    # Body state
    mr_body_hash = compute_body_hash(mr_plan_content)
    mr_stored_body_hash = extract_body_hash(mr_plan_content)
    body_state = _content_state(local_body_hash, mr_body_hash, mr_stored_body_hash)
    description = mr_data.get('description', '') or ''
    mr_body_edited, _ = body_was_edited(description)
    if mr_body_edited and body_state == _STATE_SYNCED:
        body_state = _STATE_REMOTE
    status_lines.append(f'Body:   {body_state}')

    # Diff (when local differs from MR)
    should_diff = plan_state in (_STATE_LOCAL, _STATE_REMOTE, _STATE_DIVERGED)
    if should_diff:
        diff_output = _format_diff(mr_plan_content, data['local_content']) or ''

    return status_lines, diff_output


async def cmd_status():
    """Show plan/MR sync state at a glance."""
    # 1. Get current branch
    exit_code, branch_name, _ = run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
    branch_name = branch_name.strip()

    if exit_code != 0 or branch_name == 'HEAD':
        warn('Detached HEAD — cannot determine branch')
        return

    # 2. Gather data and format output
    data = await _gather_status_data(branch_name)
    status_lines, diff_output = _format_status_output(data)

    # 3. Print
    _print_status(diff_output, status_lines, branch_name)
