#!/usr/bin/env python
"""link_check.py — invoked by post-checkout/post-merge/post-rewrite shell hooks.

Verifies inode parity between $AI_TOOLING_SRC/git-hooks/* and the consumer's
.git-hooks/* (per LINK_MAPPINGS in setup/link.py). WARN-only on divergence;
never blocks git. Always exits 0.
"""

import os
import sys

# Ensure $AI_TOOLING_SRC is on sys.path so `import setup.link` resolves.
# Mirror the pattern from entry_points/cli.py:22-25.
_AI_TOOLING_SRC = os.environ.get('AI_TOOLING_SRC') or os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _AI_TOOLING_SRC not in sys.path:
    sys.path.insert(0, _AI_TOOLING_SRC)

from setup.link import check as cmd_link_check


def main():
    project_root = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    cmd_link_check(project_root)
    return 0


if __name__ == '__main__':
    sys.exit(main())
