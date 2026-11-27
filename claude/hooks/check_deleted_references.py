#!/usr/bin/env python
"""PostToolUse hook: on switching to a different file, asks whether the one
just finished describes something that is no longer there (STYLE-10
NO-DELETED-REFERENCES).

Fires on the switch, not on every edit. A file under active editing gets
touched many times in a row, and asking after each touch is noise about work
that is not finished yet. The question lands once, when attention moves on
and the previous file is done.

Detection only, and deliberately a question rather than a verdict. Every
phrase it matches has a legitimate use - a rule may quote "no longer" as its
own anti-pattern example, a docstring may state that a value "used to" come
from elsewhere as a real constraint. Only the author knows which.

The file under edit is tracked per session in a small state file, since a
hook runs as a subprocess and cannot hold the session's environment.

Reads PostToolUse event JSON from stdin per the hook contract.
"""
import json
import os
import re
import sys
import tempfile

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

_CHECKED_EXTENSIONS = ('.cpp', '.hpp', '.h', '.py', '.md', '.txt')

_EXCLUDED_DIR_SEGMENTS = ('.claude', 'cache')
_EXCLUDED_FILES = ('.ai/BRANCH_PLAN.md',)

_STATE_DIR = os.path.join(tempfile.gettempdir(), 'orchestrator_edit_focus')

# Phrasings that define the present by contrast with something the reader
# cannot see. Word-bounded, case-insensitive.
_PATTERNS = [
    r'no longer',
    r'used to (?:be|have|live|sit|carry|run|call|hold)',
    r'(?:previously|formerly|originally)\b',
    r'(?:was|were|been) (?:removed|deleted|dropped|renamed|replaced|deprecated)',
    r'(?:we |I )?(?:removed|deleted|dropped|renamed|replaced) the\b',
    r'replaces the (?:old|previous|former)',
    r'instead of the (?:old|previous|former)',
    r'renamed from\b',
    r'\bdeprecated\b',
    r'\bany ?more\b',
    r'(?:is|are) gone\b',
    r'\bex-\w+',
]
_PHRASE_RE = re.compile('|'.join(f'(?:{p})' for p in _PATTERNS), re.IGNORECASE)


def _is_checkable(file_path):
    if not file_path or not file_path.lower().endswith(_CHECKED_EXTENSIONS):
        return False
    normalized = file_path.replace('\\', '/')
    if any(normalized.endswith(e) for e in _EXCLUDED_FILES):
        return False
    return not any(p in _EXCLUDED_DIR_SEGMENTS for p in normalized.split('/'))


def _state_path(session_id):
    safe = ''.join(c for c in str(session_id) if c.isalnum() or c in '-_')
    return os.path.join(_STATE_DIR, (safe[:120] or 'default') + '.focus')


def _read_focus(session_id):
    try:
        with open(_state_path(session_id), encoding='utf-8') as f:
            return f.read().strip()
    except OSError:
        return ''


def _write_focus(session_id, file_path):
    try:
        os.makedirs(_STATE_DIR, exist_ok=True)
        with open(_state_path(session_id), 'w', encoding='utf-8') as f:
            f.write(file_path)
    except OSError:
        pass


def find_hits(lines):
    """Return (line number, matched phrase) for each line defining by contrast."""
    hits = []
    for i, line in enumerate(lines):
        m = _PHRASE_RE.search(line)
        if m:
            hits.append((i + 1, m.group(0)))
    return hits


def scan(file_path):
    if not os.path.isfile(file_path):
        return []
    try:
        with open(file_path, encoding='utf-8') as f:
            return find_hits(f.readlines())
    except (OSError, UnicodeDecodeError):
        return []


def main():
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0

    if event.get('tool_name') not in ('Edit', 'Write'):
        return 0

    current = (event.get('tool_input') or {}).get('file_path')
    if not _is_checkable(current):
        return 0

    session_id = event.get('session_id') or ''
    previous = _read_focus(session_id)
    _write_focus(session_id, current)

    same_file = os.path.normcase(os.path.normpath(previous or '')) == \
        os.path.normcase(os.path.normpath(current))
    if not previous or same_file:
        return 0

    hits = scan(previous)
    if not hits:
        return 0

    shown = ', '.join(f'{n} ("{p}")' for n, p in hits[:6])
    more = f' (+{len(hits) - 6} more)' if len(hits) > 6 else ''
    message = (
        f"[check_deleted_references] Don't you write about deleted stuff in "
        f'the previous file? Is the described stuff actual? {previous}: '
        f'line(s) {shown}{more}. STYLE-10 NO-DELETED-REFERENCES: write what '
        f'is there. Keep a line only when it is an anti-pattern example or a '
        f'real current-behaviour constraint.'
    )
    print(json.dumps({
        'hookSpecificOutput': {
            'hookEventName': 'PostToolUse',
            'additionalContext': message,
        }
    }))
    return 0


if __name__ == '__main__':
    sys.exit(main())
