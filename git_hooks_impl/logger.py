#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Logging, color helpers, and the config singleton.

Extracted from utils.py so that every module can import logging without
pulling in subprocess helpers, GitLab API wrappers, or template code.
logger.py has no project-internal imports (only stdlib + colorama),
which breaks all potential circular-import cycles.
"""

import contextlib
import datetime
import os
import sys
import threading

import colorama
from colorama import Fore, Style

# ---------------------------------------------------------------------------
#  Config (shared mutable state)
# ---------------------------------------------------------------------------

class _Config:
    """Module-level singleton — stores current command name for file logging."""
    command = ''

config = _Config()

# Shared lock for stderr — prevents progress spinner and log messages from
# interleaving. Defined here (stdlib only) so progress.py can import it.
stderr_lock = threading.Lock()


# ---------------------------------------------------------------------------
#  Console encoding
# ---------------------------------------------------------------------------

def _force_utf8_streams():
    """Write UTF-8 to stdout and stderr regardless of the platform default.

    Windows hands Python a cp1252 stream while the terminal decodes UTF-8, so
    every non-ASCII character arrives as a replacement glyph. Runs at import so
    all entry points inherit it. Streams that cannot be reconfigured (already
    wrapped, or replaced by a test harness) are left alone.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, 'reconfigure', None)
        if reconfigure is None:
            continue
        with contextlib.suppress(ValueError, OSError):
            reconfigure(encoding='utf-8')


_force_utf8_streams()


# ---------------------------------------------------------------------------
#  Colors (via colorama — handles Windows console VTP automatically)
# ---------------------------------------------------------------------------

colorama.just_fix_windows_console()

_COLORS_ENABLED = sys.stderr.isatty() and not os.environ.get('NO_COLOR')

def cyan(text):
    """Wrap text in cyan. ``cyan(console_tag())`` → ``'\033[36m[plangen]\033[0m'``."""
    return f'{Fore.CYAN}{text}{Style.RESET_ALL}' if _COLORS_ENABLED else str(text)

def green(text):
    return f'{Fore.GREEN}{text}{Style.RESET_ALL}' if _COLORS_ENABLED else str(text)

def yellow(text):
    return f'{Fore.YELLOW}{text}{Style.RESET_ALL}' if _COLORS_ENABLED else str(text)

def bold_red(text):
    return f'{Style.BRIGHT}{Fore.RED}{text}{Style.RESET_ALL}' if _COLORS_ENABLED else str(text)

def dim(text):
    return f'{Style.DIM}{text}{Style.RESET_ALL}' if _COLORS_ENABLED else str(text)


# ---------------------------------------------------------------------------
#  Caller inspection — powers the unified log format
# ---------------------------------------------------------------------------

def _caller_info():
    """Return (filename, class_name_or_None, function_name) of the caller.

    Frame 0 = _caller_info, frame 1 = log/warn/etc, frame 2 = actual caller.
    filename includes the extension (e.g. 'sync_mr.py', not 'sync_mr').
    """
    try:
        frame = sys._getframe(2)
        full_path = frame.f_code.co_filename
        filename = os.path.basename(full_path)
        function_name = frame.f_code.co_name

        # Instance method — 'self' in locals
        instance = frame.f_locals.get('self')
        if instance is not None:
            class_name = type(instance).__name__
            return (filename, class_name, function_name)

        # Classmethod — 'cls' in locals
        cls = frame.f_locals.get('cls')
        if cls is not None:
            class_name = cls.__name__
            return (filename, class_name, function_name)

        return (filename, None, function_name)
    except Exception:
        return ('<unknown>', None, '<unknown>')


def _console_prefix(command):
    """Build the short console prefix: [command] or [mr] fallback."""
    return f'[{command}]' if command else '[mr]'


def console_tag():
    """Public accessor for modules outside the log/warn/err/ok family
    (progress.py, utils.py) that print a bare tag instead of a full log line.
    Same dynamic [command] source as log()/warn()/err()/ok().
    """
    return _console_prefix(config.command)


def _file_prefix(filename, class_name, function_name, command):
    """Build the full file-log prefix: [timestamp] [file] [class] [func] [command]."""
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    parts = [f'[{timestamp}]', f'[{filename}]']

    if class_name:
        parts.append(f'[{class_name}]')

    parts.append(f'[{function_name}]')

    if command:
        parts.append(f'[{command}]')

    return ' '.join(parts)


def _log_context(filename, class_name, function_name, command):
    """Build the unified metadata prefix for a log line (file log shape)."""
    return _file_prefix(filename, class_name, function_name, command)


# ---------------------------------------------------------------------------
#  File logging (append-only, single tooling.log in .ai/)
# ---------------------------------------------------------------------------

_LOG_DIR = '.ai'
_LOG_FILE = 'tooling.log'
_LOG_WARN_BYTES = 1024 * 1024 * 1024  # warn at 1 GB


def _file_write(line):
    """Append a single line to the log file. Never raises."""
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        log_path = os.path.join(_LOG_DIR, _LOG_FILE)

        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(line + '\n')

        try:
            if os.path.getsize(log_path) > _LOG_WARN_BYTES:
                # Print directly to stderr — avoids warn->_file_write->warn recursion
                print(f'WARNING: Log file {log_path} exceeds 1 GB. Consider deleting it.',
                      file=sys.stderr, flush=True)
        except OSError:
            pass
    except Exception:
        pass  # never fail


# ---------------------------------------------------------------------------
#  Logging helpers (stderr + file)
# ---------------------------------------------------------------------------

def dbg(msg):
    """Debug message — written to file log only (not stderr)."""
    filename, class_name, function_name = _caller_info()
    prefix = _log_context(filename, class_name, function_name, config.command)
    _file_write(f'{prefix} {msg}')


def _stderr_print(text):
    """Write to stderr under lock, clearing any active spinner first."""
    with stderr_lock:
        sys.stderr.write('\r' + ' ' * 80 + '\r' + text + '\n')
        sys.stderr.flush()


def log(msg):
    filename, class_name, function_name = _caller_info()
    con = _console_prefix(config.command)
    fil = _file_prefix(filename, class_name, function_name, config.command)
    _stderr_print(f'{cyan(con)} {msg}')
    _file_write(f'{fil} {msg}')


def ok(msg):
    filename, class_name, function_name = _caller_info()
    con = _console_prefix(config.command)
    fil = _file_prefix(filename, class_name, function_name, config.command)
    _stderr_print(f'{green(con)} {msg}')
    _file_write(f'{fil} {msg}')


def warn(msg):
    filename, class_name, function_name = _caller_info()
    con = _console_prefix(config.command)
    fil = _file_prefix(filename, class_name, function_name, config.command)
    _stderr_print(f'{yellow(con)} {msg}')
    _file_write(f'{fil} {msg}')


def err(msg):
    filename, class_name, function_name = _caller_info()
    con = _console_prefix(config.command)
    fil = _file_prefix(filename, class_name, function_name, config.command)
    _stderr_print(f'{bold_red(con)} {msg}')
    _file_write(f'{fil} {msg}')
