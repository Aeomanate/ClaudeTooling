#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""check_plan_paths — BRANCH_PLAN.md path-existence logic.

Not a registered `mr script` command on its own - `mr script audit_plan`
imports this module's functions as part of its combined report. Kept as
its own module (rather than folded inline) because its own tests target
these functions directly.

Extracts candidate file paths from backtick-quoted spans and markdown link
targets, filters out URLs and non-project paths, then checks the survivors
exist relative to the project root.
"""

import os
import re

from git_hooks_impl.entry_points.commands._shared import project_root

_BACKTICK_PATH_RE = re.compile(r'`([^`]*/[^`]+)`')
_LINK_PATH_RE = re.compile(r'\(([^)]*/[^)]+\.(?:md|sh|py|rst|json|cfg))\)')


def _is_checkable(path: str) -> bool:
    """Returns True if path looks like a real project-relative file path."""
    if re.match(r'https?://', path):
        return False
    if re.search(r'[{<*%]', path):
        return False
    if re.search(r'[ =>]', path):
        return False
    if re.match(r'/[a-z]', path):
        return False
    if re.search(r'\.ai/cache/', path):
        return False
    return bool(re.match(r'\.|tools/|docs/|reponame/|utils/|tests/', path))


def run(argv: list) -> int:
    """Prints missing BRANCH_PLAN.md paths and a count. Returns 1 if any missing."""
    root = project_root()
    plan_path = os.path.join(root, '.ai', 'BRANCH_PLAN.md')
    if not os.path.isfile(plan_path):
        print(f'ERR: {plan_path} not found')
        return 1

    with open(plan_path, encoding='utf-8') as f:
        text = f.read()

    print('=== Checking file paths in BRANCH_PLAN.md ===')

    paths = set(_BACKTICK_PATH_RE.findall(text)) | set(_LINK_PATH_RE.findall(text))

    checked = 0
    missing = 0
    for path in sorted(paths):
        if not _is_checkable(path):
            continue
        checked += 1
        if not os.path.exists(os.path.join(root, path)):
            print(f'  MISSING: {path}')
            missing += 1

    print(f'\nChecked {checked} paths, {missing} missing')
    return 1 if missing > 0 else 0
