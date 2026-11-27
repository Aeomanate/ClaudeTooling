#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""`mr script session_state` - read/write .ai/cache/{branch}/session_state.md.

Same file and field format the PreCompact/SessionStart:compact hooks
(claude/hooks/precompact.py, claude/hooks/resume_after_compact.py) use.
The hooks are self-contained scripts (no import of git_hooks_impl, since
they must run in any project the orchestrator skill is installed into) and
duplicate the parse/write logic independently - this command is the
convenience path for the orchestrator to read or update the same file from
inside this repo, not a shared library the hooks import.

Usage:
    mr script session_state get
    mr script session_state set <role> <workflow> <phase> [step]

`get` prints the current fields, one per line, or "NONE" if no state file
exists for the current branch. `set` writes the file, overwriting any
prior content.
"""
import os

from git_hooks_impl.entry_points.commands._shared import project_root, run_capture
from git_hooks_impl.plan.cache import _sanitize_branch_name

HELP = """\
mr script session_state get
mr script session_state set <role> <workflow> <phase> [step]

Reads or writes the compaction resume point at
.ai/cache/{branch}/session_state.md.

Examples:
  mr script session_state get
  mr script session_state set refactorer convergence 4 4.2

`get` prints the saved fields, or NONE if nothing is saved yet.

`set` overwrites the file for the current branch. `step` is optional.

Exit codes: `get` always returns 0. `set` returns 0 on success, 1 on a
bad argument count or an unrecognized subcommand.
"""


def _current_branch() -> str:
    _, out, _ = run_capture(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
    return out.strip()


def _state_path(root: str, branch: str) -> str:
    return os.path.join(root, '.ai', 'cache', _sanitize_branch_name(branch), 'session_state.md')


def _get(root: str, branch: str) -> int:
    path = _state_path(root, branch)
    if not os.path.isfile(path):
        print('NONE')
        return 0
    with open(path, encoding='utf-8') as f:
        print(f.read(), end='')
    return 0


def _set(root: str, branch: str, argv: list) -> int:
    if len(argv) < 3:
        print('Usage: mr script session_state set <role> <workflow> <phase> [step]')
        return 1
    role, workflow, phase = argv[0], argv[1], argv[2]
    step = argv[3] if len(argv) > 3 else None

    path = _state_path(root, branch)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = [f'Role: {role}', f'Workflow: {workflow}', f'Phase: {phase}']
    if step:
        lines.append(f'Step: {step}')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print(f'CLEAN: wrote {path}')
    return 0


def run(argv: list) -> int:
    if not argv or argv[0] in ('--help', '-h'):
        print(HELP)
        return 0

    root = project_root()
    branch = _current_branch()
    if not branch:
        print('ERR: could not determine current branch')
        return 1

    if argv[0] == 'get':
        return _get(root, branch)
    if argv[0] == 'set':
        return _set(root, branch, argv[1:])

    print(f'Unknown subcommand: {argv[0]}')
    print(HELP)
    return 1
