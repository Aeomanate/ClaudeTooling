#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""`mr script run_coverage` - canonical coverage run for git_hooks_impl tests.

Runs branch coverage over `git_hooks_impl/tests`, prints a report with
missing lines, and writes a machine-readable `.ai/artifacts/coverage.json`.
Returns the first failing step's exit code, or 0 if all steps succeed.

Usage:
    mr script run_coverage                 # full repo, writes coverage.json
    mr script run_coverage --module <mod>  # scoped to <mod>.tests, no json
"""

import os
import subprocess

from git_hooks_impl.entry_points.commands._shared import project_root

HELP = """\
mr script run_coverage
mr script run_coverage --module <mod>

Runs branch coverage and prints a missing-lines report.

Examples:
  mr script run_coverage                          # full repo
  mr script run_coverage --module git_hooks_impl  # one module only

No arguments: covers all of git_hooks_impl/tests and writes
.ai/artifacts/coverage.json.

--module <mod>: covers only <mod>.tests, with no json file. Use this
during mock-audit or test-writing instead of paying for the full-repo run.

Exit code: the first failing step's exit code, or 0 if everything passes.
"""


def run(argv: list) -> int:
    """Runs coverage run/report[/json] in sequence. Returns 0 on success."""
    if argv and argv[0] in ('--help', '-h'):
        print(HELP)
        return 0

    root = project_root()

    if argv and argv[0] == '--module':
        if len(argv) < 2:
            print('Usage: mr script run_coverage --module <mod>')
            return 1
        module = argv[1]
        print(f'=== Step 1/2: coverage run (branch coverage on {module}.tests) ===')
        result = subprocess.run(
            ['coverage', 'run', '--branch', '-m', 'unittest', f'{module}.tests'],
            cwd=root,
        )
        if result.returncode != 0:
            return result.returncode

        print()
        print('=== Step 2/2: coverage report (with missing lines) ===')
        return subprocess.run(['coverage', 'report', '--show-missing'], cwd=root).returncode

    artifacts_dir = os.path.join(root, '.ai', 'artifacts')
    os.makedirs(artifacts_dir, exist_ok=True)
    json_out = os.path.join(artifacts_dir, 'coverage.json')

    print('=== Step 1/3: coverage run (branch coverage on git_hooks_impl/tests) ===')
    result = subprocess.run(
        ['coverage', 'run', '--branch', '-m', 'unittest', 'discover', 'git_hooks_impl/tests'],
        cwd=root,
    )
    if result.returncode != 0:
        return result.returncode

    print()
    print('=== Step 2/3: coverage report (with missing lines) ===')
    result = subprocess.run(['coverage', 'report', '--show-missing'], cwd=root)
    if result.returncode != 0:
        return result.returncode

    print()
    print(f'=== Step 3/3: coverage json -> {json_out} ===')
    result = subprocess.run(['coverage', 'json', '-o', json_out], cwd=root)
    if result.returncode != 0:
        return result.returncode

    print()
    print(f'CLEAN: coverage data written to {json_out}')
    return 0
