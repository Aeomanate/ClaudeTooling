#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""`mr script plan_summary` — BRANCH_PLAN.md health summary.

Section count, word count, hash, freshness. Run before and after plan
maintenance to verify changes.
"""

import datetime
import os
import re

from git_hooks_impl.entry_points.commands._shared import project_root

HELP = """\
mr script plan_summary

Prints a quick health summary of .ai/BRANCH_PLAN.md: size, line count,
section count, checkbox counts, meta hash, last-modified time, and the
Decisions Log entry count.

Example:
  mr script plan_summary

Run this before and after plan maintenance to confirm the edit did what
you intended - it is a snapshot, not a violation report.

Exit code: 1 if BRANCH_PLAN.md is missing, 0 otherwise.
"""

_SECTION_RE = re.compile(r'^#{2,4}')
_CHECKBOX_RE = re.compile(r'- \[.\]')
_CHECKBOX_DONE_RE = re.compile(r'- \[x\]')
_CHECKBOX_PENDING_RE = re.compile(r'- \[ \]')
_HASH_RE = re.compile(r'plan-hash:\s*(\S*)')
_DECISIONS_HEADING_RE = re.compile(r'^## Decisions Log')


def run(argv: list) -> int:
    """Prints BRANCH_PLAN.md size, section/checkbox counts, hash, freshness."""
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

    print('=== BRANCH_PLAN.md Summary ===')
    print(f'File: {plan_path}')
    print(f"Size: {len(text.encode('utf-8'))} bytes")
    print(f'Lines: {len(lines)}')
    print(f'Sections: {sum(1 for line in lines if _SECTION_RE.match(line))}')

    total = sum(1 for line in lines if _CHECKBOX_RE.search(line))
    done = sum(1 for line in lines if _CHECKBOX_DONE_RE.search(line))
    pending = sum(1 for line in lines if _CHECKBOX_PENDING_RE.search(line))
    print(f'Checkboxes: {total} total ({done} done, {pending} pending)')

    hash_match = _HASH_RE.search('\n'.join(lines[:5]))
    print(f"Meta hash: {hash_match.group(1) if hash_match else 'none'}")

    mtime = datetime.datetime.fromtimestamp(os.path.getmtime(plan_path))
    print(f"Last modified: {mtime.isoformat(sep=' ')}")

    print()
    print('=== Decisions Log entries ===')
    decisions_start = next(
        (i for i, line in enumerate(lines) if _DECISIONS_HEADING_RE.match(line)),
        None,
    )
    if decisions_start is None:
        print('Decisions Log section not found')
    else:
        entry_count = sum(1 for line in lines[decisions_start:] if line.startswith('- '))
        print(entry_count)
    return 0
