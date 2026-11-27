# Test package init — backup .ai/, redirect file logging to TESTS.log
#
# Real hooks write to .ai/hook.log (via logger.py).
# Tests redirect dbg()/log()/etc. file output to a temp directory so test
# runs never write into the live .ai/ directory (CWD-relative leak).
# stderr output (warnings, errors) remains visible in test runner output.
#
# Before any of that, this module backs up the whole .ai/ directory so a
# test that writes into the live .ai/ (CWD-relative leak) is recoverable.

import atexit
import contextlib
import hashlib
import os
import shutil
import sys
import tempfile
import time

import git_hooks_impl.logger as _logger

_AI_DIR = '.ai'
_PLAN_PATH = os.path.join(_AI_DIR, 'BRANCH_PLAN.md')
_BACKUP_ROOT = os.path.join(tempfile.gettempdir(), 'ai-tooling-backups')
_BACKUP_STAMP_FORMAT = '%Y-%m-%d_%H%M%S'

# Leak marker. The restore below runs inside the test process, so by the time
# a parent runner (`mr verify`) re-reads the plan the damage is already healed
# and a hash comparison there can never see it. This file carries the fact
# across the process boundary.
_LEAK_MARKER = os.path.join(_BACKUP_ROOT, 'last-run-leak.txt')


def _backup_ai_dir():
    """Copy the whole .ai/ directory into a timestamped backup dir.

    Returns the backup path, or None when .ai/ is absent or the copy
    failed. Never raises — a failed backup must not break the suite.
    """
    try:
        if not os.path.isdir(_AI_DIR):
            return None
        stamp = time.strftime(_BACKUP_STAMP_FORMAT)
        dest = os.path.join(_BACKUP_ROOT, f'{stamp}-test-run-.ai')
        shutil.copytree(_AI_DIR, dest)
        return dest
    except Exception:
        return None


def _prune_backups(keep=10):
    """Keep only the newest `keep` backup dirs under _BACKUP_ROOT.

    Names are timestamped so they sort chronologically. Never raises.
    """
    try:
        entries = sorted(name for name in os.listdir(_BACKUP_ROOT)
                         if os.path.isdir(os.path.join(_BACKUP_ROOT, name)))
        stale = entries[:-keep] if keep > 0 else entries
        for name in stale:
            shutil.rmtree(os.path.join(_BACKUP_ROOT, name), ignore_errors=True)
    except Exception:
        pass


def _hash_plan():
    """Return the SHA-256 hex digest of the real plan file, or None if absent."""
    try:
        with open(_PLAN_PATH, 'rb') as _f:
            return hashlib.sha256(_f.read()).hexdigest()
    except OSError:
        return None


def _clear_leak_marker():
    """Drop any marker left by a previous run. Never raises."""
    with contextlib.suppress(OSError):
        os.remove(_LEAK_MARKER)


def _write_leak_marker(text):
    """Record a leak so a parent runner can see it. Never raises."""
    try:
        os.makedirs(_BACKUP_ROOT, exist_ok=True)
        with open(_LEAK_MARKER, 'w', encoding='utf-8') as handle:
            handle.write(text + '\n')
    except OSError:
        pass


_backup_dir = _backup_ai_dir()
_prune_backups(keep=10)
_clear_leak_marker()
_plan_hash_before = _hash_plan()


@atexit.register
def _restore_leaked_plan():
    """Put the real plan file back if a test overwrote it during this run.

    The backup taken at import is this run's own snapshot, so restoring
    from it cannot resurrect an older plan. A leak is a test bug — the
    restore keeps the developer's working copy intact while the stderr
    line makes the bug visible instead of silent.
    """
    try:
        if _plan_hash_before is None or _backup_dir is None:
            return
        if _hash_plan() == _plan_hash_before:
            return

        source = os.path.join(_backup_dir, 'BRANCH_PLAN.md')
        if not os.path.isfile(source):
            message = (f'a test modified the real {_PLAN_PATH} and no backup '
                       f'copy exists to restore from')
        else:
            shutil.copy2(source, _PLAN_PATH)
            restored = _hash_plan() == _plan_hash_before
            outcome = 'restored' if restored else 'RESTORE FAILED'
            message = (f'a test modified the real {_PLAN_PATH} during this run - '
                       f'{outcome} from {source}')

        _write_leak_marker(message)
        print(
            f'WARNING: {message}',
            file=sys.stderr,
        )
    except Exception as exc:
        message = f'could not restore {_PLAN_PATH} after a test modified it: {exc}'
        _write_leak_marker(message)
        print(f'WARNING: {message}', file=sys.stderr)


# Redirect log directory to a temp dir — prevents writing TESTS.log
# into the live .ai/ when tests run from the repo root.
_test_log_dir = os.path.join(tempfile.gettempdir(), 'hooks_tests')
_logger._LOG_DIR = _test_log_dir
_logger._LOG_FILE = 'TESTS.log'

# Enable file logging for test runs
_logger.config.command = 'test'

# Truncate the log at test start so it only contains current run
os.makedirs(_test_log_dir, exist_ok=True)
_log_path = os.path.join(_test_log_dir, _logger._LOG_FILE)
open(_log_path, 'w').close()
