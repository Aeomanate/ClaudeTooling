#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""`mr script audit_plan` — runs every BRANCH_PLAN.md structural check as one report.

Combines what used to be three separate `mr script` commands (audit_sections,
check_plan_paths, check_stale_refs) into one, the same way
`validate_skill_conventions` aggregates its 6 skill-tree checks. Each
command's own logic still lives in its own module, imported here - this
file only assembles one report and one exit code instead of three.
"""
import os
import re

from git_hooks_impl.entry_points.commands import audit_sections, check_plan_paths, check_stale_refs
from git_hooks_impl.entry_points.commands._shared import project_root

HELP = """\
mr script audit_plan
mr script audit_plan <pattern> [<pattern> ...]

Runs every structural check on .ai/BRANCH_PLAN.md and prints one report:
section headings + empty sections, missing file paths, and stale
references (bare links, ../ cross-refs).

Examples:
  mr script audit_plan
  mr script audit_plan 'PROJECTNAME-\\d+'   # also flag a custom pattern

Extra arguments are additional case-insensitive regex patterns to flag,
same as check_stale_refs took directly.

Exit code: 1 if any check finds an issue, 0 if the plan is clean.
"""


def run(argv: list) -> int:
    if argv and argv[0] in ('--help', '-h'):
        print(HELP)
        return 0

    root = project_root()
    plan_path = os.path.join(root, '.ai', 'BRANCH_PLAN.md')
    if not os.path.isfile(plan_path):
        print(f'ERR: {plan_path} not found')
        return 1

    with open(plan_path, encoding='utf-8') as f:
        lines = f.readlines()
    text = ''.join(lines)

    issues = 0

    print('=== BRANCH_PLAN.md sections ===')
    for i, line in enumerate(lines, start=1):
        if audit_sections._SECTION_RE.match(line):
            print(f'{i}:{line.rstrip()}')
    print()
    print('=== Section count ===')
    print(sum(1 for line in lines if audit_sections._SECTION_RE.match(line)))
    print()
    print('=== Empty sections (heading followed by another heading) ===')
    empty = audit_sections._find_empty_sections(lines)
    for entry in empty:
        print(entry)
    if empty:
        issues += 1

    print()
    print('=== File paths ===')
    paths = (
        set(check_plan_paths._BACKTICK_PATH_RE.findall(text))
        | set(check_plan_paths._LINK_PATH_RE.findall(text))
    )
    missing = 0
    for path in sorted(paths):
        if not check_plan_paths._is_checkable(path):
            continue
        if not os.path.exists(os.path.join(root, path)):
            print(f'  MISSING: {path}')
            missing += 1
    print(f'  {missing} missing' if missing else '  CLEAN: all paths exist')
    if missing:
        issues += 1

    print()
    print('=== Stale references ===')
    decisions_idx = next(
        (i for i, line in enumerate(lines) if '## Decisions Log' in line), None,
    )
    active_lines = lines if decisions_idx is None else lines[:decisions_idx]
    if check_stale_refs._report(
        active_lines, check_stale_refs._BARE_LINK_RE, 'Bare filename link texts'
    ):
        issues += 1
    if check_stale_refs._report(
        active_lines, check_stale_refs._CROSS_DIR_RE, 'Cross-directory ../ references'
    ):
        issues += 1
    for pattern in argv:
        label = f"Custom: '{pattern}' (outside Decisions Log)"
        if check_stale_refs._report(active_lines, re.compile(pattern, re.IGNORECASE), label):
            issues += 1

    print()
    if issues == 0:
        print('=== ALL CLEAN ===')
        return 0
    print(f'=== {issues} issue categories found ===')
    return 1
