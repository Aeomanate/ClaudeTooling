#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""`mr script dump_code_quality_reference` — dumps refactorer reference.

Prints code smells and the pattern index to stdout. Used by the
orchestrator before launching coder agents.
"""

import glob
import os
import sys

from git_hooks_impl.entry_points.commands._shared import ai_tooling_root

HELP = """\
mr script dump_code_quality_reference

Prints the full refactorer reference: the R1-R14 rules file path, the
pattern-index path, every code smell's full text, and the pattern index
itself.

Example:
  mr script dump_code_quality_reference

Run this before writing code, so the R1-R14 rules and smell catalog are
in context without a separate file read per smell.

Exit code: always 0.
"""


def run(argv: list) -> int:
    """Prints R1-R14 loading instructions, code smells, and the pattern index."""
    if argv and argv[0] in ('--help', '-h'):
        print(HELP)
        return 0

    # Smell/pattern .md files may contain non-ASCII characters (e.g. arrows);
    # the default Windows console codepage can't encode them.
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    root = ai_tooling_root()
    refactorer_dir = os.path.join(root, 'claude', 'skills', 'orchestrator', 'roles', 'refactorer')

    print('# =============================================')
    print('# CODE QUALITY REFERENCE — MANDATORY FOR CODING')
    print('# =============================================')
    print()
    print('# RUNTIME LOADING INSTRUCTIONS:')
    print('# 1. Read R1-R14 rules BEFORE writing code:')
    print(f"#      {os.path.join(refactorer_dir, 'rules.md')}")
    print('# 2. For a pattern or refactoring trigger, read the one-line index:')
    print(f"#      {os.path.join(refactorer_dir, 'patterns', 'ai_index.md')}")
    print()

    print('# --- CODE SMELLS ---')
    print()
    smell_files = sorted(glob.glob(os.path.join(refactorer_dir, 'smells', '*.md')))
    for smell_file in smell_files:
        print(f'## {os.path.splitext(os.path.basename(smell_file))[0]}')
        print()
        with open(smell_file, encoding='utf-8') as f:
            print(f.read())
        print()

    print('# --- PATTERN INDEX (decision trees + catalog) ---')
    print()
    with open(os.path.join(refactorer_dir, 'patterns', 'ai_index.md'), encoding='utf-8') as f:
        print(f.read())
    return 0
