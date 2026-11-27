#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Git helpers — single home for all git shell-outs used by plan generation.

All functions here use `run()` from utils and log via the logger module.
No Jira/GitLab API calls belong here.
"""

import re

from git_hooks_impl.logger import dbg
from git_hooks_impl.utils import TARGET_BRANCH, run

# Word-boundary, case-insensitive match for ticket IDs in commit subjects.
_TICKET_IN_SUBJECT_RE_CACHE = {}


def _ticket_re(ticket_id: str) -> re.Pattern:
    """Return (cached) word-boundary regex for ticket_id."""
    if ticket_id not in _TICKET_IN_SUBJECT_RE_CACHE:
        _TICKET_IN_SUBJECT_RE_CACHE[ticket_id] = re.compile(
            r'\b' + re.escape(ticket_id) + r'\b',
            re.IGNORECASE,
        )
    return _TICKET_IN_SUBJECT_RE_CACHE[ticket_id]


def get_merge_base() -> str:
    """Find merge-base between HEAD and the closest base branch.

    Tries TARGET_BRANCH ('master') then 'main'. Returns empty string on failure.
    """
    for ref in (TARGET_BRANCH, 'main'):
        exit_code, out, _ = run(['git', 'merge-base', ref, 'HEAD'])
        if exit_code == 0 and out.strip():
            return out.strip()
    dbg('git merge-base failed for all refs')
    return ''


def get_commit_messages(merge_base: str = '') -> str:
    """Get one-line commit messages (hash + subject) from merge-base to HEAD.

    Returns newline-separated '<hash> <subject>' lines, or '' on failure.
    Resolves merge-base internally when not supplied.
    """
    if not merge_base:
        merge_base = get_merge_base()
    if not merge_base:
        return ''
    exit_code, out, _ = run(
        ['git', 'log', '--format=%H %s', f'{merge_base}..HEAD']
    )
    if exit_code != 0:
        dbg(f'git log failed (exit_code={exit_code})')
        return ''
    return out


def get_current_branch_diff_stats() -> str:
    """Return git diff stat between merge-base and HEAD.

    Capped at 20 files and 80-char name width to keep prompt injection
    budget under ~500ms on typical branches (B40).
    """
    base = get_merge_base()
    if not base:
        return ''
    exit_code, out, _ = run([
        'git', 'diff', f'{base}..HEAD',
        '--stat',
        '--stat-count=20',
        '--stat-name-width=80',
    ])
    return out if exit_code == 0 else ''


def get_branch_diff_raw() -> str:
    """Return the full raw diff between master and HEAD (on-demand only)."""
    merge_base = get_merge_base()
    if not merge_base:
        return ''
    exit_code, out, _ = run(['git', 'diff', f'{merge_base}..HEAD'])
    return out if exit_code == 0 else ''


def detect_nearest_parent_branch() -> tuple:
    """Return (parent_branch_name, parent_sha) for the nearest non-default
    ancestor of HEAD. Falls back to (TARGET_BRANCH, master_sha) on any
    edge case — never worse than the old master-diff baseline.

    Algorithm:
    1. Enumerate local branches via `git for-each-ref refs/heads/`.
    2. Exclude: current HEAD branch, TARGET_BRANCH ('master'), 'main',
       and any ref ending in '/HEAD'.
    3. For each candidate: skip if not an ancestor of HEAD.
    4. Compute distance from default: commit count in
       `git log <TARGET_BRANCH>..<candidate>` (commits on candidate since master).
       Higher = deeper parent (more progress past default branch).
    5. Return the deepest qualifying ancestor.
    6. Fall back to (TARGET_BRANCH, <master sha>) on any failure.
    """
    # Resolve fallback: master sha
    fallback_name = TARGET_BRANCH
    _, fallback_sha, _ = run(['git', 'rev-parse', TARGET_BRANCH])
    fallback_sha = fallback_sha.strip()
    if not fallback_sha:
        _, fallback_sha, _ = run(['git', 'rev-parse', 'HEAD'])
        fallback_sha = fallback_sha.strip()
    fallback = (fallback_name, fallback_sha)

    # Get current branch (may be empty on detached HEAD)
    exit_code, current_branch, _ = run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
    current_branch = current_branch.strip()
    if exit_code != 0:
        return fallback

    # Enumerate local branch refs
    exit_code, refs_out, _ = run([
        'git', 'for-each-ref',
        '--format=%(refname:short)',
        'refs/heads/',
    ])
    if exit_code != 0:
        return fallback

    excluded = {current_branch, TARGET_BRANCH, 'main', 'HEAD'}
    candidates = []
    for ref in refs_out.strip().splitlines():
        ref = ref.strip()
        if not ref or ref in excluded or ref.endswith('/HEAD'):
            continue
        candidates.append(ref)

    if not candidates:
        return fallback

    # Score each candidate: ancestor check + distance from default
    best_name = None
    best_distance = -1
    best_sha = ''

    for candidate in candidates:
        # Ancestor check: exit 0 means candidate IS an ancestor of HEAD
        anc_exit, _, _ = run(['git', 'merge-base', '--is-ancestor', candidate, 'HEAD'])
        if anc_exit != 0:
            continue

        # Distance: commits on candidate since master (higher = deeper parent)
        dist_exit, dist_out, _ = run([
            'git', 'rev-list', '--count', f'{TARGET_BRANCH}..{candidate}',
        ])
        if dist_exit != 0:
            continue
        try:
            distance = int(dist_out.strip())
        except ValueError:
            continue

        if distance > best_distance:
            sha_exit, sha_out, _ = run(['git', 'rev-parse', candidate])
            if sha_exit == 0 and sha_out.strip():
                best_distance = distance
                best_name = candidate
                best_sha = sha_out.strip()

    if best_name and best_sha:
        return (best_name, best_sha)
    return fallback


def detect_stacked_branch(starter_ticket_id: str) -> str:
    """Return a stacked-branch warning string, or '' if branch is clean.

    A branch is stacked when merge-base..HEAD commits do not reference
    starter_ticket_id (B1-B6):
    - Uses canonical get_merge_base(), not a hardcoded 'master' ref (B1).
    - Word-boundary, case-insensitive match (B2, B3).
    - Fires also when <25% of commits are in-scope (partial-stack) (B4).
    - Caps log at 50 commits (B41).
    - Accepts explicit starter_ticket_id; returns "STARTER UNKNOWN" warning
      when caller passes an empty id (B6).
    """
    if not starter_ticket_id:
        return (
            'STARTER UNKNOWN — diff signals unevaluated. '
            'Could not determine stacked-branch status without a ticket ID.'
        )

    base = get_merge_base()
    if not base:
        return ''
    exit_code, out, _ = run([
        'git', 'log', '--max-count=50', '--format=%s', f'{base}..HEAD',
    ])
    if exit_code != 0 or not out.strip():
        return ''

    subjects = [s for s in out.strip().splitlines() if s.strip()]
    ticket_re = _ticket_re(starter_ticket_id)
    in_scope = [s for s in subjects if ticket_re.search(s)]
    total = len(subjects)

    capped_note = ' (showing first 50 of many)' if total >= 50 else ''

    if not in_scope:
        return (
            f"STACKED BRANCH DETECTED: {base}..HEAD contains {total} commit(s)"
            f"{capped_note}, none reference {starter_ticket_id}. "
            f"The branch is built on top of unmerged predecessor work. "
            f"Diff stats below describe the predecessor's diff, NOT this MR's "
            f"deliverables. Do NOT request `branch_diff` and do NOT describe "
            f"predecessor content as this MR's work."
        )

    in_scope_pct = len(in_scope) / total
    if in_scope_pct < 0.25:
        return (
            f"MOSTLY-STACKED BRANCH: {base}..HEAD contains {total} commit(s)"
            f"{capped_note}; only {len(in_scope)} of {total} reference "
            f"{starter_ticket_id}. Diff stats are dominated by predecessor work. "
            f"Do NOT request `branch_diff` — diff content would mostly describe "
            f"predecessor changes, not this MR's deliverables."
        )

    return ''
