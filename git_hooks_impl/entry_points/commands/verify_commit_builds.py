#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""`mr script verify_commit_builds` — builds a commit standalone, restoring the branch after.

Builds <build_dir> with <config> using the project's own build command
(cmake --build <build_dir> --config <config>, run from the calling
project's root via project_root() — the same invocation shape
run_cpp_tests uses for its own build step). With no sha, builds the
current working tree in place. With a sha, checks out that commit
detached from the current branch, builds it, then unconditionally
restores the original branch afterward — including popping any stash
pushed to make the checkout safe — on every exit path, even a build
failure or an unexpected exception.

Usage:
    mr script verify_commit_builds <build_dir> <config>
    mr script verify_commit_builds <build_dir> <config> <sha>

Example:
  mr script verify_commit_builds build/x64 Debug
  mr script verify_commit_builds build/x64 Debug a1b2c3d

Exit code: the build's exit code (0 on PASS).
"""

import subprocess

from git_hooks_impl.entry_points.commands._shared import project_root

HELP = """\
mr script verify_commit_builds <build_dir> <config>
mr script verify_commit_builds <build_dir> <config> <sha>

Builds <build_dir> with <config> via cmake --build, from the calling
project's root. With no sha, builds the current working tree in place.
With a sha, checks out that commit standalone (detached HEAD), builds
it, then always restores the original branch afterward - even on a
build failure or an unexpected error - popping any stash pushed to make
the checkout safe.

Examples:
  mr script verify_commit_builds build/x64 Debug
  mr script verify_commit_builds build/x64 Debug a1b2c3d

Exit code: the build's exit code (0 on PASS).
"""


def _run_build(build_dir: str, config: str) -> int:
    """Runs cmake --build <build_dir> --config <config> from the project root."""
    result = subprocess.run(
        ['cmake', '--build', build_dir, '--config', config],
        cwd=project_root(),
    )
    return result.returncode


def _current_branch() -> str:
    """Returns the current branch name (or ref) via git rev-parse."""
    return subprocess.check_output(
        ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
        cwd=project_root(), text=True,
    ).strip()


def _working_tree_dirty() -> bool:
    """True if `git status --porcelain` reports any pending change."""
    status = subprocess.check_output(
        ['git', 'status', '--porcelain'],
        cwd=project_root(), text=True,
    )
    return bool(status.strip())


def _restore(original_branch: str, stashed: bool) -> None:
    """Returns to original_branch and pops the stash if one was pushed.

    Called from a finally block, so this must never leave the repo on a
    detached HEAD or a stranded stash regardless of what happened before it.
    """
    subprocess.run(['git', 'checkout', '--force', original_branch], cwd=project_root())
    if stashed:
        subprocess.run(['git', 'stash', 'pop'], cwd=project_root())


def _verify_at_sha(build_dir: str, config: str, sha: str) -> int:
    """Checks out sha detached, builds it, then always restores the original branch."""
    original_branch = _current_branch()
    stashed = False
    try:
        if _working_tree_dirty():
            subprocess.run(['git', 'stash', 'push'], cwd=project_root(), check=True)
            stashed = True
        subprocess.run(
            ['git', 'checkout', '--force', '--detach', sha],
            cwd=project_root(), check=True,
        )
        return _run_build(build_dir, config)
    finally:
        _restore(original_branch, stashed)


def run(argv: list) -> int:
    """Builds build_dir/config, optionally at a detached sha. See module docstring."""
    if argv and argv[0] in ('--help', '-h'):
        print(HELP)
        return 0

    if len(argv) < 2:
        print('Usage: mr script verify_commit_builds <build_dir> <config> [sha]')
        return 1

    build_dir, config = argv[0], argv[1]
    sha = argv[2] if len(argv) > 2 else None

    returncode = _run_build(build_dir, config) if sha is None else _verify_at_sha(build_dir, config, sha)

    status = 'PASS' if returncode == 0 else 'FAIL'
    target = f'sha {sha}' if sha else 'working tree'
    print(f'{status}: verify_commit_builds ({target}, build_dir={build_dir}, config={config})')
    return returncode
