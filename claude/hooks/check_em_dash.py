#!/usr/bin/env python
"""PostToolUse hook: replaces em dash (U+2014) with '-' in files touched by
Edit/Write, then reports which lines changed.

Reads PostToolUse event JSON from stdin per the hook contract. Rewrites the
touched file in place when a replacement is made.
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

_EM_DASH = chr(0x2014)
_CHECKED_EXTENSIONS = ('.cpp', '.hpp', '.py', '.md')

# Deployed harness files live under a dotted ".claude" segment. Exclude
# only that exact segment, not a bare "claude" directory, so the source
# repo's own claude/ tree stays in scope.
_EXCLUDED_DIR_SEGMENTS = ('.claude',)


def _extract_file_path(event):
    tool_input = event.get('tool_input') or {}
    return tool_input.get('file_path')


def _is_excluded(file_path):
    normalized = file_path.replace('\\', '/')
    parts = normalized.split('/')
    return any(part in _EXCLUDED_DIR_SEGMENTS for part in parts)


def _replace_em_dashes(lines):
    """Replace em dashes with '-' in place. Return 1-indexed changed line numbers."""
    changed = []
    for i, line in enumerate(lines):
        if _EM_DASH in line:
            lines[i] = line.replace(_EM_DASH, '-')
            changed.append(i + 1)
    return changed


def main():
    try:
        event = json.load(sys.stdin)
    except ValueError:
        # malformed event, never block the tool this hook observes
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
        # unreadable file, never block the tool this hook observes
        return 0

    changed = _replace_em_dashes(lines)
    if not changed:
        return 0

    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
    except OSError:
        # can't write back, still report what would have changed
        pass

    line_list = ', '.join(str(n) for n in changed[:10])
    more = f' (+{len(changed) - 10} more)' if len(changed) > 10 else ''
    message = f'[check_em_dash] {file_path}: replaced em dash with "-" on line(s) {line_list}{more}'
    print(json.dumps({
        'hookSpecificOutput': {
            'hookEventName': 'PostToolUse',
            'additionalContext': message,
        }
    }))
    return 0


if __name__ == '__main__':
    sys.exit(main())
