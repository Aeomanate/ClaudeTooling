#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Plan merge and conflict resolution — 3-way merge via git merge-file,
interactive conflict dialog, and conflict artifact management.

Extracted from extract_plan.py to break the mutual dependency between
sync_mr and extract_plan. sync_mr._resolve_push_plan_conflict needs
merge functions, but shouldn't depend on the entire extract_plan module.
"""

import contextlib
import os
import subprocess
import tempfile

from git_hooks_impl.dialogs import _build_diff_lines
from git_hooks_impl.logger import dbg, log, warn
from git_hooks_impl.plan.cache import _conflict_path, _load_base


def _print_diff(local_content, remote_content):
    """Print added/removed lines between local and remote BRANCH_PLAN.md.

    Shows line numbers: '-L42: old line' / '+R42: new line'.
    """
    diff_lines = _build_diff_lines(local_content, remote_content)
    if diff_lines:
        for _, text in diff_lines:
            log(f'  {text}')
    else:
        log('(no visible diff — whitespace or hash-line change only)')


def _try_auto_merge(base_content, local_content, remote_content):
    """Try 3-way merge via git merge-file. Returns merged content or None.

    Uses git merge-file -p (stdout mode).  exit_code=0 means clean merge,
    exit_code>0 means conflicts remain (conflict markers in output).
    """
    try:
        # Write temp files in binary mode with \n-only line endings so
        # git merge-file outputs \n (not \r\n on Windows).  Text-mode
        # writes would produce \r\n, and the raw stdout decode would
        # carry \r into _write_plan(), doubling every newline.
        with tempfile.NamedTemporaryFile(
            mode='wb', suffix='.md', delete=False,
        ) as bf, tempfile.NamedTemporaryFile(
            mode='wb', suffix='.md', delete=False,
        ) as lf, tempfile.NamedTemporaryFile(
            mode='wb', suffix='.md', delete=False,
        ) as rf:
            bf.write(base_content.encode('utf-8'))
            bf.flush()
            lf.write(local_content.encode('utf-8'))
            lf.flush()
            rf.write(remote_content.encode('utf-8'))
            rf.flush()

            result = subprocess.run(
                ['git', 'merge-file', '-p', lf.name, bf.name, rf.name],
                capture_output=True, timeout=10)

            # Clean up temp files
            for f in (bf.name, lf.name, rf.name):
                with contextlib.suppress(OSError):
                    os.remove(f)

            if result.returncode == 0:
                return result.stdout.decode('utf-8', errors='replace')
    except Exception as exc:
        dbg(f'git merge-file failed: {exc}')

    return None


def _write_remote(branch, content):
    """Write remote_PLAN.md into the branch cache dir for external merge tools."""
    path = _conflict_path(branch, 'remote')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    log(f'Remote version saved to {path}')


def _write_local_backup(branch, content):
    """Save local BRANCH_PLAN.md before merge overwrites it.

    Safety net: if auto-merge produces bad content, the user can restore
    from git_hooks_impl.ai/cache/<branch>/local_PLAN.md.  Cleaned up on
    next push (overwritten with the new pre-merge snapshot).
    """
    path = _conflict_path(branch, 'local')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    log(f'Local backup saved to {path}')


def _cleanup_remote(branch):
    """Remove remote_PLAN.md after conflict resolution."""
    with contextlib.suppress(OSError):
        os.remove(_conflict_path(branch, 'remote'))


def _show_merge_result(branch, local_content, merged_content):
    """Print diff between original local and merged result, save as merged_PLAN.md.

    Lets the user review what Claude changed before the plan is written.
    """
    log('Merge result — diff vs original local:')
    diff_lines = _build_diff_lines(local_content, merged_content)
    if diff_lines:
        for _, text in diff_lines:
            log(f'  {text}')
    else:
        log('  (no diff — merged identical to local)')
    path = _conflict_path(branch, 'merged')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(merged_content)
    log(f'Merged version saved to {path}')


def _cleanup_merged(branch):
    """Remove merged_PLAN.md after it's been applied."""
    with contextlib.suppress(OSError):
        os.remove(_conflict_path(branch, 'merged'))


def _attempt_auto_merge_with_base(local_content, remote_content, branch):
    """Try 3-way auto-merge using the cached push base.

    Loads the base from cache, attempts git merge-file, and shows the
    merge result diff on success.

    Returns merged content string on success, or None when:
    - no branch provided
    - no push base exists in cache
    - git merge-file reports overlapping changes
    """
    base = _load_base(branch) if branch else None
    if not base:
        return None
    merged = _try_auto_merge(base, local_content, remote_content)
    if not merged:
        return None
    log('Auto-merged (no overlapping changes)')
    if branch:
        _show_merge_result(branch, local_content, merged)
    dbg('Conflict resolved: auto-merged (no overlaps)')
    return merged


def _resolve_conflict(local_content, remote_content, branch=None):
    """Handle MR plan conflict on pull: write artifacts, print suggestion, return non-zero.

    If a push base exists and changes don't overlap, auto-merges via
    git merge-file (clean merge path only).

    On true conflict: writes .local and .remote under .ai/cache/<branch>/
    so the next AI session can propose a merge. Never shows an interactive
    dialog; never calls AI automatically.

    Returns (action, content):
      'merged'  -> auto-merged (3-way, no overlapping changes)
      'local'   -> conflict artifacts written; caller should exit non-zero
    """
    _print_diff(local_content, remote_content)

    merged = _attempt_auto_merge_with_base(local_content, remote_content, branch)
    if merged:
        return 'merged', merged

    if branch:
        _write_local_backup(branch, local_content)
        _write_remote(branch, remote_content)
        local_path = _conflict_path(branch, 'local')
        remote_path = _conflict_path(branch, 'remote')
        warn(
            f'Plan conflict detected. Resolve manually then re-push, '
            f'or `mr gen_plan --force` to take MR version.\n'
            f'  Local:  {local_path}\n'
            f'  Remote: {remote_path}'
        )
    else:
        warn('Plan conflict detected. Resolve manually then re-push, '
             'or `mr gen_plan --force` to take MR version.')

    dbg('Conflict: artifacts written, manual resolution required')
    return 'local', local_content
