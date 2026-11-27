#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Per-project linker — symlink 8 hook stubs into a consumer project.

Two modes:
  A. install(project_root): walk LINK_MAPPINGS, symlink via os.symlink(),
     prompt before replacing a diverged existing file, set core.hooksPath.
     Windows requires Developer Mode or Administrator; fails hard otherwise.
  B. check(project_root):   symlink check only, warn on divergence,
     never writes. Always exits 0 (never blocks git).

Same-drive only: cross-volume symlinking is not supported.
"""

import os
import sys

from git_hooks_impl.utils import prompt_yn, run
from setup._link_helpers import _is_linked, _link_unconditional

# ---------------------------------------------------------------------------
#  Source root
# ---------------------------------------------------------------------------

# Absolute path to $AI_TOOLING_SRC — two levels up from this file.
_AI_TOOLING_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
#  Link mappings — 8 hook stubs (source relative to _AI_TOOLING_SRC,
#  target relative to the consumer project root).
# ---------------------------------------------------------------------------

LINK_MAPPINGS = [
    ('git-hooks/pre-push',              '.git-hooks/pre-push'),
    ('git-hooks/post-checkout',         '.git-hooks/post-checkout'),
    ('git-hooks/post-commit',           '.git-hooks/post-commit'),
    ('git-hooks/post-merge',            '.git-hooks/post-merge'),
    ('git-hooks/post-rewrite',          '.git-hooks/post-rewrite'),
    ('git-hooks/reference-transaction', '.git-hooks/reference-transaction'),
    ('git-hooks/pre-commit',            '.git-hooks/pre-commit'),
    ('git-hooks/commit-msg',            '.git-hooks/commit-msg'),
]

# ---------------------------------------------------------------------------
#  git config helpers
# ---------------------------------------------------------------------------

def _git_config_get(key: str) -> str:
    """Return git local config value or empty string."""
    rc, stdout, _stderr = run(['git', 'config', '--local', key])
    return stdout.strip() if rc == 0 else ''


def _git_config_set(key: str, value: str) -> None:
    """Set a git local config value."""
    run(['git', 'config', '--local', key, value])


def _set_hooks_path(project_root: str) -> None:
    """Set core.hooksPath to .git-hooks, backing up previous value if set."""
    current = _git_config_get('core.hooksPath')
    if current.rstrip('/') == '.git-hooks':
        return
    if current:
        _git_config_set('ai-tooling.previousHooksPath', current)
        print(f'  Backed up core.hooksPath={current!r} → ai-tooling.previousHooksPath')
    _git_config_set('core.hooksPath', '.git-hooks')
    print('  Set core.hooksPath = .git-hooks')


# ---------------------------------------------------------------------------
#  .gitignore management
# ---------------------------------------------------------------------------

_GITIGNORE_COMMENT = '# ai-tooling: local runtime artifacts (BRANCH_PLAN.md, caches) — never commit'
_GITIGNORE_ENTRY = '.ai/'
_GITIGNORE_ACCEPTED_FORMS = ('.ai/', '.ai', '/.ai/', '/.ai')


def _ensure_gitignore_entry(project_root: str) -> None:
    """Append a `.ai/` ignore rule to the project's .gitignore, once.

    Creates .gitignore when it doesn't exist yet. Idempotent: does nothing
    if any line already covers `.ai/` (with or without a leading/trailing
    slash). Never duplicates the entry on a re-run.
    """
    gitignore_path = os.path.join(project_root, '.gitignore')

    existing_lines = []
    if os.path.isfile(gitignore_path):
        with open(gitignore_path, 'r', encoding='utf-8') as handle:
            existing_lines = handle.read().splitlines()

    for line in existing_lines:
        if line.strip() in _GITIGNORE_ACCEPTED_FORMS:
            return

    needs_leading_blank = bool(existing_lines) and existing_lines[-1].strip() != ''
    with open(gitignore_path, 'a', encoding='utf-8') as handle:
        if needs_leading_blank:
            handle.write('\n')
        handle.write(f'{_GITIGNORE_COMMENT}\n{_GITIGNORE_ENTRY}\n')
    print('  Added .ai/ to .gitignore (tooling-managed runtime cache).')


# ---------------------------------------------------------------------------
#  Mode A — install
# ---------------------------------------------------------------------------

def install(project_root: str) -> int:
    """Symlink 8 hook stubs into the consumer project.

    Returns 0 on success, 1 on error.
    Bails early when:
    - not inside a git repo
    - project_root matches _AI_TOOLING_SRC (don't link into self)
    - AI_TOOLING_ENABLED is not 'true' (kill switch)
    """
    if os.environ.get('AI_TOOLING_ENABLED', 'true') != 'true':
        print("AI_TOOLING_ENABLED is not 'true' — skipping link install.")
        return 0

    rc, toplevel, _err = run(['git', 'rev-parse', '--show-toplevel'])
    if rc != 0:
        print('ERROR: not inside a git repository.', file=sys.stderr)
        return 1
    toplevel = toplevel.strip()

    # Normalise for comparison.
    project_root = os.path.realpath(project_root)
    ai_tooling_real = os.path.realpath(_AI_TOOLING_SRC)

    if project_root == ai_tooling_real:
        print('ERROR: refusing to link into $AI_TOOLING_SRC itself.', file=sys.stderr)
        return 1

    linked_count = 0
    refreshed_count = 0
    skipped_count = 0

    os.makedirs(os.path.join(project_root, '.git-hooks'), exist_ok=True)

    # Pass 1: classify every mapping — new links are applied immediately;
    # diverged files are collected for a single batch prompt.
    diverged_pairs = []  # [(source_file, target_file, target_rel), ...]

    for src_rel, target_rel in LINK_MAPPINGS:
        source_file = os.path.join(ai_tooling_real, src_rel)
        target_file = os.path.join(project_root, target_rel)

        if not os.path.isfile(source_file):
            print(f'  WARNING: source not found: {src_rel} — skipping')
            continue

        os.makedirs(os.path.dirname(target_file), exist_ok=True)

        # Cross-volume guard.
        try:
            src_dev = os.stat(source_file).st_dev
            tgt_dev = (
                os.stat(target_file).st_dev
                if os.path.exists(target_file)
                else os.stat(os.path.dirname(target_file)).st_dev
            )
        except OSError as exc:
            print(f'  ERROR: stat failed for {target_rel}: {exc}', file=sys.stderr)
            return 1

        if src_dev != tgt_dev:
            print(
                f'  ERROR: {target_rel} — cross-volume linking not supported in MVP.',
                file=sys.stderr,
            )
            return 1

        if os.path.isfile(target_file) and not _is_linked(source_file, target_file):
            diverged_pairs.append((source_file, target_file, target_rel))
        elif not os.path.exists(target_file):
            os.symlink(source_file, target_file)
            print(f'  Linked: {target_rel}')
            linked_count += 1
        else:
            skipped_count += 1

    # Pass 2: batch prompt for all diverged files.
    if diverged_pairs:
        print('The following hooks have diverged from source:')
        for _, _, target_rel in diverged_pairs:
            print(f'  - {target_rel}')
        print()
        if prompt_yn(f'Refresh all {len(diverged_pairs)}?', default_yes=False):
            for source_file, target_file, target_rel in diverged_pairs:
                _link_unconditional(source_file, target_file)
                print(f'  Refreshed: {target_rel}')
                refreshed_count += 1
            print(f'Refreshed {refreshed_count} diverged hooks.')
        else:
            print('Skipped — no changes made.')
            skipped_count += len(diverged_pairs)
    elif linked_count == 0:
        print('All hooks are up to date.')

    _set_hooks_path(project_root)
    _ensure_gitignore_entry(project_root)

    print(
        f'Done — linked {linked_count}, refreshed {refreshed_count}, '
        f'skipped {skipped_count} up-to-date.'
    )
    return 0


# ---------------------------------------------------------------------------
#  Mode B — check-only (called from post-* hooks via link_check.py)
# ---------------------------------------------------------------------------

def check(project_root: str) -> int:
    """Compare hook stub inodes against source. Warn on divergence, never writes.

    Always returns 0 — must not block git operations.
    """
    project_root = os.path.realpath(project_root)
    ai_tooling_real = os.path.realpath(_AI_TOOLING_SRC)

    ok_count = 0
    diverged = []
    missing = []

    for src_rel, target_rel in LINK_MAPPINGS:
        source_file = os.path.join(ai_tooling_real, src_rel)
        target_file = os.path.join(project_root, target_rel)

        if not os.path.isfile(target_file):
            missing.append(target_rel)
        elif not _is_linked(source_file, target_file):
            diverged.append(target_rel)
        else:
            ok_count += 1

    hooks_path = _git_config_get('core.hooksPath')
    hooks_path_wrong = hooks_path.rstrip('/') != '.git-hooks'

    if diverged or missing or hooks_path_wrong:
        print('[ai-tooling] link-check warnings:')
        for p in missing:
            print(f'  MISSING: {p}')
        for p in diverged:
            print(f'  DIVERGED: {p}')
        if hooks_path_wrong:
            print(f'  HOOKS_PATH_WRONG: core.hooksPath={hooks_path!r}, expected .git-hooks')
        print(
            f"  {ok_count} links OK, {len(diverged)} diverged, {len(missing)} missing, "
            f"hooksPath {'wrong' if hooks_path_wrong else 'OK'}"
            " — run `mr setup` to repair."
        )
    return 0


# ---------------------------------------------------------------------------
#  CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'install'
    project_root = sys.argv[2] if len(sys.argv) > 2 else os.getcwd()
    if mode == 'install':
        sys.exit(install(project_root))
    elif mode == 'check':
        sys.exit(check(project_root))
    else:
        print(f'Unknown mode: {mode}', file=sys.stderr)
        sys.exit(2)
