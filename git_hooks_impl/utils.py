#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Shared constants, subprocess helpers, prompt helpers, and tool discovery.
"""

import asyncio
import os
import shutil
import subprocess
import sys
import time

from git_hooks_impl.logger import console_tag, dbg

# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------

TARGET_BRANCH    = 'master'
PLAN_FILE        = '.ai/BRANCH_PLAN.md'
# When set, hooks exit immediately — prevents re-entry during internal git ops
AI_TOOLING_HOOK_RECURSION_GUARD = 'AI_TOOLING_RECURSION_GUARD'

# ---------------------------------------------------------------------------
#  Subprocess helpers
# ---------------------------------------------------------------------------

def _cmd_display(cmd):
    """Format a command list for debug logging, truncating args over 80 chars."""
    parts = []
    for arg in cmd:
        if len(arg) > 80:
            parts.append(f'"{arg[:77]}..."')
        elif ' ' in arg or '\n' in arg:
            parts.append(f'"{arg}"')
        else:
            parts.append(arg)
    return ' '.join(parts)


def run(cmd, input_data=None):
    """Run a subprocess. Returns (exit_code, stdout, stderr).

    When input_data is provided it is piped via stdin, bypassing the
    Windows 32 767-char command-line limit for large payloads.
    """
    dbg(f'exec: {_cmd_display(cmd)}')
    t0 = time.time()
    result = subprocess.run(  # noqa: UP022  # capture_output incompatible with stdin parameter
        cmd,
        input=input_data if input_data is not None else None,
        stdin=None if input_data is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding='utf-8',
        errors='replace',
    )
    elapsed = time.time() - t0
    if result.returncode != 0:
        dbg(f'  -> exit_code={result.returncode} ({elapsed:.1f}s)')
        if result.stderr.strip():
            dbg(f'  -> stderr: {result.stderr.strip()}')
    else:
        dbg(f'  -> ok ({elapsed:.1f}s)')
    return result.returncode, result.stdout, result.stderr


async def run_async(cmd, input=None, timeout=None):
    """Async subprocess for glab/jira CLI calls. Returns (returncode, stdout, stderr).

    On CancelledError: kills child process, then re-raises — clean teardown on Ctrl+C.

    asyncio.create_subprocess_exec docs: "coroutine asyncio.create_subprocess_exec(program,
    *args, ...) — Create a subprocess. Return a Process instance."
    (docs.python.org/3/library/asyncio-subprocess.html)
    """
    dbg(f'exec (async): {_cmd_display(cmd)}')
    stdin_data = input.encode('utf-8') if input is not None else None
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE if stdin_data is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except asyncio.CancelledError:
        raise
    try:
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(input=stdin_data),
            timeout=timeout,
        )
    except asyncio.CancelledError:
        proc.kill()
        await proc.wait()
        raise
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return 1, '', 'timeout'
    stdout = stdout_b.decode('utf-8', errors='replace')
    stderr = stderr_b.decode('utf-8', errors='replace')
    if proc.returncode != 0:
        dbg(f'  -> exit_code={proc.returncode}')
        if stderr.strip():
            dbg(f'  -> stderr: {stderr.strip()}')
    else:
        dbg('  -> ok')
    return proc.returncode, stdout, stderr


def is_master_or_main(branch: str) -> bool:
    """Return True when branch is master or main."""
    return branch in ('master', 'main')


def run_interactive(cmd):
    """Run a subprocess with inherited stdin/stdout (for interactive commands)."""
    dbg(f'exec (interactive): {_cmd_display(cmd)}')
    return subprocess.run(cmd).returncode


# ---------------------------------------------------------------------------
#  Tool discovery
# ---------------------------------------------------------------------------

# Known install locations per tool, checked when shutil.which() fails.
# This handles stale terminal sessions where PATH hasn't been reloaded
# after a fresh tool install (e.g. pushed before re-sourcing ~/.bashrc).
_FALLBACK_DIRS = {
    'glab':  (
        [os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'glab')]
        if sys.platform == 'win32' else
        ['/usr/local/bin', os.path.expanduser('~/.linuxbrew/bin'), '/opt/homebrew/bin']
    ),
    'jira':  [os.path.expanduser('~/bin')],
    'claude': (
        [os.path.join(os.environ.get('APPDATA', ''), 'npm')]
        if sys.platform == 'win32' else
        [os.path.expanduser('~/.npm-global/bin'), '/usr/local/bin']
    ),
}


def find_tool(name):
    """Locate a tool binary. Checks PATH first, then known install locations.
    If found via fallback, adds its directory to the current session PATH
    so subsequent subprocess calls can reach it without a full env reload.
    Returns the binary path, or empty string if not found.
    """
    path = shutil.which(name)
    if path:
        return path

    for directory in _FALLBACK_DIRS.get(name, []):
        if not directory:
            continue
        exe = name + '.exe' if sys.platform == 'win32' else name
        candidate = os.path.join(directory, exe)
        if os.path.isfile(candidate):
            dbg(f'{name} not in PATH — found at {candidate}, adding to session PATH')
            ensure_path(directory)
            return candidate

    return ''


# ---------------------------------------------------------------------------
#  User prompts
# ---------------------------------------------------------------------------

def prompt_yn(question, default_yes=True):
    """Prompt user for yes/no. Returns True for yes, False for no."""
    suffix = '[Y/n]' if default_yes else '[y/N]'
    try:
        answer = input(f'{console_tag()} {question} {suffix} ').strip().lower()
    except (EOFError, KeyboardInterrupt):
        print(file=sys.stderr)
        return False
    if not answer:
        return default_yes
    return answer in ('y', 'yes')


def prompt_input(label, default=''):
    """Prompt user for a single value. Returns string or default on cancel."""
    suffix = f' [{default}]' if default else ''
    try:
        value = input(f'{console_tag()} {label}{suffix}: ').strip()
    except (EOFError, KeyboardInterrupt):
        print(file=sys.stderr)
        return default
    return value or default


# ---------------------------------------------------------------------------
#  Runtime path / env utilities
# ---------------------------------------------------------------------------

def ensure_path(directory: str) -> None:
    """Add a directory to PATH for the current session if not already there."""
    current = os.environ.get('PATH', '')
    if directory not in current.split(os.pathsep):
        os.environ['PATH'] = current + os.pathsep + directory
        dbg(f'Added to session PATH: {directory}')


def add_env_path(directory: str) -> None:
    """Add a directory to the current session PATH (deduped)."""
    ensure_path(directory)


def _to_posix_path(path: str) -> str:
    """Convert a Windows path to POSIX/Git Bash format.

    C:\\Kragle\\reponame -> /c/Kragle/reponame
    C:\\Kragle\\reponame -> /c/Kragle/reponame
    Passthrough on non-Windows or already-POSIX paths.
    """
    p = path.replace('\\', '/')
    if len(p) >= 2 and p[1] == ':' and p[0].isalpha():
        p = '/' + p[0].lower() + p[2:]
    return p

