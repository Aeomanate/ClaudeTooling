#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""cli.py - unified mr CLI + git hook dispatcher.

mr CLI (invoked by `mr` Bash shim):
  exec python "${AI_TOOLING_SRC}/git_hooks_impl/entry_points/cli.py" "$@"
  Subcommands: sync [--force], planget, plangen [--force], status, setup, new,
  on, off, help.

Hook dispatcher (invoked by ai_tooling_hooks.py via the same main()):
  Subcommands: sync-mr, extract-plan, get-plan, cache-swap, cache-save, cache-prune, status.
  Recursion guard prevents re-entrant hook invocations.
"""

import argparse
import asyncio
import hashlib
import os
import signal
import subprocess
import sys
import tempfile
import time
import traceback

_AI_TOOLING_SRC = os.environ.get('AI_TOOLING_SRC') or os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _AI_TOOLING_SRC not in sys.path:
    sys.path.insert(0, _AI_TOOLING_SRC)

from git_hooks_impl.branch_utils import parse_branch
from git_hooks_impl.entry_points.commands import leak_check as leak_check_cmd
from git_hooks_impl.entry_points.commands import registry
from git_hooks_impl.entry_points.extract_plan import (
    _discover_branch_and_ticket,
    cmd_cache_prune,
    cmd_cache_save,
    cmd_cache_swap,
    cmd_extract_plan,
)
from git_hooks_impl.entry_points.extract_plan import (
    cmd_planget as _cmd_planget,
)
from git_hooks_impl.entry_points.extract_plan import (
    scaffold_or_generate as _scaffold_or_generate,
)
from git_hooks_impl.entry_points.status import cmd_status as _cmd_status
from git_hooks_impl.entry_points.sync_mr import cmd_sync_mr
from git_hooks_impl.logger import config, dbg, err, log, warn
from git_hooks_impl.utils import AI_TOOLING_HOOK_RECURSION_GUARD, PLAN_FILE, run
from setup._link_helpers import _is_linked, _resolves_to_source
from setup.install_profiles import (
    cmd_install_profiles,
    toggle_hardening,
    toggle_tooling_enabled,
)
from setup.link import LINK_MAPPINGS
from setup.link import install as link_install
from setup.skills import cmd_setup_user_global
from setup.tools import cmd_install_tools


def _suppress_proactor_transport_del_errors(unraisable):
    exc = unraisable.exc_value
    obj_repr = repr(unraisable.object) if unraisable.object else ''
    if (isinstance(exc, RuntimeError)
            and 'Event loop is closed' in str(exc)
            and '_ProactorBasePipeTransport' in obj_repr):
        return
    sys.__unraisablehook__(unraisable)

sys.unraisablehook = _suppress_proactor_transport_del_errors

_SIGINT_ACTIVE_TASK = None


def _sigint_handler(signum, frame):
    if _SIGINT_ACTIVE_TASK is not None:
        _SIGINT_ACTIVE_TASK.cancel()


def _run_async_cmd(coro_fn, args):
    """Sync boundary for async cmd_*: installs task ref, runs event loop."""
    global _SIGINT_ACTIVE_TASK

    async def _with_task():
        global _SIGINT_ACTIVE_TASK
        _SIGINT_ACTIVE_TASK = asyncio.current_task()
        result = await coro_fn(args)
        # Yield to event loop so Windows ProactorEventLoop pipe transports
        # can schedule their cleanup callbacks before asyncio.run() closes
        # the loop. Without this, __del__ fires on a closed loop and prints
        # spurious "RuntimeError: Event loop is closed" to stderr.
        await asyncio.sleep(0.1)
        return result

    def _suppress_transport_del_errors(loop, context):
        # Suppress known Windows ProactorBasePipeTransport __del__ errors that
        # fire after loop closure. All other errors are forwarded to default.
        exc = context.get('exception')
        if isinstance(exc, RuntimeError) and 'Event loop is closed' in str(exc):
            return
        loop.default_exception_handler(context)

    try:
        loop = asyncio.new_event_loop()
        loop.set_exception_handler(_suppress_transport_del_errors)
        try:
            return loop.run_until_complete(_with_task())
        except (asyncio.CancelledError, KeyboardInterrupt):
            return 130
        finally:
            loop.close()
    finally:
        _SIGINT_ACTIVE_TASK = None


HELP_TEXT = """\
mr - AI tooling CLI

Usage:
  mr sync [--force]         Push MR description update (sync PLAN.md → MR;
                            --force overwrites a remotely-changed MR body)
  mr planget                Pull plan from MR description → local .ai/PLAN.md
  mr plangen [--force]      Generate PLAN.md via AI pipeline (uses cache; --force to regenerate)
  mr status                 Show MR + plan status
  mr setup                  Full setup - refreshes project hooks (if in a consumer project)
                            AND user-global ~/.claude/ hard-links. Idempotent.
  mr new --branch-name <b>  Create branch, generate plan (publish with `mr sync`)
  mr on                     Enable ai_tooling (set AI_TOOLING_ENABLED=true in ~/.bashrc)
  mr off                    Disable ai_tooling (set AI_TOOLING_ENABLED=false in ~/.bashrc)
  mr hardening on|off       Orchestrator mode. On: roles, dispatch, full verification stack.
                            Off (default): direct work, dirty commits, no side stack.
  mr verify                 Run lint (ruff) + test suite (unittest); exit nonzero if either fails
  mr script <name> [params...]  Run a command from the script registry (see commands/registry.py)
  mr help                   Show this message
"""


# ---------------------------------------------------------------------------
# Context detection helpers
# ---------------------------------------------------------------------------

def _git_project_root() -> str:
    """Returns the git toplevel, or raises SystemExit(1) with a hint if not in a repo."""
    try:
        return subprocess.check_output(
            ['git', 'rev-parse', '--show-toplevel'],
            stderr=subprocess.DEVNULL, text=True,
        ).strip()
    except subprocess.CalledProcessError:
        print('ERROR: not inside a git repo.', file=sys.stderr)
        print('  Run `mr setup` from inside a consumer project or ai_tooling itself.',
              file=sys.stderr)
        sys.exit(1)


def _is_ai_tooling_repo(project_root: str) -> bool:
    return os.path.normpath(project_root) == os.path.normpath(_AI_TOOLING_SRC)


# ---------------------------------------------------------------------------
# Smoke check helpers
# ---------------------------------------------------------------------------

def _cmd_ok(cmd: list) -> bool:
    try:
        subprocess.run(cmd, capture_output=True, timeout=5)
        return True
    except Exception:
        return False



def _run_smoke_checks(project_root: str, ai_tooling_mode: bool) -> int:
    """~6 probes, ~5s total. Print PASS/FAIL per probe. Return 0 if all pass."""
    failures = 0
    user_claude = os.path.expanduser('~/.claude')

    def probe(label: str, ok: bool) -> None:
        nonlocal failures
        status = 'PASS' if ok else 'FAIL'
        print(f'  [{status}] {label}')
        if not ok:
            failures += 1

    probe('glab --version',   _cmd_ok(['glab', '--version']))
    probe('jira --version',   _cmd_ok(['jira', '--version']))
    probe('claude --version', _cmd_ok(['claude', '--version']))
    probe('python imports (anthropic, coverage)',
          _cmd_ok(['python', '-c', 'import anthropic, coverage']))

    bashrc = os.path.expanduser('~/.bashrc')
    block_present = False
    if os.path.isfile(bashrc):
        with open(bashrc, encoding='utf-8', errors='replace') as f:
            block_present = '# >>> ai-tooling (managed)' in f.read()
    probe('~/.bashrc managed block present', block_present)

    skill_src  = os.path.join(_AI_TOOLING_SRC, 'claude', 'skills', 'orchestrator', 'SKILL.md')
    skill_dest = os.path.join(user_claude, 'skills', 'orchestrator', 'SKILL.md')
    probe('orchestrator SKILL.md symlinked to source', _resolves_to_source(skill_src, skill_dest))

    if not ai_tooling_mode:
        for src_rel, dst_rel in LINK_MAPPINGS:
            src = os.path.join(_AI_TOOLING_SRC, src_rel)
            dst = os.path.join(project_root, dst_rel)
            probe(f'hook stub symlinked: {dst_rel}', _is_linked(src, dst))

    print()
    if failures:
        print(f'  {failures} probe(s) FAILED - re-run `mr setup` after fixing.')
        return 1
    print('  All probes passed.')
    return 0


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

async def cmd_sync(args):
    # The sync-mr hook path shares this handler and registers no --force,
    # so getattr keeps a hook run from ever forcing an overwrite.
    return await cmd_sync_mr(force=getattr(args, 'force', False)) or 0


async def cmd_planget(args):
    return await _cmd_planget() or 0


async def cmd_plangen(args):
    branch, template_type, jira_ticket = _discover_branch_and_ticket()
    if branch is None:
        return 1
    try:
        await _scaffold_or_generate(branch, jira_ticket, template_type,
                                    force=args.force, interactive=True)
        return 0
    except Exception as exc:
        print(f'plangen failed: {exc}', file=sys.stderr)
        return 1


async def cmd_status(args):
    return await _cmd_status() or 0


def cmd_setup(args):
    """Universal setup - context-detected.

    Both modes (ai_tooling-repo and per-project) ALWAYS run the user-global
    hard-link refresh (cmd_setup_user_global). The user never has to manually
    `cd ${AI_TOOLING_SRC} && mr setup` to refresh user-local agents/skills/hooks
    after canonical edits - running `mr setup` from any consumer project
    refreshes both project hooks and the user-global Claude tree.
    """
    project_root = _git_project_root()
    ai_tooling_mode = _is_ai_tooling_repo(project_root)

    if getattr(args, 'setup_subcommand', None) == 'link':
        return link_install(project_root)

    if ai_tooling_mode:
        rc = cmd_install_profiles(_AI_TOOLING_SRC, {})
        if rc:
            return rc
        rc = cmd_install_tools(_AI_TOOLING_SRC)
        if rc:
            return rc
    else:
        rc = link_install(project_root)
        if rc:
            return rc

    # User-global hard-link refresh runs in BOTH modes. rc == 1 means user
    # declined the y/N confirmation - that's not a failure, continue to probes.
    rc = cmd_setup_user_global(_AI_TOOLING_SRC, auto_yes=args.yes)
    if rc and rc != 1:
        return rc

    rc = _run_smoke_checks(project_root, ai_tooling_mode)
    if ai_tooling_mode and rc == 0:
        print()
        print('Activate `mr` in your current shell:')
        print('    source ~/.bashrc')
        print()
        print('Or open a new terminal. Then verify with: mr help')
    return rc


async def cmd_new(args):
    """Create branch and generate its plan. Publish with `mr sync`.

    Steps:
      1. git checkout -b <branch> (fires post-checkout: cache_swap + link_check)
      2. Generate BRANCH_PLAN.md via the AI pipeline (scaffold_or_generate, non-interactive)
    """
    branch = args.branch_name
    _git_project_root()

    # Step 1: create branch (fires post-checkout: cache_swap + link_check)
    rc, _, _ = run(['git', 'checkout', '-b', branch])
    if rc:
        return rc

    # Step 2: generate the branch plan via the AI pipeline. interactive=False
    # is required - the interactive path calls prompt_yn(), which would hang
    # the same way `glab mr create` did (stdin=DEVNULL, no TTY to answer).
    template_type, jira_ticket = parse_branch(branch)
    await _scaffold_or_generate(branch, jira_ticket, template_type, interactive=False)

    log('Branch created and BRANCH_PLAN.md generated.')
    log(f'Review {PLAN_FILE}, then run `mr sync` to push the branch and open the MR.')
    return 0


def cmd_verify(args):
    """Run lint (ruff) + test suite (unittest) + leak check. Exit nonzero if any fails."""
    ai_dir = os.path.join(_AI_TOOLING_SRC, '.ai')
    plan_path = os.path.join(ai_dir, 'BRANCH_PLAN.md')
    tooling_path = os.path.join(ai_dir, 'tooling.log')

    # Snapshot before tests - no files written
    try:
        with open(plan_path, 'rb') as _f:
            plan_hash_before = hashlib.sha256(_f.read()).hexdigest()
    except OSError:
        plan_hash_before = None
    try:
        with open(tooling_path, encoding='utf-8') as _f:
            tooling_lines_before = sum(1 for _ in _f)
    except OSError:
        tooling_lines_before = None

    # Run ruff through the active interpreter so the repo-local env/ copy is
    # used without needing its Scripts/ dir on PATH.
    try:
        lint_rc = subprocess.call(
            [sys.executable, '-m', 'ruff', 'check', 'git_hooks_impl/', 'claude/hooks/'])
        print('ruff: clean' if lint_rc == 0 else 'ruff: violations found')
    except OSError as exc:
        print(f'ruff: could not run ({exc})')
        lint_rc = 1
    test_start = time.time()
    test_rc = subprocess.call(
        [sys.executable, '-m', 'unittest', 'discover',
         '-t', '.', '-s', '.', '-p', 'test_*.py', '-v']
    )
    os.environ['TEST_WALL_TIME_SECONDS'] = str(time.time() - test_start)
    print('tests: passed' if test_rc == 0 else 'tests: FAILED')

    # Leak marker written by git_hooks_impl/tests/__init__.py. The test process
    # restores the plan at exit, so the hash below is already healed by the time
    # it is read here - the marker is what actually reports the leak.
    leak_rc = 0
    backup_root = os.path.join(tempfile.gettempdir(), 'ai-tooling-backups')
    leak_marker = os.path.join(backup_root, 'last-run-leak.txt')
    try:
        with open(leak_marker, encoding='utf-8') as _f:
            marker_text = _f.read().strip()
    except OSError:
        marker_text = ''

    if marker_text:
        print(f'LEAK: {marker_text}')
        leak_rc = 1
    elif plan_hash_before is not None:
        # Secondary net: a write from outside the test process leaves no marker.
        try:
            with open(plan_path, 'rb') as _f:
                plan_hash_after = hashlib.sha256(_f.read()).hexdigest()
        except OSError:
            plan_hash_after = None
        if plan_hash_after != plan_hash_before:
            print('LEAK: PLAN.md content changed during tests '
                  'and was not restored')
            try:
                backups = sorted(name for name in os.listdir(backup_root)
                                 if os.path.isdir(os.path.join(backup_root, name)))
            except OSError:
                backups = []
            if backups:
                print(f'restore from: {os.path.join(backup_root, backups[-1])}')
            else:
                print('no backup found to restore from')
            leak_rc = 1
        else:
            print('plan: unchanged')

    if tooling_lines_before is not None:
        try:
            with open(tooling_path, encoding='utf-8') as _f:
                tooling_lines_after = sum(1 for _ in _f)
        except OSError:
            tooling_lines_after = tooling_lines_before
        if tooling_lines_after > tooling_lines_before:
            delta = tooling_lines_after - tooling_lines_before
            print(f'LEAK: tooling.log grew by {delta} lines during tests')
            leak_rc = 1
        else:
            print('tooling.log: unchanged')

    # Runs leak_check in-process; see leak_check.py for the check logic.
    leak_check_return_code = leak_check_cmd.run([])
    print('leak check: clean' if leak_check_return_code == 0 else 'leak check: FAILED')
    return max(lint_rc, test_rc, leak_rc, leak_check_return_code)


def cmd_script(args):
    # Deferred: keeps `mr` startup free of a hard dependency on the script
    # registry for every subcommand that isn't `mr script`.
    return registry.run(args.name, args.params)


def cmd_help(args):
    print(HELP_TEXT)
    return 0


def cmd_on(args):
    error = toggle_tooling_enabled(True)
    if error == 'not_found':
        err("Bashrc managed block not found. Run 'mr setup' first.")
        return 1
    if error == 'line_missing':
        err("AI_TOOLING_ENABLED line missing from managed block. Run 'mr setup' first.")
        return 1
    if error == 'already':
        warn('Tooling already enabled.')
        return 0
    log("Tooling enabled. Run 'source ~/.bashrc' or open a new shell.")
    return 0


def cmd_off(args):
    error = toggle_tooling_enabled(False)
    if error == 'not_found':
        err("Bashrc managed block not found. Run 'mr setup' first.")
        return 1
    if error == 'line_missing':
        err("AI_TOOLING_ENABLED line missing from managed block. Run 'mr setup' first.")
        return 1
    if error == 'already':
        warn('Tooling already disabled.')
        return 0
    log("Tooling disabled. Run 'source ~/.bashrc' or open a new shell.")
    return 0


def cmd_hardening(args):
    """`mr hardening on|off` - pick the orchestrator's mode for new sessions."""
    enabled = args.state == 'on'
    error = toggle_hardening(enabled)
    if error == 'not_found':
        err("Bashrc managed block not found. Run 'mr setup' first.")
        return 1
    if error == 'line_missing':
        err("IS_HARDENING line missing from managed block. Run 'mr setup' first.")
        return 1
    if error == 'already':
        warn(f"Hardening already {args.state}.")
        return 0
    log(f"Hardening {args.state}. Applies from the next tool call; new shells "
        f"pick it up too.")
    return 0


# ---------------------------------------------------------------------------
# Argparse setup
# ---------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        prog='mr',
        description=HELP_TEXT,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest='subcommand')

    sync_p = sub.add_parser('sync')
    sync_p.add_argument('--force', action='store_true')
    sub.add_parser('planget')

    gen = sub.add_parser('plangen')
    gen.add_argument('--force', action='store_true')

    sub.add_parser('status')

    setup_p = sub.add_parser('setup')
    setup_p.add_argument('--yes', '-y', action='store_true', help='Skip confirmation prompt')
    setup_sub = setup_p.add_subparsers(dest='setup_subcommand')
    setup_sub.add_parser('link')

    new_p = sub.add_parser(
        'new',
        help='Create branch and generate plan (publish with `mr sync`)',
        description=(
            'Create a branch and generate BRANCH_PLAN.md. Does not push or open an MR - '
            'review the plan, then run `mr sync` to push the branch and open the MR.\n'
            '\n'
            'The <slug> segment of the branch name selects the MR template:\n'
            '  private/<username>/<description>                 -> default template (no Jira)\n'
            '  <swimlane>/fixes/[TICKET_]<description>          -> fix template\n'
            '  <swimlane>/features/[TICKET_]<description>       -> feature template\n'
            '  <swimlane>/devices/<description>                 -> default template\n'
            '  <swimlane>/docs/[TICKET_]<description>           -> documentation template\n'
            '  <swimlane>/documentation/[TICKET_]<description>  -> documentation template\n'
            '\n'
            'Example: productname/docs/PROJECTNAME-1234_update_readme'
            'Example: productname/docs/PROJECTNAME-1234_update_readme'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    new_p.add_argument(
        '--branch-name', required=True, dest='branch_name',
        metavar='<swimlane>/<slug>/[TICKET_]<description>',
        help='branch to create; the <slug> segment selects the template (see above)',
    )

    sub.add_parser('on')
    sub.add_parser('off')

    hardening_p = sub.add_parser('hardening')
    hardening_p.add_argument('state', choices=('on', 'off'))

    sub.add_parser('verify')

    script_p = sub.add_parser('script')
    script_p.add_argument('name', nargs='?', default=None)
    script_p.add_argument('params', nargs=argparse.REMAINDER)

    sub.add_parser('help')

    # Hook subcommands
    sub.add_parser('sync-mr')
    extract_p = sub.add_parser('extract-plan')
    extract_p.add_argument('--force', action='store_true')
    sub.add_parser('get-plan')
    cache_swap_p = sub.add_parser('cache-swap')
    cache_swap_p.add_argument('--prev-ref', dest='prev_ref')
    sub.add_parser('cache-save')
    sub.add_parser('cache-prune')

    return parser


# ---------------------------------------------------------------------------
# Hook-subcommand wrappers (adapt no-args/kwarg callees to (args) signature)
# ---------------------------------------------------------------------------

async def _hook_get_plan(args):
    return await _cmd_planget()


async def _hook_extract_plan(args):
    return await cmd_extract_plan(force=args.force)


# ---------------------------------------------------------------------------
# Command dispatch table (mr CLI + hook subcommands unified)
# ---------------------------------------------------------------------------

COMMANDS = {
    # mr CLI subcommands
    'status':       lambda a: _run_async_cmd(cmd_status, a),
    'sync':         lambda a: _run_async_cmd(cmd_sync, a),
    'plangen':      lambda a: _run_async_cmd(cmd_plangen, a),
    'planget':      lambda a: _run_async_cmd(cmd_planget, a),
    'new':          lambda a: _run_async_cmd(cmd_new, a),
    'setup':        lambda a: cmd_setup(a),
    'on':           lambda a: cmd_on(a),
    'off':          lambda a: cmd_off(a),
    'hardening':    lambda a: cmd_hardening(a),
    'verify':       lambda a: cmd_verify(a),
    'script':       lambda a: cmd_script(a),
    'help':         lambda a: cmd_help(a),
    # hook subcommands
    'sync-mr':      lambda a: _run_async_cmd(cmd_sync, a),
    'extract-plan': lambda a: _run_async_cmd(_hook_extract_plan, a),
    'get-plan':     lambda a: _run_async_cmd(_hook_get_plan, a),
    'cache-swap':   lambda a: (cmd_cache_swap(prev_ref=a.prev_ref) or 0),
    'cache-save':   lambda a: (cmd_cache_save() or 0),
    'cache-prune':  lambda a: (cmd_cache_prune() or 0),
}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    if os.environ.get(AI_TOOLING_HOOK_RECURSION_GUARD):
        return 0
    os.environ[AI_TOOLING_HOOK_RECURSION_GUARD] = '1'

    parser = build_parser()
    args = parser.parse_args()

    if args.subcommand is not None:
        config.command = args.subcommand
        dbg(f'Command: {args.subcommand}')

    signal.signal(signal.SIGINT, _sigint_handler)
    handler = COMMANDS.get(args.subcommand, lambda a: (parser.print_help(), 1)[1])

    result = 0
    try:
        result = handler(args)
    except Exception as exc:
        err(f'Unexpected error: {exc}')
        err(traceback.format_exc())
        # A crashed command is a failed command. Returning 0 here would let a
        # broken gate (`mr verify`) report success.
        return 1

    return result if result is not None else 0


if __name__ == '__main__':
    sys.exit(main())
