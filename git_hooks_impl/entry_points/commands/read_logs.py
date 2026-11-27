#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""`mr script read_logs` — reads hook log + recent commits for debugging."""

import os
import subprocess
import sys

from git_hooks_impl.entry_points.commands._shared import project_root

HELP = """\
mr script read_logs

Prints .ai/hook.log in full, then the last 10 commits (git log --oneline).

Example:
  mr script read_logs

Use this as the first step of fixer investigation - it is the fastest way
to see what the hooks logged around a failure.

Exit code: the exit code of the git log call (0 on success).
"""


def run(argv: list) -> int:
    """Prints hook.log and the last 10 commits. Returns 0."""
    if argv and argv[0] in ('--help', '-h'):
        print(HELP)
        return 0

    # hook.log content is uncontrolled and may contain non-ASCII characters;
    # the default Windows console codepage can't encode them.
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    root = project_root()
    print('=== hook.log ===')
    log_path = os.path.join(root, '.ai', 'hook.log')
    try:
        with open(log_path, encoding='utf-8') as f:
            print(f.read(), end='')
    except FileNotFoundError:
        print('(no hook.log)')
    print('=== Recent commits ===')
    result = subprocess.run(
        ['git', 'log', '--oneline', '-10'], cwd=root, text=True,
    )
    return result.returncode
