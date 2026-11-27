#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""`mr script leak_check` — verifies no test-run leaks into production state.

Run after every test suite execution. Checks, against the ai_tooling
project's own `.ai/` regardless of the invoking cwd:
  1. hook.log must not exist (sentinel — writes moved to tooling.log)
  2. TESTS.log must not exist under .ai/ (tests log to a temp dir instead)
  3. BRANCH_PLAN.md must not be corrupted (hash or backup-diff check;
     restored from `.ai/BRANCH_PLAN_COPY.md` and reported as a leak if so)
  4. `.ai/cache/` layout matches the AGT-14 canonical layout, for both the
     ai_tooling repo and the invoking repo's cwd when they differ
  5. Wall time — only checked when `mr verify` set TEST_WALL_TIME_SECONDS;
     a run this slow usually means a test is hitting the real network or a
     real subprocess that should be mocked. Silently skipped when the env
     var is absent (e.g. `mr script leak_check` run standalone).

Exit code: 0 = clean, 1 = leak detected.
"""

import filecmp
import hashlib
import os
import subprocess
from pathlib import Path

HELP = """\
mr script leak_check

Checks that the test suite left no trace in production state: no
hook.log, no TESTS.log under .ai/, BRANCH_PLAN.md not corrupted, the
.ai/cache/ layout still canonical, and (only inside `mr verify`) the
suite didn't take suspiciously long.

Example:
  mr script leak_check

Run this after any test suite execution, not just via `mr verify` - it
works standalone too, just without the wall-time check (that one needs
`mr verify` to have measured a real run first).

Exit code: 0 if clean, 1 if any check finds a leak.
"""


def _ai_tooling_root() -> Path:
    """Resolves the ai_tooling repo root: $AI_TOOLING_SRC, else this module's git root."""
    env_root = os.environ.get('AI_TOOLING_SRC')
    if env_root:
        return Path(env_root)
    script_dir = Path(__file__).resolve().parent
    result = subprocess.run(
        ['git', '-C', str(script_dir), 'rev-parse', '--show-toplevel'],
        capture_output=True, text=True,
    )
    return Path(result.stdout.strip())


def _git_toplevel() -> Path:
    """Returns the git root for the current working directory, or None."""
    result = subprocess.run(
        ['git', 'rev-parse', '--show-toplevel'],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return Path(result.stdout.strip())


def _git_tracked(root: Path, relpath: str) -> bool:
    """Returns True if relpath is a tracked file in the root repo."""
    result = subprocess.run(
        ['git', '-C', str(root), 'ls-files', '--error-unmatch', relpath],
        capture_output=True, text=True,
    )
    return result.returncode == 0


def _check_hook_log(ai_dir: Path) -> bool:
    """Check 1: hook.log must not exist. Returns True if a leak was found."""
    hook_log = ai_dir / 'hook.log'
    if not hook_log.is_file():
        print('CLEAN: no hook.log')
        return False
    lines = hook_log.read_text(encoding='utf-8', errors='replace').splitlines()
    print(f'LEAK: hook.log exists ({len(lines)} lines)')
    for line in lines[:5]:
        print(line)
    return True


def _check_tests_log(ai_dir: Path) -> bool:
    """Check 2: no TESTS.log under .ai/. Returns True if a leak was found."""
    tests_log = ai_dir / 'TESTS.log'
    if not tests_log.is_file():
        print('CLEAN: no TESTS.log under .ai/')
        return False
    lines = tests_log.read_text(encoding='utf-8', errors='replace').splitlines()
    print(f'LEAK: {tests_log} exists ({len(lines)} lines) — the log redirect did not apply')
    for line in lines[:3]:
        print(line)
    return True


def _check_plan_integrity(ai_dir: Path, ai_tooling_root: Path) -> bool:
    """Check 3: BRANCH_PLAN.md must not be corrupted. Returns True if a leak was found."""
    plan_file = ai_dir / 'BRANCH_PLAN.md'
    plan_copy = ai_dir / 'BRANCH_PLAN_COPY.md'
    plan_hash_before = os.environ.get('PLAN_HASH_BEFORE')

    if not plan_file.is_file():
        if plan_copy.is_file() or plan_hash_before:
            print('LEAK: BRANCH_PLAN.md DELETED during the gate window')
            print('  Pre-test baseline existed but file is gone')
            if plan_copy.is_file():
                _restore(plan_copy, plan_file)
                print('  RESTORED from BRANCH_PLAN_COPY.md backup')
            return True
        print('CLEAN: no BRANCH_PLAN.md to check (no prior baseline)')
        return False

    current_size = plan_file.stat().st_size

    if plan_hash_before:
        plan_hash_after = hashlib.md5(plan_file.read_bytes()).hexdigest()
        if plan_hash_before == plan_hash_after:
            print(f'CLEAN: BRANCH_PLAN.md intact (hash unchanged, {current_size} bytes)')
            return False
        print(f'LEAK: BRANCH_PLAN.md corrupted by tests (hash changed; size={current_size} bytes)')
        print(f'  Before: {plan_hash_before}')
        print(f'  After:  {plan_hash_after}')
        print('  FIX: patch PLAN_FILE to a temp path in the leaking test')
        if plan_copy.is_file():
            _restore(plan_copy, plan_file)
            print('  RESTORED: BRANCH_PLAN.md restored from backup')
        return True

    if plan_copy.is_file():
        if filecmp.cmp(plan_file, plan_copy, shallow=False):
            print(f'CLEAN: BRANCH_PLAN.md intact (matches backup, {current_size} bytes)')
            return False
        print(f'LEAK: BRANCH_PLAN.md corrupted (differs from backup; size={current_size} bytes)')
        _restore(plan_copy, plan_file)
        print('  RESTORED: BRANCH_PLAN.md restored from backup')
        return True

    # Fallback: no hash baseline and no backup — apply creation-leak heuristics.
    # Untracked carries no signal on its own (.ai/ is gitignored, so a
    # legitimate plan is always untracked) — content is the only evidence.
    is_untracked = 0 if _git_tracked(ai_tooling_root, '.ai/BRANCH_PLAN.md') else 1
    text = plan_file.read_text(encoding='utf-8', errors='replace')
    is_fixture = current_size < 200 and any(
        line.startswith('# Local Plan') or line.startswith('# Remote Plan')
        for line in text.splitlines()
    )
    if not is_fixture:
        print(f'CLEAN: BRANCH_PLAN.md present '
              f'({current_size} bytes; use mr verify for in-flight size check)')
        return False

    print(f'WARN: BRANCH_PLAN.md looks like a test-fixture artifact '
          f'(untracked={is_untracked}, fixture-content=1; {current_size} bytes)')
    if os.environ.get('LEAK_CHECK_AUTO_DELETE_FIXTURE', '0') == '1':
        plan_file.unlink()
        print('  DELETED: artifact removed (LEAK_CHECK_AUTO_DELETE_FIXTURE=1 in effect)')
        return True
    print('  KEPT: refusing to delete without LEAK_CHECK_AUTO_DELETE_FIXTURE=1; inspect manually')
    return False


def _restore(plan_copy: Path, plan_file: Path) -> None:
    """Restores plan_file from its backup copy."""
    plan_file.write_bytes(plan_copy.read_bytes())


def _default_branch(repo_root: Path) -> str:
    """Returns the repo's default branch name, or 'master' if undetermined."""
    result = subprocess.run(
        ['git', '-C', str(repo_root), 'symbolic-ref', '--short', 'refs/remotes/origin/HEAD'],
        capture_output=True, text=True,
    )
    ref = result.stdout.strip()
    ref = ref.removeprefix('origin/')
    return ref or 'master'


def _sanitized_branch_set(repo_root: Path) -> set:
    """Returns local branch names sanitized as: lowercased, '/' -> '_', '-' removed."""
    result = subprocess.run(
        ['git', '-C', str(repo_root), 'branch', '--list'],
        capture_output=True, text=True,
    )
    names = set()
    for line in result.stdout.splitlines():
        name = line.lstrip('* ').strip()
        if not name:
            continue
        names.add(name.lower().replace('/', '_').replace('-', ''))
    return names


# Files legitimately written directly under .ai/cache/{branch}/ by the
# plan-cache and compaction-resume features (git_hooks_impl/plan/cache.py
# _save_cache/_conflict_path; claude/hooks/precompact.py) - not agent
# output, so AGT-14's agents/recycle/ layout doesn't cover them.
_ALLOWED_BRANCH_CACHE_FILES = frozenset({
    'cached_BRANCH_PLAN.md',
    'base_PLAN.md',
    'local_PLAN.md',
    'remote_PLAN.md',
    'merged_PLAN.md',
    'session_state.md',
})
_ALLOWED_BRANCH_CACHE_DIRS = ('agents', 'recycle', 'gen_cache')


def _check_cache_layout(cache_dir: Path, repo_root: Path, label: str) -> bool:
    """Check 4 (AGT-14): validates .ai/cache/ layout. Returns True if a leak was found."""
    if not cache_dir.is_dir():
        print(f'CLEAN: {label} — no .ai/cache/ directory')
        return False

    default_branch = _default_branch(repo_root)
    branch_set = _sanitized_branch_set(repo_root)
    found_leak = False

    for entry in sorted(cache_dir.iterdir()):
        if not entry.is_dir():
            print(f'LEAK: {label} — loose file at .ai/cache/ — {entry.name}')
            found_leak = True
            continue

        name = entry.name
        if name == default_branch:
            print(f'LEAK: {label} — default-branch cache forbidden — .ai/cache/{name}/')
            found_leak = True
        elif name not in branch_set:
            print(f'LEAK: {label} — cache for non-existent branch — .ai/cache/{name}/')
            found_leak = True

        for sub in sorted(entry.iterdir()):
            if not sub.is_dir():
                if sub.name in _ALLOWED_BRANCH_CACHE_FILES:
                    continue
                print(f'LEAK: {label} — loose file under branch cache — '
                      f'.ai/cache/{name}/{sub.name}')
                found_leak = True
            elif sub.name not in _ALLOWED_BRANCH_CACHE_DIRS:
                print(f'LEAK: {label} — non-canonical top-level dir under '
                      f'.ai/cache/{name}/ — {sub.name}/')
                found_leak = True

        found_leak |= _check_agent_slots(entry / 'agents', name, label)

    if not found_leak:
        print(f'CLEAN: {label} — .ai/cache/ layout is canonical')
    return found_leak


def _check_agent_slots(agents_dir: Path, branch_name: str, label: str) -> bool:
    """Flags nested agent folders one level under each agent slot. Returns True if found."""
    if not agents_dir.is_dir():
        return False
    found_leak = False
    for slot in sorted(agents_dir.iterdir()):
        if not slot.is_dir():
            continue
        for inner in sorted(slot.iterdir()):
            if not inner.is_dir():
                continue
            is_nested = (
                inner.name.startswith('ass-')
                or (inner / 'output.md').is_file()
                or (inner / 'state.md').is_file()
            )
            if is_nested:
                print(f'LEAK: {label} — nested agent folder — '
                      f'.ai/cache/{branch_name}/agents/{slot.name}/{inner.name}/ '
                      f'(should be sibling under agents/)')
                found_leak = True
    return found_leak


_MAX_WALL_TIME_SECONDS_DEFAULT = 180


def _check_wall_time() -> bool:
    """Check 5: flags a suite run slower than the threshold. Returns True if a leak was found.

    Silently CLEAN (not a leak, no print) when TEST_WALL_TIME_SECONDS is
    absent - this check only applies when `mr verify` measured a real run.
    """
    raw_seconds = os.environ.get('TEST_WALL_TIME_SECONDS')
    if raw_seconds is None:
        return False
    try:
        seconds = float(raw_seconds)
    except ValueError:
        return False

    max_seconds = float(os.environ.get(
        'TEST_WALL_TIME_MAX_SECONDS', _MAX_WALL_TIME_SECONDS_DEFAULT
    ))
    if seconds > max_seconds:
        print(f'LEAK: test suite took {seconds:.1f}s (threshold: {max_seconds:.0f}s)')
        print('  Likely cause: a test hitting a real network call or subprocess')
        print('  that should be mocked. Run `mr script test_timings` to find it.')
        return True

    print(f'CLEAN: test suite took {seconds:.1f}s (threshold: {max_seconds:.0f}s)')
    return False


def run(argv: list) -> int:
    """Runs all leak checks against the ai_tooling project's own .ai/. See module docstring."""
    if argv and argv[0] in ('--help', '-h'):
        print(HELP)
        return 0

    ai_tooling_root = _ai_tooling_root()
    ai_dir = ai_tooling_root / '.ai'

    failed = False
    failed |= _check_hook_log(ai_dir)
    failed |= _check_tests_log(ai_dir)
    failed |= _check_plan_integrity(ai_dir, ai_tooling_root)
    failed |= _check_cache_layout(ai_dir / 'cache', ai_tooling_root, 'ai_tooling')
    failed |= _check_wall_time()

    cwd_root = _git_toplevel()
    if cwd_root is not None and cwd_root != ai_tooling_root:
        failed |= _check_cache_layout(
            cwd_root / '.ai' / 'cache', cwd_root, f'cwd({cwd_root.name})')

    return 1 if failed else 0
