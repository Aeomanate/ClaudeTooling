#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""audit_sections — BRANCH_PLAN.md section/heading logic.

Not a registered `mr script` command on its own - `mr script audit_plan`
imports this module's functions as part of its combined report. Kept as
its own module (rather than folded inline) because its own tests target
these functions directly.
"""

import os
import re

from git_hooks_impl.entry_points.commands._shared import project_root

_SECTION_RE = re.compile(r'^#{2,4}')
_CONTENT_RE = re.compile(r'^[^ \t#]')


def _find_empty_sections(lines: list) -> list:
    """Returns 'line: EMPTY — heading' entries for headings with no content before the next one."""
    empty = []
    prev_heading = None
    for i, line in enumerate(lines, start=1):
        stripped = line.rstrip('\n')
        if _SECTION_RE.match(line):
            if prev_heading is not None:
                empty.append(f'{i - 1}: EMPTY — {prev_heading}')
            prev_heading = stripped
        elif _CONTENT_RE.match(stripped):
            prev_heading = None
    if prev_heading is not None:
        empty.append(f'{len(lines)}: EMPTY — {prev_heading}')
    return empty


def run(argv: list) -> int:
    """Prints BRANCH_PLAN.md headings, section count, and empty sections."""
    root = project_root()
    plan_path = os.path.join(root, '.ai', 'BRANCH_PLAN.md')
    if not os.path.isfile(plan_path):
        print(f'ERR: {plan_path} not found')
        return 1

    with open(plan_path, encoding='utf-8') as f:
        lines = f.readlines()

    print('=== BRANCH_PLAN.md sections ===')
    for i, line in enumerate(lines, start=1):
        if _SECTION_RE.match(line):
            print(f'{i}:{line.rstrip()}')

    print()
    print('=== Section count ===')
    print(sum(1 for line in lines if _SECTION_RE.match(line)))

    print()
    print('=== Empty sections (heading followed by another heading) ===')
    for entry in _find_empty_sections(lines):
        print(entry)
    return 0
