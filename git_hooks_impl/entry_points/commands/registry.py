#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Dict-based command registry for `mr script <name> [params...]`.

Each entry maps a command name to its callable and audience. The one-line
help shown in the listing is never hand-written here - it's derived from
each command module's own first docstring line, so it can't go stale
independently of the module it describes.
"""

import re
import sys

from git_hooks_impl.entry_points.commands import (
    audit_plan,
    check_comment_style,
    classify_diff,
    compile_mermaid,
    dump_code_quality_reference,
    evt_compile,
    leak_check,
    plan_summary,
    publish_review_subtask,
    read_logs,
    run_coverage,
    run_cpp_tests,
    session_state,
    test_timings,
    validate_agent_files,
    validate_skill_conventions,
    verify_commit_builds,
)

# Matches a leading "`mr script <name>`" or "<filename>.py" prefix, then a
# hyphen or em-dash separator, at the start of a module's first docstring
# line. Built from chr(0x2014) rather than a literal dash character, so
# the em-dash auto-fix hook has nothing in this file to mangle.
_DASH_CLASS = '[-' + chr(0x2014) + ']'
_DOC_PREFIX_RE = re.compile(r'^(?:`mr script [^`]+`|[\w.]+\.py)\s*' + _DASH_CLASS + r'\s*')


def _help_from_docstring(module) -> str:
    """Derives a one-line help string from a command module's docstring.

    Takes the first line, strips the leading "`mr script <name>` -" or
    "<filename>.py -" prefix and a trailing period. Falls back to the raw
    first line if the prefix pattern doesn't match, and to an empty string
    if the module has no docstring at all.
    """
    doc = (module.__doc__ or '').strip()
    if not doc:
        return ''
    first_line = doc.splitlines()[0].strip()
    first_line = _DOC_PREFIX_RE.sub('', first_line)
    return first_line.rstrip('.')


# name -> {'callable': fn(argv) -> int, 'audience': 'dev'|'user'}
_MODULES = {
    'read_logs': read_logs,
    'run_cpp_tests': run_cpp_tests,
    'plan_summary': plan_summary,
    'audit_plan': audit_plan,
    'dump_code_quality_reference': dump_code_quality_reference,
    'validate_agent_files': validate_agent_files,
    'run_coverage': run_coverage,
    'validate_skill_conventions': validate_skill_conventions,
    'compile_mermaid': compile_mermaid,
    'evt_compile': evt_compile,
    'leak_check': leak_check,
    'check_comment_style': check_comment_style,
    'session_state': session_state,
    'classify_diff': classify_diff,
    'test_timings': test_timings,
    'verify_commit_builds': verify_commit_builds,
    'publish_review_subtask': publish_review_subtask,
}

REGISTRY = {
    name: {
        'callable': module.run,
        'audience': 'dev',
        'help': _help_from_docstring(module),
    }
    for name, module in _MODULES.items()
}


def run(name, argv: list) -> int:
    """Looks up name in REGISTRY and runs it with argv. Returns its exit code.

    name=None means "mr script" was called with no name at all - that's a
    deliberate discovery request, not an error, so it prints the listing
    and returns 0. An unrecognized name also prints the listing, but
    returns 1 - that one really is a mistake.
    """
    if name is None:
        _print_listing()
        return 0

    entry = REGISTRY.get(name)
    if entry is None:
        print(f'Unknown script command: {name}', file=sys.stderr)
        _print_listing()
        return 1
    return entry['callable'](argv)


def _print_listing() -> None:
    if not REGISTRY:
        print('No commands registered yet.', file=sys.stderr)
        return
    print('Available commands:', file=sys.stderr)
    for audience in ('dev', 'user'):
        names = sorted(n for n, e in REGISTRY.items() if e['audience'] == audience)
        if not names:
            continue
        print(f'  {audience}:', file=sys.stderr)
        for n in names:
            print(f"    {n:<20} {REGISTRY[n]['help']}", file=sys.stderr)
    print(file=sys.stderr)
    print("Run mr script <name> --help for one command's usage.", file=sys.stderr)
