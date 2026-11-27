#!/usr/bin/env python
"""PreToolUse hook - restates the current orchestrator mode, rarely.

Replaces the old `gate.sh`, which fired on every `UserPromptSubmit` and
repeated the same instruction on every turn regardless of mode. This one
fires only where the mode changes what the next action should be: a role
dispatch, and a git commit or push. Every other tool call, including an
investigation dispatch and every non-git shell command, passes silently.

Emits the one-line reminder, not the full contract: session_start.py and
resume_after_compact.py already state the contract in full, and this hook
fires while the developer is mid-task.

`PreToolUse` stdout is not injected into the model's context, so the text
goes out as `hookSpecificOutput.additionalContext` JSON instead.
"""
import json
import os
import re
import sys

try:
    from . import _mode
except ImportError:
    import _mode

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

_SPAWN_TOOLS = ('Agent', 'Task')
_SHELL_TOOLS = ('Bash', 'PowerShell')

# Role agents do the work; Explore and general-purpose only investigate, and
# investigation is normal in either mode.
_ROLE_AGENT_RE = re.compile(r'^orchestrator-(persistent|agent)-')

_GIT_WRITE_RE = re.compile(r'\bgit\s+(commit|push)\b')


def should_fire(event):
    tool = event.get('tool_name') or ''
    tool_input = event.get('tool_input') or {}

    if tool in _SPAWN_TOOLS:
        return bool(_ROLE_AGENT_RE.match(tool_input.get('subagent_type') or ''))

    if tool in _SHELL_TOOLS:
        return bool(_GIT_WRITE_RE.search(tool_input.get('command') or ''))

    return False


def main():
    if os.getenv('AI_TOOLING_ENABLED') == 'false':
        return 0

    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0

    # Sub-agents run their own rule stack; this gate is the orchestrator's.
    if event.get('agent_id'):
        return 0

    if not should_fire(event):
        return 0

    json.dump({
        'hookSpecificOutput': {
            'hookEventName': 'PreToolUse',
            'additionalContext': _mode.reminder(),
        }
    }, sys.stdout)
    return 0


if __name__ == '__main__':
    sys.exit(main())
