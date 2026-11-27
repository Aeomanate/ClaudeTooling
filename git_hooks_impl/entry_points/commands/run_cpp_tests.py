#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""`mr script run_cpp_tests` — builds and runs C++ tests for a target."""

import subprocess

from git_hooks_impl.entry_points.commands._shared import project_root

HELP = """\
mr script run_cpp_tests <target> <pattern>

Builds <target> with cmake, then runs ctest filtered to <pattern>.

Example:
  mr script run_cpp_tests MyLibTests "MyClass.*"

Never runs the full test suite - always pass a pattern scoped to the
module you changed.

Exit code: the cmake build's exit code if the build fails, otherwise
ctest's exit code.
"""


def run(argv: list) -> int:
    """Builds argv[0] target then runs ctest filtered by argv[1] pattern."""
    if argv and argv[0] in ('--help', '-h'):
        print(HELP)
        return 0

    if len(argv) < 2:
        print('Usage: mr script run_cpp_tests <target> <pattern>')
        return 1
    target, pattern = argv[0], argv[1]
    root = project_root()
    build_result = subprocess.run(
        ['cmake', '--build', 'build/x64', '--config', 'Debug', '--target', target],
        cwd=root,
    )
    if build_result.returncode != 0:
        return build_result.returncode
    test_result = subprocess.run(
        ['ctest', '--preset', 'windows-x64-debug', '-R', pattern, '--verbose'],
        cwd=root,
    )
    return test_result.returncode
