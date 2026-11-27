#!/usr/bin/env python
"""SessionStart hook (matcher: compact) - injects a resume block after compaction.

Reads `.ai/cache/{sanitized_branch}/session_state.md` (written by
precompact.py just before compaction) and emits a short RESUME block
instead of the full mandatory-read manifest session_start.py emits on a
cold start. Per WF-16 RESUME-ON-COMPACTION
(shared/rules/workflow.md): continue the named step, re-read a rule file
only for a new task or a rule you must quote.

If the state file is missing or unparsable, fall back to the full
manifest - degrade toward safety, not toward silence.

Self-contained: no import of git_hooks_impl (see precompact.py header).
"""
import os
import subprocess
import sys

try:
    from . import _branch, _manifest, _mode
except ImportError:
    import _branch
    import _manifest
    import _mode
_sanitize_branch = _branch.sanitize_branch

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

_SKILL_ROOT = _manifest.SKILL_ROOT


def _git(*args):
    try:
        return subprocess.run(
            ['git', *args], capture_output=True, text=True, timeout=5
        ).stdout.strip()
    except Exception:
        return ''


def _parse_state(path):
    fields = {}
    try:
        with open(path, encoding='utf-8') as f:
            for line in f:
                if ':' not in line:
                    continue
                key, _, value = line.partition(':')
                fields[key.strip().lower()] = value.strip()
    except OSError:
        return None
    if 'role' not in fields or 'workflow' not in fields or 'phase' not in fields:
        return None
    return fields


def _emit_resume_block(fields):
    step_part = f" Step {fields['step']}" if fields.get('step') else ''
    print(
        f"RESUME: {fields['role']} / {fields['workflow']} / "
        f"Phase {fields['phase']}{step_part}"
    )
    print('Continue this step. Do NOT re-read the rule stack.')
    print('Re-read only on: a new task, or a rule you must quote.')
    print(
        "If this phase's mode tag (PLAN MODE / EXIT PLAN MODE) matters for "
        "the next action, check it in the workflow file below - do not "
        "re-read the whole file."
    )
    print(
        f'Index: {_SKILL_ROOT}/SKILL.md | '
        f'{_SKILL_ROOT}/shared/rules/{{style,agents,workflow,documentation}}.md | '
        f'{_SKILL_ROOT}/roles/<role>/{{rules,workflow}}.md'
    )


def _emit_full_manifest_fallback():
    print('RESUME: no session_state.md found, falling back to full manifest.')
    print('Mandatory to read before continue:')
    print('  - .ai/BRANCH_PLAN.md')
    for rel in _manifest.MANDATORY_FILES:
        print(f'  - {_SKILL_ROOT}/{rel}')
    print(f'  - {_SKILL_ROOT}/roles/<chosen-role>/rules.md')
    print(f'  - {_SKILL_ROOT}/roles/<chosen-role>/workflow.md')


def _emit_poc_resume():
    """POC has no workflow position to resume - only the contract to restate."""
    print(_mode.POC_CONTRACT)
    print()
    print('No role or workflow is active, and none is needed. Do NOT re-read '
          'the rule stack. Read a rule file only to quote or apply a specific '
          'rule; read the full stack only once the developer moves the session '
          'to hardening.')


def _emit_branch_reminder():
    """Restates the cheap, local, decision-driving facts from session_start.py's
    BRANCH CONTEXT block - branch, local plan presence, other worktrees - so
    a compaction doesn't silently drop them. Skips the network-calling
    remote-plan check and the label-only JIRA/GitLab fields: cold start is
    the only place those are worth their cost.
    """
    if not os.path.isdir('.git'):
        return
    branch = _branch.current_branch()
    if not branch:
        return
    default = _branch.default_branch()
    local_plan = 'present' if _branch.local_plan_present() else 'absent'

    print()
    print('=== BRANCH CONTEXT (post-compaction) ===')
    print(f'BRANCH: {branch}')
    print(f'DEFAULT-BRANCH: {default}')
    print(f'LOCAL-PLAN: {local_plan}')
    if local_plan == 'absent' and branch != default:
        print('NOTE: no .ai/BRANCH_PLAN.md found for this branch. '
              'Run `mr plangen` to generate one.')

    others = _branch.other_worktrees()
    if others:
        print('OTHER-WORKTREES:')
        for line in others:
            print(f'  {line}')


def _find_state():
    """Returns the parsed WF-2B status fields for this branch, or None."""
    if not os.path.isdir('.git'):
        return None
    branch = _git('rev-parse', '--abbrev-ref', 'HEAD')
    if not branch:
        return None
    state_path = os.path.join(
        '.ai', 'cache', _sanitize_branch(branch), 'session_state.md'
    )
    if not os.path.isfile(state_path):
        return None
    return _parse_state(state_path)


def main():
    is_disabled = os.getenv('AI_TOOLING_ENABLED') == 'false'
    if is_disabled:
        return 0

    fields = _find_state()

    if fields is not None:
        print(_mode.contract())
        print()
        _emit_resume_block(fields)
    elif _mode.is_hardening():
        _emit_full_manifest_fallback()
    else:
        _emit_poc_resume()

    _emit_branch_reminder()
    return 0


if __name__ == '__main__':
    sys.exit(main())
