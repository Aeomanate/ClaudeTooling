#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""check_stale_refs — BRANCH_PLAN.md stale-reference logic.

Not a registered `mr script` command on its own - `mr script audit_plan`
imports this module's functions as part of its combined report. Kept as
its own module (rather than folded inline) because its own tests target
these functions directly.

With no args, checks bare filename markdown link texts and `../`
cross-directory references. Extra args are treated as additional
case-insensitive regex patterns to search for. All checks run only over
the active plan (everything before the Decisions Log, which is
append-only history).
"""

import os
import re

from git_hooks_impl.entry_points.commands._shared import project_root

_BARE_LINK_RE = re.compile(r'\[[a-z_-]+\.md\]\(')
_CROSS_DIR_RE = re.compile(r'\]\(\.\./')


def _report(active_lines: list, pattern: re.Pattern, label: str) -> bool:
    """Prints matching lines under label. Returns True if any matched."""
    print()
    print(f'--- {label} ---')
    matches = [
        (i + 1, line.rstrip('\n'))
        for i, line in enumerate(active_lines)
        if pattern.search(line)
    ]
    if not matches:
        print('  CLEAN')
        return False
    for line_no, line in matches:
        print(f'{line_no}:{line}')
    return True


def run(argv: list) -> int:
    """Runs the plan lint checks. Returns 0 if clean, 1 if any issue found."""
    root = project_root()
    plan_path = os.path.join(root, '.ai', 'BRANCH_PLAN.md')
    if not os.path.isfile(plan_path):
        print('ERR: .ai/BRANCH_PLAN.md not found')
        return 1

    with open(plan_path, encoding='utf-8') as f:
        lines = f.readlines()

    decisions_idx = next(
        (i for i, line in enumerate(lines) if '## Decisions Log' in line), None,
    )
    active_lines = lines if decisions_idx is None else lines[:decisions_idx]

    print('=== Plan lint: .ai/BRANCH_PLAN.md ===')

    issues = 0
    if _report(active_lines, _BARE_LINK_RE, 'Bare filename link texts'):
        issues += 1
    if _report(active_lines, _CROSS_DIR_RE, 'Cross-directory ../ references'):
        issues += 1

    for pattern in argv:
        label = f"Custom: '{pattern}' (outside Decisions Log)"
        if _report(active_lines, re.compile(pattern, re.IGNORECASE), label):
            issues += 1

    print()
    if issues == 0:
        print('=== ALL CLEAN ===')
        return 0
    print(f'=== {issues} issue categories found ===')
    return 1
