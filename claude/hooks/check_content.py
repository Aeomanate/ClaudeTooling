#!/usr/bin/env python
"""PostToolUse hook: runs every skill-tree content check against the newly
inserted text of one Edit/Write and emits one combined warning.

Flag-only: never edits, never blocks. WF-23 WARNING-SWEEP is the pass that
resolves what this raises - fix the text, or judge it correct as written.

Scoped to new content only: `tool_input.new_string` for Edit,
`tool_input.content` for Write. Pre-existing, untouched lines are never
re-flagged.

Reads PostToolUse event JSON from stdin per the hook contract.
"""
import json
import sys

try:
    from . import _checks
except ImportError:
    import _checks

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')


def _extract(event):
    tool_name = event.get('tool_name')
    tool_input = event.get('tool_input') or {}
    file_path = tool_input.get('file_path')
    if tool_name == 'Edit':
        text = tool_input.get('new_string', '')
    elif tool_name == 'Write':
        text = tool_input.get('content', '')
    else:
        text = None
    return tool_name, file_path, text


def run_checks(tool_name, file_path, text):
    findings = []
    for check in _checks.CONTENT_ONLY_CHECKS:
        findings.extend(check(file_path, text))
    for check in _checks.TOOL_AWARE_CHECKS:
        findings.extend(check(file_path, text, tool_name))
    return findings


def main():
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0

    tool_name, file_path, text = _extract(event)
    if text is None or not file_path:
        return 0

    findings = run_checks(tool_name, file_path, text)
    if not findings:
        return 0

    message = f'[check_content] {file_path}:\n' + '\n'.join(f'  - {f}' for f in findings)
    print(json.dumps({
        'hookSpecificOutput': {
            'hookEventName': 'PostToolUse',
            'additionalContext': message,
        }
    }))
    return 0


if __name__ == '__main__':
    sys.exit(main())
