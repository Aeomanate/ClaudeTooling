#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Plan cache management - per-branch cache save/restore/prune.

Extracted from extract_plan.py to break the mutual dependency between
sync_mr and extract_plan. Both modules need cache operations, but
neither should depend on the other for them.
"""

import contextlib
import os
import re
import shutil
import sys

from git_hooks_impl.logger import dbg, log, ok, warn
from git_hooks_impl.plan.parser import extract_meta
from git_hooks_impl.utils import PLAN_FILE, run

_CACHE_DIR = os.path.join('.ai', 'cache')

def load_gen_cache(branch: str) -> 'dict[int, str]':
    """Read step1.md..step6.md from gen_cache/. Return {step_number: content}.

    Missing steps are simply absent from the dict. Caller decides resume behavior.
    """
    cache_dir = os.path.join(_CACHE_DIR, _sanitize_branch_name(branch), 'gen_cache')
    result = {}
    for step_num in range(1, 7):
        step_path = os.path.join(cache_dir, f'step{step_num}.md')
        try:
            with open(step_path, encoding='utf-8') as f:
                result[step_num] = f.read()
        except OSError:
            pass
    return result


def invalidate_gen_cache(branch: str) -> None:
    """Remove all stepN.md and .version files from .ai/cache/<branch>/gen_cache/."""
    cache_dir = os.path.join(_CACHE_DIR, _sanitize_branch_name(branch), 'gen_cache')
    if not os.path.isdir(cache_dir):
        return
    for step_num in range(1, 7):
        step_path = os.path.join(cache_dir, f'step{step_num}.md')
        with contextlib.suppress(OSError):
            os.remove(step_path)
    version_path = os.path.join(cache_dir, '.version')
    with contextlib.suppress(OSError):
        os.remove(version_path)
    dbg(f"Invalidated gen_cache for branch '{branch}'")


def _sanitize_branch_name(branch):
    """Sanitize a branch name for use as a directory name.

    'private/oziuz/ai_plan' -> 'private_oziuz_ai_plan'
    'productname/fixes/PROJECTNAME-1234_fix' -> 'productname_fixes_productname_1234_fix'
    'productname/fixes/PROJECTNAME-1234_fix' -> 'productname_fixes_productname_1234_fix'
    """
    text = branch.replace('/', '_').replace('-', '_').lower()
    text = re.sub(r'[^a-z0-9_]', '', text)
    return text[:80] if text else 'unknown'


def _conflict_path(branch, kind):
    """Build path for a conflict artifact inside the branch cache dir.

    _conflict_path('productname/fixes/PROJECTNAME-1_fix', 'remote')
    _conflict_path('productname/fixes/PROJECTNAME-1_fix', 'remote')
    -> '.ai/cache/productname_fixes_productname1_fix/remote_PLAN.md'
    -> '.ai/cache/productname_fixes_productname1_fix/remote_PLAN.md'

    kind is one of: 'local', 'remote', 'merged'.
    """
    return os.path.join(_CACHE_DIR, _sanitize_branch_name(branch),
                        f'{kind}_PLAN.md')


def _save_cache(branch, force=False):
    """Copy BRANCH_PLAN.md -> .ai/cache/<branch>/cached_BRANCH_PLAN.md.

    Checks UUID before overwriting - if the existing cache has a different
    UUID than the plan on disk, realigns the cache (prevents cross-branch
    cache corruption).

    When force=True, the UUID guard is bypassed (used after mr plangen --force
    where the UUID change is intentional, not cross-branch contamination).
    """
    if not os.path.isfile(PLAN_FILE):
        return
    try:
        cache_dir = os.path.join(_CACHE_DIR, _sanitize_branch_name(branch))
        cache_path = os.path.join(cache_dir, 'cached_BRANCH_PLAN.md')

        # UUID guard: don't overwrite cache with a plan from a different branch
        with open(PLAN_FILE, encoding='utf-8') as f:
            plan_content = f.read()
        plan_uuid = extract_meta(plan_content).get('plan-uuid', '')

        if not force and plan_uuid and os.path.isfile(cache_path):
            with open(cache_path, encoding='utf-8') as f:
                cached_uuid = extract_meta(f.read()).get('plan-uuid', '')
            if cached_uuid and plan_uuid != cached_uuid:
                warn(f'UUID mismatch - realigning cache to current plan for {branch}')
                dbg(f'  plan UUID:  {plan_uuid}')
                dbg(f'  cache UUID: {cached_uuid}')
                with contextlib.suppress(OSError):
                    os.remove(cache_path)

        os.makedirs(cache_dir, exist_ok=True)
        shutil.copy2(PLAN_FILE, cache_path)
        dbg(f'Saved cache: {PLAN_FILE} -> {cache_path}')
    except OSError as exc:
        warn(f'Could not save cache for {branch}: {exc}')


def _save_mr_description(branch, description):
    """Save the full MR description to the branch cache for comparison.

    Stores the entire MR body (not just the plan section) at
    .ai/cache/<branch>/last_mr_description.md so future operations
    can compare local plan against the actual MR state.
    """
    try:
        cache_dir = os.path.join(_CACHE_DIR, _sanitize_branch_name(branch))
        path = os.path.join(cache_dir, 'last_mr_description.md')
        os.makedirs(cache_dir, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(description)
        dbg(f'Saved MR description: {path} ({len(description)} chars)')
    except OSError as exc:
        warn(f'Could not save MR description for {branch}: {exc}')


def _save_base(branch, content):
    """Save stripped plan content as the push base for 3-way conflict detection.

    Written alongside the cache: .ai/cache/<branch>/base_PLAN.md.
    Used later to distinguish true conflicts (both sides changed same region)
    from non-overlapping edits.
    """
    try:
        cache_dir = os.path.join(_CACHE_DIR, _sanitize_branch_name(branch))
        os.makedirs(cache_dir, exist_ok=True)
        base_path = os.path.join(cache_dir, 'base_PLAN.md')
        with open(base_path, 'w', encoding='utf-8') as f:
            f.write(content)
        dbg(f'Saved push base: {base_path}')
    except OSError as exc:
        warn(f'Could not save base for {branch}: {exc}')


def _load_base(branch):
    """Load the push base for 3-way conflict detection. Returns None if missing."""
    base_path = os.path.join(_CACHE_DIR, _sanitize_branch_name(branch),
                             'base_PLAN.md')
    try:
        with open(base_path, encoding='utf-8') as f:
            return f.read()
    except OSError:
        return None


def _restore_cache(branch):
    """Copy .ai/cache/<branch>/cached_BRANCH_PLAN.md -> .ai/BRANCH_PLAN.md.

    Uses copy (not move) so the cache survives the restore - switching
    away and back doesn't require an MR fetch.
    Returns True if cache existed and was restored, False otherwise.
    """
    cache_path = os.path.join(_CACHE_DIR, _sanitize_branch_name(branch),
                              'cached_BRANCH_PLAN.md')
    if not os.path.isfile(cache_path):
        return False
    try:
        os.makedirs(os.path.dirname(PLAN_FILE), exist_ok=True)
        shutil.copy2(cache_path, PLAN_FILE)
        ok(f'Restored {PLAN_FILE} from cache ({branch})')
        dbg(f'Restored cache: {cache_path} -> {PLAN_FILE}')
        return True
    except OSError as exc:
        warn(f'Could not restore cache for {branch}: {exc}')
        return False


def _resolve_branch_from_ref(ref):
    """Resolve a SHA ref -> branch name via git name-rev.

    Returns '' on failure (detached HEAD, tags, ambiguous refs).
    """
    if not ref:
        return ''
    exit_code, out, _ = run(['git', 'name-rev', '--name-only', ref])
    if exit_code != 0:
        return ''
    name = out.strip()
    # git name-rev may return 'tags/...' for tag refs
    if name.startswith('tags/') or name == 'undefined':
        return ''
    # Strip trailing ~N or ^N suffixes (e.g. 'branch~2')
    name = re.sub(r'[~^]\d+$', '', name)
    return name


def _prune_stale_caches():
    """Remove cache dirs for branches that no longer exist locally.

    Forward-maps branch names via _sanitize_branch_name and compares
    against cache directory names.  Best-effort, never blocks.
    """
    if not os.path.isdir(_CACHE_DIR):
        return
    try:
        exit_code, out, _ = run(['git', 'branch', '--list', '--format=%(refname:short)'])
        if exit_code != 0:
            return
        local_branches = {b.strip() for b in out.splitlines() if b.strip()}
        valid_dirs = {_sanitize_branch_name(b) for b in local_branches}

        pruned = 0
        for entry in os.listdir(_CACHE_DIR):
            full_dir = os.path.join(_CACHE_DIR, entry)
            if not os.path.isdir(full_dir):
                continue
            if entry not in valid_dirs:
                shutil.rmtree(full_dir, ignore_errors=True)
                pruned += 1

        if pruned:
            log(f'Pruned {pruned} stale cache dir(s)')
            dbg(f'Pruned {pruned} stale cache(s)')
    except Exception:
        pass  # never block


_NULL_SHA = '0' * 40


def _read_deleted_branches():
    """Parse reference-transaction stdin for branch deletions.

    reference-transaction hook receives on stdin:
      <old-sha> <new-sha> <ref-name>
    Branch deletion: new-sha is all zeros, ref starts with refs/heads/.
    """
    deleted = []
    try:
        for line in sys.stdin:
            parts = line.strip().split()
            if len(parts) >= 3:
                new_sha = parts[1]
                ref_name = parts[2]
                if new_sha == _NULL_SHA and ref_name.startswith('refs/heads/'):
                    branch = ref_name[len('refs/heads/'):]
                    deleted.append(branch)
    except (OSError, ValueError):
        pass
    return deleted
