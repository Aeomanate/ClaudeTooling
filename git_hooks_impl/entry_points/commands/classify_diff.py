#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""`mr script classify_diff` - tags a diff `mechanical` or `standard`.

A deterministic stand-in for gitter's diff-size tier (roles/gitter/rules.md,
the tier definition next to G7): "mechanical" means under 3 files and under
30 changed lines, with no added line introducing a new function, class, or
control-flow construct in a code file. Anything else is "standard". A
mechanical diff collapses gitter's separate rules-check + consistency-check
dispatches into one combined pass (roles/gitter/workflow.md Step 2.2/3.2)
and narrows refactorer's clean-room re-audit scope (roles/refactorer/
workflow.md Phase 4) - see those files for what the tag actually changes.
This script only classifies; it does not skip anything itself.

Usage:
    mr script classify_diff [DIFF_SPEC]

With no argument, classifies staged changes (`git diff --cached`). With an
argument, classifies `git diff DIFF_SPEC`.

Exit code: always 0 - this is a classification, not a pass/fail check.
"""
import re
import subprocess
import sys

HELP = """\
mr script classify_diff

Tags a diff "mechanical" or "standard". Mechanical means under 3 files,
under 30 changed lines, and no new function, class, or control flow in a
code file. Anything else is standard.

Examples:
  mr script classify_diff          # staged changes (the normal case)
  mr script classify_diff HEAD~5   # everything in the last 5 commits

Output: a short report, then the tag alone on the last line.

Exit code: always 0. This labels the diff, it does not pass or fail it.
"""

_MAX_FILES = 3
_MAX_CHANGED_LINES = 30

_CODE_EXTENSIONS = (
    '.py', '.cpp', '.cc', '.c', '.h', '.hpp', '.cxx', '.js', '.ts',
)

_NEW_CONSTRUCT_RES = (
    re.compile(r'^\s*(def|class)\s'),
    re.compile(r'^\s*(async\s+)?function\s'),
    re.compile(r'^\s*(if|elif|else|for|while|switch|case|try|catch|except|finally)\b'),
    re.compile(r'\b(class|struct)\s+\w+\s*[:{]'),
)

_FILE_RE = re.compile(r'^\+\+\+ b/(.+)$')


def _extension(file_path):
    idx = file_path.rfind('.')
    return file_path[idx:] if idx != -1 else ''


def _diff_args(diff_spec):
    return ['git', 'diff', diff_spec] if diff_spec else ['git', 'diff', '--cached']


def get_diff_text(diff_spec):
    result = subprocess.run(_diff_args(diff_spec), capture_output=True, text=True, check=True)
    return result.stdout


def get_numstat(diff_spec):
    """Returns (file_count, changed_lines) from `git diff --numstat`."""
    args = _diff_args(diff_spec)
    args.insert(2, '--numstat')
    result = subprocess.run(args, capture_output=True, text=True, check=True)
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    changed = 0
    for line in lines:
        parts = line.split('\t')
        if len(parts) < 2:
            continue
        added, removed = parts[0], parts[1]
        if added.isdigit():
            changed += int(added)
        if removed.isdigit():
            changed += int(removed)
    return len(lines), changed


def has_new_construct(diff_text):
    """True if any added line in a code file matches a new-construct pattern."""
    current_file = None
    for line in diff_text.splitlines():
        if line.startswith('+++ '):
            m = _FILE_RE.match(line)
            current_file = m.group(1) if m else None
            continue
        if not line.startswith('+') or line.startswith('+++'):
            continue
        if current_file is None or _extension(current_file) not in _CODE_EXTENSIONS:
            continue
        content = line[1:]
        if any(pattern.search(content) for pattern in _NEW_CONSTRUCT_RES):
            return True, current_file
    return False, None


def run(argv: list) -> int:
    if argv and argv[0] in ('--help', '-h'):
        print(HELP)
        return 0

    diff_spec = argv[0] if argv else None
    diff_text = get_diff_text(diff_spec)
    file_count, changed_lines = get_numstat(diff_spec)
    new_construct, construct_file = has_new_construct(diff_text)

    print(f'Files changed: {file_count} (threshold: < {_MAX_FILES})')
    print(f'Lines changed: {changed_lines} (threshold: < {_MAX_CHANGED_LINES})')
    if new_construct:
        print(f'New function/class/control-flow construct found in {construct_file}')
    else:
        print('No new function/class/control-flow construct in a code file')

    is_mechanical = (
        file_count < _MAX_FILES
        and changed_lines < _MAX_CHANGED_LINES
        and not new_construct
    )
    print()
    print('mechanical' if is_mechanical else 'standard')
    return 0


if __name__ == '__main__':
    sys.exit(run(sys.argv[1:]))
