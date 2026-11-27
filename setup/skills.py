#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""User-global Claude config setup - symlink agents/skills/hooks into ~/.claude/.

Prompts for confirmation, then symlinks (via os.symlink - never hard-link)
${AI_TOOLING_SRC}/claude/{agents,skills,hooks} into ~/.claude/.
Invoked by `mr setup`.
"""

import os
import shutil
import sys

_AI_TOOLING_SRC = os.environ.get('AI_TOOLING_SRC') or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
if _AI_TOOLING_SRC not in sys.path:
    sys.path.insert(0, _AI_TOOLING_SRC)

import json as _json

from git_hooks_impl.utils import prompt_yn
from setup._link_helpers import (
    PruneStatError,
    _link_directory_recursive,
    _link_flat_directory,
    _prune_flat_directory,
    _prune_managed_skill_orphan_files,
    _prune_recursive_directory,
)


def _print_preflight_warning(ai_tooling_src: str, user_claude: str) -> None:
    print('+----------------------------------------------------------------+')
    print('|  AI tooling - Claude config setup                              |')
    print('+----------------------------------------------------------------+')
    print('|                                                                |')
    print('|  This will MODIFY your USER-GLOBAL Claude config:             |')
    print('|                                                                |')
    print(f'|    Symlink  {ai_tooling_src}/claude/agents/*')
    print(f'|       into  {user_claude}/agents/')
    print('|                                                                |')
    print(f'|    Symlink  {ai_tooling_src}/claude/skills/orchestrator/')
    print(f'|       into  {user_claude}/skills/orchestrator/')
    print('|                                                                |')
    print('|  hooks/ is NOT symlinked - settings.json runs hook commands   |')
    print('|  straight from $AI_TOOLING_SRC/claude/hooks/*, so there is no |')
    print('|  deployed copy to diverge from source.                         |')
    print('|                                                                |')
    print("|  Existing files at the target will be REPLACED if they're     |")
    print('|  not already symlinked to the source.                          |')
    print('|                                                                |')
    print('|  After symlinking, you (or the LLM session running setup)     |')
    print('|  must MANUALLY MERGE the settings template into your existing  |')
    print('|  config. Recommended manual backup first:                      |')
    print(f'|    cp {user_claude}/settings.json \\')
    print(f'|       {user_claude}/settings.json.bak')
    print('|                                                                |')
    print('|  Then merge:                                                   |')
    print(f'|    Template:  {ai_tooling_src}/claude/settings.json')
    print(f'|    Target:    {user_claude}/settings.json')
    print('|  Per Components §8 instruction (printed after this dialog).   |')
    print('|                                                                |')
    print('|  Continue with symlink step? [y/N]                            |')
    print('+----------------------------------------------------------------+')


def _print_merge_instruction(ai_tooling_src: str, user_claude: str) -> None:
    print()
    print(f'Now manually merge {ai_tooling_src}/claude/settings.json (template) into')
    print(f'{user_claude}/settings.json (your existing config):')
    print()
    print('1. (Recommended) Back up first:')
    print(f'     cp {user_claude}/settings.json {user_claude}/settings.json.bak')
    print()
    print('2. For every key in the template:')
    print('   - Same value in target: no change.')
    print('   - Different value in target: ai_tooling-managed keys win on re-merge;')
    print('     other keys -> prompt user.')
    print('   - Missing in target: add it.')
    print()
    print('ai_tooling-managed keys:')
    print('  - hooks.PreToolUse, matchers Agent|Task and Bash|PowerShell (gate.py)')
    print('  - hooks.SessionStart, matcher startup|resume|clear  (session_start.py)')
    print('  - hooks.PreCompact                     (precompact.py)')
    print('  - hooks.SessionStart, matcher compact   (resume_after_compact.py)')
    print('  - hooks.PostToolUse, matcher Edit|Write (check_em_dash.py,')
    print('    check_line_citations.py, check_content.py)')
    print('  - permissions.allow       (entries marked _ai_tooling: true)')
    print("  - statusLine              (only if you don't already have one)")


def _link_claude_tree(claude_src: str, user_claude: str) -> None:
    """Symlink agents/ and skills/ from claude_src into user_claude.

    hooks/ is never linked - settings.json's hook commands run
    `$AI_TOOLING_SRC/claude/hooks/<name>.py` directly, so the deployed
    tree never holds a hook copy to diverge from source.

    Only adds or replaces diverged symlinks. Never deletes - stale artifact
    removal is handled separately by _prune_stale_targets().
    """
    # agents/ - flat (no subdirectories in source)
    source_agents = os.path.join(claude_src, 'agents')
    target_agents = os.path.join(user_claude, 'agents')
    if os.path.isdir(source_agents):
        linked, up_to_date = _link_flat_directory(source_agents, target_agents)
        if linked:
            print(f'  agents: {linked} file(s) linked')
        else:
            print(f'  agents: up to date ({up_to_date} file(s))')

    # skills/ - recursive walk
    source_skills = os.path.join(claude_src, 'skills')
    target_skills = os.path.join(user_claude, 'skills')
    if os.path.isdir(source_skills):
        linked, up_to_date = _link_directory_recursive(source_skills, target_skills)
        if linked:
            print(f'  skills: {linked} file(s) linked')
        else:
            print(f'  skills: up to date ({up_to_date} file(s))')


def _prune_stale_targets(claude_src: str, user_claude: str) -> tuple:
    """Enumerate stale ai_tooling artifacts in user_claude across two zones.

    - agents/: file-level prune, prefix + inode guard (orchestrator- prefix)
    - skills/: directory-level prune, path-existence + user-file block guard

    hooks/ is not a zone here - it is never linked into user_claude, so
    there is nothing there to go stale.

    Returns (files_to_delete, dirs_to_delete), each a list of
    (path, reason) tuples - does NOT delete anything.
    """
    files_to_delete = []
    dirs_to_delete = []

    source_agents = os.path.join(claude_src, 'agents')
    target_agents = os.path.join(user_claude, 'agents')
    files_to_delete.extend(
        (path, 'orchestrator-prefixed file in agents/, no live source inode match')
        for path in _prune_flat_directory(source_agents, target_agents, 'orchestrator-')
    )

    source_skills = os.path.join(claude_src, 'skills')
    target_skills = os.path.join(user_claude, 'skills')
    # File-level orphans inside ai_tooling-managed skill namespaces (Bug B fix
    # - catches files in source-present subdirs that the recursive walk skips).
    files_to_delete.extend(
        (path, 'orphan file inside managed skill namespace, no source counterpart')
        for path in _prune_managed_skill_orphan_files(source_skills, target_skills)
    )
    # Subtree-level orphans (Bug C fix lives inside _prune_recursive_directory
    # - managed-namespace subtrees skip the user-file guard).
    dirs_to_delete.extend(
        (path, 'orphan subdirectory, no source counterpart')
        for path in _prune_recursive_directory(source_skills, target_skills)
    )

    return files_to_delete, dirs_to_delete


def _update_claude_settings_env(key: str, value: str) -> None:
    """Write key=value into the env block of ~/.claude/settings.json.

    Creates the file or the env key if absent. Idempotent.
    """
    settings_path = os.path.join(os.path.expanduser('~'), '.claude', 'settings.json')
    if os.path.isfile(settings_path):
        with open(settings_path, encoding='utf-8') as f:
            settings = _json.load(f)
    else:
        settings = {}
    env = settings.setdefault('env', {})
    if env.get(key) == value:
        return  # already set, no write needed
    env[key] = value
    with open(settings_path, 'w', encoding='utf-8') as f:
        _json.dump(settings, f, indent=2, ensure_ascii=False)


def cmd_setup_user_global(ai_tooling_src: str = None, auto_yes: bool = False) -> int:
    """Print pre-flight warning, confirm, symlink Claude tree, print merge instruction.

    Returns 0 on success, 1 on abort or error.
    """
    if ai_tooling_src is None:
        ai_tooling_src = _AI_TOOLING_SRC
    user_claude = os.path.expanduser('~/.claude')
    claude_src = os.path.join(ai_tooling_src, 'claude')

    if not os.path.isdir(claude_src):
        print(f'ERROR: Claude source tree not found at {claude_src}', file=sys.stderr)
        print('  Is AI_TOOLING_SRC set correctly?', file=sys.stderr)
        return 1

    _print_preflight_warning(ai_tooling_src, user_claude)

    if not auto_yes and not prompt_yn('', default_yes=False):
        print('Aborted - no changes made.')
        return 1

    print()
    print('Linking Claude config files...')
    print()

    _link_claude_tree(claude_src, user_claude)

    # WF-12 gate: collect stale artifacts across all three zones, prompt once.
    try:
        files_to_delete, dirs_to_delete = _prune_stale_targets(claude_src, user_claude)
    except PruneStatError as error:
        print(f'WARNING: stale-artifact scan aborted - {error}', file=sys.stderr)
        print('  Skipping cleanup this run; re-run `mr setup` to retry.', file=sys.stderr)
        files_to_delete, dirs_to_delete = [], []
    if files_to_delete or dirs_to_delete:
        print()
        print('  Stale ai_tooling artifacts detected:')
        for path, reason in files_to_delete:
            print(f'    [file] {os.path.basename(path)}  [{path}]  - {reason}')
        for path, reason in dirs_to_delete:
            print(f'    [dir]  {os.path.relpath(path, user_claude)}  [{path}]  - {reason}')
        print()
        n_files = len(files_to_delete)
        n_dirs = len(dirs_to_delete)
        label = f'{n_files} stale file(s) + {n_dirs} stale director(ies)'
        if prompt_yn(f'Delete {label}?', default_yes=False):
            for path, _reason in files_to_delete:
                os.remove(path)
                print(f'  Deleted: {os.path.basename(path)}')
            for path, _reason in dirs_to_delete:
                shutil.rmtree(path)
                print(f'  Deleted dir: {os.path.relpath(path, user_claude)}')
        else:
            print('  Skipped - stale artifacts left in place.')

    print()
    _print_merge_instruction(ai_tooling_src, user_claude)

    # Write AI_TOOLING_SRC to ~/.claude/settings.json so Claude's tool-execution
    # context can resolve ${AI_TOOLING_SRC}/... paths referenced in skill files.
    # Complements the shell-profile export (install_profiles.py).
    _update_claude_settings_env('AI_TOOLING_SRC', ai_tooling_src.replace('\\', '/'))
    print('  Set AI_TOOLING_SRC in ~/.claude/settings.json')
    return 0


if __name__ == '__main__':
    src = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('AI_TOOLING_SRC', _AI_TOOLING_SRC)
    sys.exit(cmd_setup_user_global(src))
