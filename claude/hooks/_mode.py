#!/usr/bin/env python
"""Shared POC/hardening mode state for the orchestrator's hooks.

Mode lives in one place: `IS_HARDENING`. Unset or false means POC, so the
default needs no declaration; hardening is the mode that has to be asked
for, and `mr hardening on|off` is how it is set.

That command rewrites the export inside the bashrc managed block, and that
line is the record: it is read first, before the environment. The profile
exports `IS_HARDENING` into every session, so a session that started in POC
carries `IS_HARDENING=false` in its environment forever - reading the
environment first would pin the mode to whatever it was at launch and make
`mr hardening on` do nothing until a restart. Reading the file makes the
switch land on the next tool call instead.

The env var is the fallback, for a session launched with no managed block:

    IS_HARDENING=1 claude

Nothing else is written. The mode survives a restart, a resume and every
compaction because the bashrc line does.
"""
import os
import re

ENV_VAR = 'IS_HARDENING'
_FALSE = ('', '0', 'false', 'no', 'off')

_BLOCK_BEGIN = '# >>> ai-tooling (managed) >>>'
_BLOCK_END = '# <<< ai-tooling (managed) <<<'
_EXPORT_RE = re.compile(rf'^\s*export\s+{ENV_VAR}=(.*)$')


def _from_bashrc():
    """Reads IS_HARDENING out of the bashrc managed block, or '' if absent."""
    path = os.path.join(os.path.expanduser('~'), '.bashrc')
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            lines = f.read().splitlines()
    except OSError:
        return ''

    inside = False
    for line in lines:
        stripped = line.strip()
        if stripped == _BLOCK_BEGIN:
            inside = True
        elif stripped == _BLOCK_END:
            inside = False
        elif inside:
            m = _EXPORT_RE.match(line)
            if m:
                return m.group(1).strip().strip('"').strip("'")
    return ''


def is_hardening():
    value = _from_bashrc() or os.environ.get(ENV_VAR) or ''
    return value.strip().lower() not in _FALSE


POC_CONTRACT = """MODE: poc  (IS_HARDENING off -> the default). The developer builds the workflow on the fly.
- Follow the order given. No roadmap, no convergence loops. Switch role or
  approach on request.
- Sub-agents are for investigation, not for execution or verification:
  Explore for a lookup, general-purpose when a bigger picture has to come
  from several places at once. Never a role dispatch to do the work.
- Read the rules and comply where compliance is free: style STYLE-1..9,
  commit conventions (G2 subject, G8 body, G12 terms, G15 ticket), DEL-6
  dependency read before an edit.
- Run no other check. Deferred to hardening: refactorer R1-R14, tests,
  plan-writer audit, consistency agent, DRD convergence.
- One exception, never deferred: build the production targets. No test
  target, no ctest, no test binary, no test suite of any kind.
- Every commit lands dirty: `Verb (dirty) description`. No approval gate -
  commit, then show `git log -1`. Wrong message: amend it. Never amend
  content, an older commit, or anything pushed.
- Never switch to hardening yourself. If a request signals it (tests,
  review, cleanup, "verify this"), ASK first; on approval run
  `mr hardening on`, which takes effect from the next tool call."""

POC_REMINDER = (
    'MODE: poc. Commits land dirty (`Verb (dirty) description`), no approval '
    'gate, production build only, no role dispatch. Hardening is '
    '`mr hardening on` - ask before running it, never assume it.'
)

HARDENING_CONTRACT = """MODE: hardening  (IS_HARDENING on). Full orchestration is in force; `mr hardening off` returns to poc.
1. Follow answering and writing style rules: BE-SIMPLE, BE-ACTUAL, and UNIFORM-QUESTIONS
2. Follow all session rules: SESSION-PLAN-FIRST, BRANCH-PLAN-LAST, EXECUTION-STRUCTURE, AFTER-EXECUTION-VERIFICATION, and WISE-REFLECTION
3. Select an orchestrator role for this request and use the orchestrator skill's shared resources before acting alone."""

HARDENING_REMINDER = (
    'MODE: hardening. Select a role, dispatch it, and run the full gate stack.'
)


def contract():
    return HARDENING_CONTRACT if is_hardening() else POC_CONTRACT


def reminder():
    return HARDENING_REMINDER if is_hardening() else POC_REMINDER
