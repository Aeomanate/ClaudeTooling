#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""check_comment_style.py - detect STYLE-8 CODE-COMMENTS violations in a diff.

Scans added lines in a git diff for comment-register violations: banned
first-person-plural wording, filler openers, and comment blocks over the
four-line hard cap. This is the mechanical half of STYLE-8 - it cannot
judge whether a comment is disproportionate to the code it guards. A
clean run here does not mean the prose is clean; the second-pass agent
covers proportionality.

Usage:
    mr script check_comment_style [DIFF_SPEC]

With no argument, scans staged changes (`git diff --cached`). With an
argument, runs `git diff DIFF_SPEC` - e.g. `HEAD~5` scans everything
changed across the last five commits.

Exit code 0 = clean; non-zero = violations found (suitable for CI gating).
"""
import re
import subprocess
import sys

from claude.hooks._checks import BANNED_REGISTER, COMMENT_MARKERS

HELP = """\
mr script check_comment_style

Scans added comment lines in a diff for STYLE-8 violations: banned
first-person-plural words ("we", "let's", "our"), filler openers ("Note
that", "Basically"), and comment blocks over 4 lines.

Examples:
  mr script check_comment_style        # staged changes (the normal case)
  mr script check_comment_style HEAD~5 # everything in the last 5 commits

Scope: this is the mechanical half of STYLE-8 only. It cannot tell
whether a comment is disproportionate to the code it guards - a
second-pass agent covers that.

Exit code: 0 means clean, non-zero means violations found.
"""

_MAX_BLOCK_LINES = 4

_HUNK_RE = re.compile(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@')
_FILE_RE = re.compile(r'^\+\+\+ b/(.+)$')


def _extension(file_path):
    idx = file_path.rfind('.')
    return file_path[idx:] if idx != -1 else ''


def _comment_text(marker, line_content):
    """Return the line stripped of leading whitespace and comment marker, or None."""
    stripped = line_content.lstrip()
    if not stripped.startswith(marker):
        return None
    return stripped[len(marker):].strip()


def iter_added_comment_lines(diff_text):
    """Yield (file_path, line_no, comment_text) for each added comment line."""
    current_file = None
    current_line_no = None
    for line in diff_text.splitlines():
        if line.startswith('+++ '):
            m = _FILE_RE.match(line)
            current_file = m.group(1) if m else None
            continue
        if line.startswith('@@'):
            m = _HUNK_RE.match(line)
            if m:
                current_line_no = int(m.group(1))
            continue
        if current_file is None or current_line_no is None:
            continue
        if line.startswith('\\'):
            continue
        if line.startswith('+'):
            marker = COMMENT_MARKERS.get(_extension(current_file))
            if marker:
                text = _comment_text(marker, line[1:])
                if text is not None:
                    yield (current_file, current_line_no, text)
            current_line_no += 1
        elif line.startswith('-'):
            continue
        else:
            current_line_no += 1


def find_register_violations(diff_text):
    """Return a list of (file, line_no, reason) for banned-register comment lines."""
    violations = []
    for file_path, line_no, text in iter_added_comment_lines(diff_text):
        for pattern, reason in BANNED_REGISTER:
            if pattern.search(text):
                violations.append((file_path, line_no, reason))
                break
    return violations


def find_budget_violations(diff_text):
    """Return a list of (file, start_line, end_line) for comment blocks over the 4-line cap."""
    violations = []
    block_file = None
    block_start = None
    block_len = 0

    def _close_block():
        if block_len > _MAX_BLOCK_LINES:
            violations.append((block_file, block_start, block_start + block_len - 1))

    for file_path, line_no, _text in iter_added_comment_lines(diff_text):
        if file_path == block_file and line_no == block_start + block_len:
            block_len += 1
        else:
            _close_block()
            block_file, block_start, block_len = file_path, line_no, 1
    _close_block()
    return violations


def get_diff(diff_spec):
    args = ['git', 'diff', diff_spec] if diff_spec else ['git', 'diff', '--cached']
    result = subprocess.run(args, capture_output=True, text=True, check=True)
    return result.stdout


def main(argv):
    if argv and argv[0] in ('--help', '-h'):
        print(HELP)
        return 0

    diff_spec = argv[0] if argv else None
    diff_text = get_diff(diff_spec)

    register_violations = find_register_violations(diff_text)
    budget_violations = find_budget_violations(diff_text)
    total = len(register_violations) + len(budget_violations)

    if total:
        print(f'FAIL: {total} STYLE-8 comment-style violation(s) found.')
        print()
        for file_path, line_no, reason in register_violations:
            print(f'{file_path}:{line_no}: {reason}')
        for file_path, start, end in budget_violations:
            print(f'{file_path}:{start}-{end}: comment block exceeds {_MAX_BLOCK_LINES}-line cap')
        print()
        print('This check covers banned register and the hard line cap only.')
        print('It cannot judge proportionality to the guarded code - see the')
        print('second-pass agent for that half of STYLE-8.')
        return 1

    print('PASS: no mechanical STYLE-8 violations in the scanned diff.')
    print('This does not confirm proportionality - see the second-pass agent.')
    return 0


def run(argv: list) -> int:
    """Registry entry point - delegates to main()."""
    return main(argv)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
