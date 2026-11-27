#!/usr/bin/env python
"""PostToolUse hook: warns about file:line citations in human-facing
documentation and code comments (STYLE-9 NO-LINE-CITATIONS).

Detection only: never rewrites a file. A file:line citation ("foo.cpp:42")
names no fact by itself; fixing it requires a human-meaningful replacement
(a function or class name), which this hook cannot infer. It reports hits
so the fact can be restated by name.

Reads PostToolUse event JSON from stdin per the hook contract.
"""
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

_CHECKED_EXTENSIONS = ('.cpp', '.hpp', '.h', '.py', '.md', '.txt')

# filename.ext:123  or  filename.ext:12-34  or  filename.ext:12,34
_CITATION_RE = re.compile(
    r'\b[A-Za-z0-9_][A-Za-z0-9_./\\-]*\.[A-Za-z0-9]{1,5}:\d+(?:[-,]\d+)*\b'
)

# Path segments that store or discuss exact line numbers as data, not
# documentation prose: the deployed harness directory and the plan cache.
# Matched as an exact path component. ".claude" is dotted on purpose - it
# must not match a bare "claude" segment, or the source repo's own
# claude/ tree (C:/Kragle/ai_tooling/claude/...) would be excluded too.
_EXCLUDED_DIR_SEGMENTS = ('.claude', 'cache')

# Exact file, checked against the path's suffix, regardless of directory.
_EXCLUDED_FILES = ('.ai/BRANCH_PLAN.md',)


def _extract_file_path(event):
    tool_input = event.get('tool_input') or {}
    return tool_input.get('file_path')


def _is_excluded(file_path):
    normalized = file_path.replace('\\', '/')
    for excluded in _EXCLUDED_FILES:
        if normalized.endswith(excluded):
            return True
    parts = normalized.split('/')
    return any(part in _EXCLUDED_DIR_SEGMENTS for part in parts)


def _find_citation_lines(lines):
    """Return 1-indexed line numbers containing a file:line citation."""
    return [i + 1 for i, line in enumerate(lines) if _CITATION_RE.search(line)]


def main():
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0

    if event.get('tool_name') not in ('Edit', 'Write'):
        return 0

    file_path = _extract_file_path(event)
    if not file_path:
        return 0

    if not file_path.lower().endswith(_CHECKED_EXTENSIONS):
        return 0

    if _is_excluded(file_path):
        return 0

    if not os.path.isfile(file_path):
        return 0

    try:
        with open(file_path, encoding='utf-8') as f:
            lines = f.readlines()
    except (OSError, UnicodeDecodeError):
        return 0

    hits = _find_citation_lines(lines)
    if not hits:
        return 0

    line_list = ', '.join(str(n) for n in hits[:10])
    more = f' (+{len(hits) - 10} more)' if len(hits) > 10 else ''
    message = (
        f'[check_line_citations] {file_path}: file:line citation on '
        f'line(s) {line_list}{more} - STYLE-9 NO-LINE-CITATIONS: name the '
        f'file, class, or function instead.'
    )
    print(json.dumps({
        'hookSpecificOutput': {
            'hookEventName': 'PostToolUse',
            'additionalContext': message,
        }
    }))
    return 0


if __name__ == '__main__':
    sys.exit(main())
