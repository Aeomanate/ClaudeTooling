#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Shared helpers for `mr script <name>` command implementations."""

import os
import subprocess


def project_root() -> str:
    """Returns the git repository root for the current working directory.

    Use this for anything scoped to the CALLING repo - the project the
    developer is actually working in. Use ai_tooling_root() instead for
    anything that reads the orchestrator skill tree itself (it lives in
    ai_tooling's own repo, not the calling repo, when run from a consumer
    project like reponame).
    project like reponame).
    """
    return subprocess.check_output(
        ['git', 'rev-parse', '--show-toplevel'],
        stderr=subprocess.DEVNULL, text=True,
    ).strip()


def ai_tooling_root() -> str:
    """Resolves the ai_tooling repo root: $AI_TOOLING_SRC, else this module's git root.

    Never the calling repo's cwd - a command whose data lives inside
    ai_tooling's own tree (claude/skills/orchestrator/, git_hooks_impl/)
    must resolve it this way, not via project_root(), or it silently
    breaks when run from a consumer repo.
    """
    env_root = os.environ.get('AI_TOOLING_SRC')
    if env_root:
        return env_root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return subprocess.check_output(
        ['git', '-C', script_dir, 'rev-parse', '--show-toplevel'],
        stderr=subprocess.DEVNULL, text=True,
    ).strip()


def run_capture(cmd: list) -> tuple:
    """Runs cmd, capturing output. Returns (returncode, stdout, stderr)."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr
