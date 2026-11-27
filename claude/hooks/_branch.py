#!/usr/bin/env python
"""Shared branch-name sanitizing and cheap local git facts for the
orchestrator's hooks.

One implementation, imported by session_start.py, precompact.py, and
resume_after_compact.py as a sibling module - hooks run as
`python ~/.claude/hooks/<name>.py`, so this file's own directory is on
sys.path and no git_hooks_impl import is needed (hooks are self-contained).

Must match `git_hooks_impl/plan/cache.py::_sanitize_branch_name` exactly,
or the write and read sides of `.ai/cache/{sanitized_branch}/` look in
different directories. That function runs under the repo's own
interpreter and is the source of truth this one has to mirror.

The `git`-backed helpers below are local-only (no network call) - cheap
enough to re-run on every SessionStart, cold or post-compaction alike.
"""
import os
import re
import subprocess


def sanitize_branch(branch):
    """Sanitize a branch name for use as a directory name.

    'private/oziuz/ai_plan' -> 'private_oziuz_ai_plan'
    'productname/fixes/PROJECTNAME-1234_fix' -> 'productname_fixes_productname_1234_fix'
    'productname/fixes/PROJECTNAME-1234_fix' -> 'productname_fixes_productname_1234_fix'
    """
    text = branch.replace('/', '_').replace('-', '_').lower()
    text = re.sub(r'[^a-z0-9_]', '', text)
    return text[:80] if text else 'unknown'


def git(*args):
    try:
        return subprocess.run(
            ['git', *args], capture_output=True, text=True, timeout=5
        ).stdout.strip()
    except Exception:
        return ''


def current_branch():
    return git('rev-parse', '--abbrev-ref', 'HEAD')


def default_branch():
    return (
        git('symbolic-ref', '--short', 'refs/remotes/origin/HEAD') or 'origin/master'
    ).rsplit('/', 1)[-1]


def local_plan_present():
    return os.path.isfile(os.path.join('.ai', 'BRANCH_PLAN.md'))


def other_worktrees():
    """Other git worktrees for this repo, one `git worktree list` line each,
    excluding the current one. Empty list if none, not a git repo, or on
    any failure - callers print nothing rather than guess."""
    current = os.path.normcase(os.path.normpath(git('rev-parse', '--show-toplevel') or ''))
    if not current:
        return []
    return [
        line for line in git('worktree', 'list').splitlines()
        if line and os.path.normcase(os.path.normpath(line.split()[0])) != current
    ]
