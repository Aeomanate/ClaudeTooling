#!/usr/bin/env python
"""The orchestrator's mandatory-read manifest, in one place.

`session_start.py` and `resume_after_compact.py` both emit this list and
used to carry their own copy, which drifts. The POC list is deliberately
short: the mode's own contract comes from the hook text, not from a file, so
the only things worth reading up front are the index and the style rules
that bind every reply regardless of mode.
"""
import os

SKILL_ROOT = os.environ.get(
    'CLAUDE_SKILL_DIR',
    os.path.expanduser('~/.claude/skills/orchestrator'),
)

MANDATORY_FILES = [
    'SKILL.md',
    'shared/rules/style.md',
    'shared/rules/agents.md',
    'shared/rules/workflow.md',
    'shared/rules/documentation.md',
    'rules/delegation.md',
    'rules/plan.md',
    'shared/common_resources.md',
]

POC_FILES = [
    'SKILL.md',
    'shared/rules/style.md',
]

PERSISTENT_ROLES = [
    'coder', 'drd-writer', 'evt-writer', 'featurer', 'fixer', 'gitter',
    'plan-writer', 'refactorer', 'skill-validation', 'tester',
]
