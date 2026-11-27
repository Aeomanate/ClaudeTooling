#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""`mr script validate_agent_files` - validates orchestrator agent files.

Checks every `orchestrator-*.md` agent file for required frontmatter
(`kind: agent`, a current Claude 4.x `model:` declaration), exactly one
`# Dispatch info` section, the persistent-sub-agent-only fields
(`self_role_dir:`, a "MANDATORY pre-work" section), and the absence of the
forbidden `CLAUDE_SKILL_DIR` reference.
"""

import glob
import os

from claude.hooks import _checks
from git_hooks_impl.entry_points.commands._shared import project_root

HELP = """\
mr script validate_agent_files

Checks every claude/agents/orchestrator-*.md file for required frontmatter:
kind: agent, a current Claude 4.x model: declaration, exactly one
# Dispatch info section, and, for orchestrator-persistent-* agents only,
self_role_dir: and a MANDATORY pre-work section. Also flags the forbidden
CLAUDE_SKILL_DIR reference.

Example:
  mr script validate_agent_files

Exit code: 0 when every agent file passes, 1 when any file has an issue.
"""


def run(argv: list) -> int:
    """Prints incomplete agent files and a summary.

    Returns 0 when all agent files pass frontmatter + pre-work checks,
    1 when any are found with issues.
    """
    if argv and argv[0] in ('--help', '-h'):
        print(HELP)
        return 0

    root = project_root()
    agents_dir = os.path.join(root, 'claude', 'agents')

    print('### Check: Agent file frontmatter + mandatory pre-work')
    print()

    files = sorted(glob.glob(os.path.join(agents_dir, 'orchestrator-*.md')))
    issues = 0
    for f in files:
        short = os.path.basename(f)
        with open(f, encoding='utf-8') as fh:
            content = fh.read()

        # tool_name='Write' runs every presence check against the whole
        # file, same as check_content.py does for a fresh agent-file write.
        file_issues = _checks.check_agent_frontmatter(f, content, 'Write')

        if file_issues:
            print(f"  INCOMPLETE: {short} - {'; '.join(file_issues)}")
            issues += 1

    print()
    if issues == 0:
        print(f'  CLEAN: All {len(files)} agent files pass frontmatter + pre-work checks')
    else:
        print(f'  {issues} of {len(files)} agent files have issues')
    return 0 if issues == 0 else 1
