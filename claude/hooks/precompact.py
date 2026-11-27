#!/usr/bin/env python
"""PreCompact hook: snapshots the current workflow position before compaction.

Reads PreCompact event JSON from stdin (`transcript_path`), scans the
transcript backward for the most recent WF-2B status line
(`[Orchestration: {role} / {workflow} - Phase {N}[ Step {N.M}], state
kept]`, shared/rules/workflow.md) and writes it to
`.ai/cache/{sanitized_branch}/session_state.md`.

PreCompact stdout is never injected into the model's context (unlike
SessionStart) - this hook's only job is the disk write. The injection
happens separately, in resume_after_compact.py, on the SessionStart that
follows with source=compact.

This hook is self-contained (no import of git_hooks_impl): it runs from
any project directory the orchestrator skill is installed into, not only
this source repo.
"""
import json
import os
import re
import subprocess
import sys

try:
    from . import _branch
except ImportError:
    import _branch
_sanitize_branch = _branch.sanitize_branch

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

_STATUS_RE = re.compile(
    r'\[Orchestration:\s*([^/]+?)\s*/\s*(.+?)\s*-\s*'
    r'Phase\s*(\S+)(?:\s+Step\s*(\S+))?,\s*state kept\]'
)


def _git(*args):
    try:
        return subprocess.run(
            ['git', *args], capture_output=True, text=True, timeout=5
        ).stdout.strip()
    except Exception:
        return ''


def _iter_transcript_texts(transcript_path):
    """Yields every string found in each transcript line, most recent line first."""
    try:
        with open(transcript_path, encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
    except OSError:
        return
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        yield from _strings_in(obj)


def _strings_in(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings_in(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings_in(v)


def find_last_status_line(transcript_path):
    """Returns a match object for the most recent WF-2B status line, or None."""
    for text in _iter_transcript_texts(transcript_path):
        m = _STATUS_RE.search(text)
        if m:
            return m
    return None


def write_session_state(root, branch, match, note_line):
    branch_dir = os.path.join(root, '.ai', 'cache', _sanitize_branch(branch))
    os.makedirs(branch_dir, exist_ok=True)
    state_path = os.path.join(branch_dir, 'session_state.md')
    role, workflow, phase, step = match.group(1), match.group(2), match.group(3), match.group(4)
    lines = [
        f'Role: {role.strip()}',
        f'Workflow: {workflow.strip()}',
        f'Phase: {phase.strip()}',
    ]
    if step:
        lines.append(f'Step: {step.strip()}')
    lines.append(f'Note: {note_line.strip()}')
    with open(state_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    return state_path


def main():
    is_disabled = os.getenv('AI_TOOLING_ENABLED') == 'false'
    if is_disabled:
        return 0

    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0

    transcript_path = event.get('transcript_path')
    if not transcript_path or not os.path.isfile(transcript_path):
        return 0

    if not os.path.isdir('.git'):
        return 0

    branch = _git('rev-parse', '--abbrev-ref', 'HEAD')
    if not branch:
        return 0

    default = (
        _git('symbolic-ref', '--short', 'refs/remotes/origin/HEAD') or 'origin/master'
    ).rsplit('/', 1)[-1]
    if branch == default:
        # No workflow position is worth tracking on the default branch -
        # work there isn't the orchestrator's per-branch session in the
        # first place.
        return 0

    match = find_last_status_line(transcript_path)
    if not match:
        return 0

    write_session_state(os.getcwd(), branch, match, match.group(0))
    return 0


if __name__ == '__main__':
    sys.exit(main())
