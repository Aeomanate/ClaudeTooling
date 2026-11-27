#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""`mr script validate_skill_conventions` - orchestrator skill-tree lint.

Runs 6 fixed checks (heading convention, link convention including link
targets, role file structure, inline-command convention, history-narrative
convention, agent-instructions section format) and assembles one report.
The checks run in an explicit sequence so a renamed or missing check can
no longer silently drop out of the report. Most of these checks also run
scoped to newly inserted text on every Edit/Write via
claude/hooks/check_content.py - this script covers the two that need the
whole file or whole tree: link targets and role file structure.

Lines with `<!-- VALIDATED -->` are known false positives and are excluded
from the history-narrative violation count.

Each check function returns `(lines, issue_count)` - the issue count is
the check's own tally of what it found, never re-derived by scanning the
printed report text for a marker string. A check's report formatting can
change freely without silently breaking the summary count.
"""

import datetime
import glob
import os
import re
import subprocess

from claude.hooks import _checks
from git_hooks_impl.entry_points.commands._shared import project_root

_STRUCTURE_ROLES = (
    'coder', 'fixer', 'plan_writer', 'featurer', 'refactorer', 'tester',
    'gitter', 'drd_writer', 'skill-validation',
)
_AGENT_INSTRUCTIONS_ROLES = (
    'fixer', 'plan_writer', 'featurer', 'refactorer', 'drd_writer', 'skill-validation',
)


def _orch_dir(root: str) -> str:
    """Returns the orchestrator skill directory under the repo root."""
    return os.path.join(root, 'claude', 'skills', 'orchestrator')


def _grep_md(orch: str, pattern: re.Pattern, exclude_substrings: tuple = ()) -> list:
    """Greps every *.md file under orch for pattern. Returns 'rel:line:text' strings.

    exclude_substrings is matched against the full 'rel:line:text' result string,
    mirroring the original `grep -v` piped onto the raw grep -rn output line.
    """
    results = []
    for f in sorted(glob.glob(os.path.join(orch, '**', '*.md'), recursive=True)):
        relpath = os.path.relpath(f, orch).replace(os.sep, '/')
        with open(f, encoding='utf-8', errors='ignore') as fh:
            for lineno, line in enumerate(fh, start=1):
                if not pattern.search(line):
                    continue
                result = f'{relpath}:{lineno}:{line.rstrip(chr(10))}'
                if any(sub in result for sub in exclude_substrings):
                    continue
                results.append(result)
    return results


def _check_headings(root: str) -> tuple:
    """Checks every role workflow.md starts with a `## ` heading. Returns (lines, issues).

    Scoped to roles/*/workflow.md and roles/*/*/workflow.md - role workflow
    files, not shared rule files like shared/rules/workflow.md (which is a
    WF-1..14 rule listing, correctly titled with `# Title` like its
    shared/rules/ siblings, not a role workflow).
    """
    lines = ['### Check: Heading convention', '']
    roles_dir = os.path.join(_orch_dir(root), 'roles')
    issues = 0
    files = sorted(
        f for f in glob.glob(os.path.join(roles_dir, '**', 'workflow.md'), recursive=True)
        if '/roles/skill-validation/' not in f.replace(os.sep, '/')
    )
    for f in files:
        first_heading = None
        with open(f, encoding='utf-8', errors='ignore') as fh:
            for line in fh:
                if line.startswith('#'):
                    first_heading = line.rstrip('\n')
                    break
        if first_heading and not first_heading.startswith('## '):
            lines.append(f'VIOLATION: {f} first heading is not ## (found: {first_heading})')
            issues += 1
    if issues == 0:
        lines.append('  CLEAN: All workflow.md files use correct heading hierarchy')
    return lines, issues


_MD_LINK_RE = re.compile(r'\]\(([^)#]+\.md)(?:#[^)]*)?\)')
_INLINE_CODE_RE = re.compile(r'`[^`]*`')


def _check_link_targets(root: str, orch: str) -> tuple:
    """Checks every relative .md link target exists on disk. Returns (lines, issues)."""
    lines = ['### Check: Link targets exist', '']
    agents_dir = os.path.join(root, 'claude', 'agents')
    scan_dirs = [d for d in (orch, agents_dir) if os.path.isdir(d)]
    issues = 0
    for scan_dir in scan_dirs:
        for f in sorted(glob.glob(os.path.join(scan_dir, '**', '*.md'), recursive=True)):
            relpath = os.path.relpath(f, scan_dir).replace(os.sep, '/')
            with open(f, encoding='utf-8', errors='ignore') as fh:
                file_lines = fh.readlines()
            for lineno, raw in enumerate(file_lines, start=1):
                # Strip inline-code spans first: a link shown as a rule EXAMPLE
                # inside backticks (e.g. DOC-5's `[name](./file.md)`) is prose
                # describing the convention, not a real cross-reference.
                scan_line = _INLINE_CODE_RE.sub('', raw)
                for m in _MD_LINK_RE.finditer(scan_line):
                    target = m.group(1)
                    if target.startswith(('http://', 'https://')):
                        continue
                    target_path = os.path.normpath(os.path.join(os.path.dirname(f), target))
                    if not os.path.isfile(target_path):
                        lines.append(
                            f"  VIOLATION: {relpath}:{lineno}: dangling link target '{target}'"
                        )
                        issues += 1
    lines.append('')
    if issues == 0:
        lines.append('  CLEAN: All relative .md link targets exist')
    return lines, issues


def _check_links(root: str) -> tuple:
    """Checks ../ cross-refs, bare filenames, dangling targets. Returns (lines, issues)."""
    lines = ['### Check: Link convention', '']
    orch = _orch_dir(root)
    issues = 0

    cross_dir_results = _grep_md(
        orch, _checks.CROSS_DIR_LINK_RE,
        exclude_substrings=_checks.CROSS_DIR_LINK_EXEMPT_SUFFIXES,
    )
    if cross_dir_results:
        lines.append('Found ../ cross-references:')
        lines.extend(f'  VIOLATION: {r}' for r in cross_dir_results)
        issues += len(cross_dir_results)
    else:
        lines.append('  CLEAN: No ../ cross-references')

    lines.append('')

    bare_link_results = _grep_md(
        orch, _checks.BARE_LINK_RE,
        exclude_substrings=_checks.BARE_LINK_EXEMPT_SUFFIXES,
    )
    if bare_link_results:
        lines.append('Found bare filename link texts:')
        lines.extend(f'  VIOLATION: {r}' for r in bare_link_results)
        issues += len(bare_link_results)
    else:
        lines.append('  CLEAN: All link texts are descriptive')

    if issues == 0:
        lines.append('  CLEAN: All links follow conventions')

    lines.append('')
    target_lines, target_issues = _check_link_targets(root, orch)
    lines.extend(target_lines)
    issues += target_issues
    return lines, issues


def _check_structure(root: str) -> tuple:
    """Checks every role has rules.md + workflow(s) + agent-instructions. Returns (lines, issues)."""
    lines = ['### Check: Role file structure', '']
    orch = os.path.join(_orch_dir(root), 'roles')
    issues = 0

    for role in _STRUCTURE_ROLES:
        role_dir = os.path.join(orch, role)
        if os.path.isfile(os.path.join(role_dir, 'rules.md')):
            lines.append(f'  OK: {role}/rules.md')
        else:
            lines.append(f'  MISSING: {role}/rules.md')
            issues += 1

        if os.path.isfile(os.path.join(role_dir, 'workflow.md')):
            lines.append(f'  OK: {role}/workflow.md (single workflow)')
        else:
            nested = sorted(
                glob.glob(os.path.join(role_dir, '*', '**', 'workflow.md'), recursive=True),
            )
            if nested:
                for wf in nested:
                    short = os.path.relpath(wf, orch).replace(os.sep, '/')
                    lines.append(f'  OK: {short} (named workflow)')
            else:
                lines.append(f'  MISSING: {role}/workflow.md (no workflows found)')
                issues += 1

    lines.append('')

    for role in _AGENT_INSTRUCTIONS_ROLES:
        agent_dir = os.path.join(orch, role, 'agent-instructions')
        if os.path.isdir(agent_dir):
            count = len(glob.glob(os.path.join(agent_dir, '*.md')))
            lines.append(f'  OK: {role}/agent-instructions/ ({count} files)')
        else:
            lines.append(f'  MISSING: {role}/agent-instructions/')
            issues += 1

    tester_dir = os.path.join(orch, 'tester')
    if os.path.isdir(tester_dir):
        for sub in sorted(os.listdir(tester_dir)):
            sub_path = os.path.join(tester_dir, sub)
            if sub == 'check-tests' or not os.path.isdir(sub_path):
                continue
            agent_dir = os.path.join(sub_path, 'agent-instructions')
            if os.path.isdir(agent_dir):
                count = len(glob.glob(os.path.join(agent_dir, '*.md')))
                lines.append(f'  OK: tester/{sub}/agent-instructions/ ({count} files)')
            else:
                lines.append(f'  MISSING: tester/{sub}/agent-instructions/')
                issues += 1

    if issues == 0:
        lines.append('')
        lines.append('  CLEAN: All roles have required structure')
    return lines, issues


def _check_inline_commands(root: str) -> tuple:
    """Checks ```bash blocks in workflow/rules .md use mr or scripts. Returns (lines, issues)."""
    lines = ['### Check: Inline commands (should be scripts or mr)', '']
    orch = _orch_dir(root)
    issues = 0

    for f in sorted(glob.glob(os.path.join(orch, '**', '*.md'), recursive=True)):
        relpath = os.path.relpath(f, orch).replace(os.sep, '/')
        if 'agent-instructions' in relpath.split('/') or 'patterns' in relpath.split('/'):
            continue
        with open(f, encoding='utf-8', errors='ignore') as fh:
            file_lines = fh.readlines()
        in_block = False
        for lineno, raw in enumerate(file_lines, start=1):
            # lstrip before the fence check: a ```bash fence nested inside a
            # numbered list is indented, and an anchored startswith('```bash')
            # on the un-lstripped line would silently never match it.
            stripped = raw.rstrip('\n')
            fence = stripped.lstrip()
            if fence.startswith('```bash'):
                in_block = True
                continue
            if fence.startswith('```'):
                in_block = False
                continue
            if not in_block:
                continue
            cmd = stripped.strip()
            if not cmd or cmd.startswith('#') or 'VALIDATED' in cmd:
                continue
            if any(allowed.search(cmd) for allowed in _checks.ALLOWED_INLINE_RES):
                continue
            lines.append(f'  VIOLATION: {relpath}:{lineno}: {cmd}')
            issues += 1

    lines.append('')
    if issues == 0:
        lines.append('  CLEAN: All commands use mr or scripts')
    else:
        lines.append(f'  {issues} inline command(s) should be extracted to scripts')
    return lines, issues


def _check_history_narrative(root: str) -> tuple:
    """Checks canonical .md files for STYLE-2 history-narrative pollution. Returns (lines, issues)."""
    orch = _orch_dir(root)
    agents_dir = os.path.join(root, 'claude', 'agents')
    scan_dirs = [d for d in (orch, agents_dir) if os.path.isdir(d)]

    violations = []
    for scan_dir in scan_dirs:
        for pattern in _checks.HISTORY_PATTERNS:
            regex = re.compile(pattern)
            for f in sorted(glob.glob(os.path.join(scan_dir, '**', '*.md'), recursive=True)):
                relpath = os.path.relpath(f, scan_dir).replace(os.sep, '/')
                if scan_dir == orch and _checks.has_suffix(relpath, _checks.HISTORY_EXEMPT_SUFFIXES):
                    continue
                with open(f, encoding='utf-8', errors='ignore') as fh:
                    for lineno, line in enumerate(fh, start=1):
                        if '<!-- VALIDATED -->' in line:
                            continue
                        if regex.search(line):
                            violations.append(f'{f}:{lineno}:{line.rstrip(chr(10))}')

    if violations:
        lines = [
            f'FAIL: {len(violations)} history-narrative violation(s) found in canonical files.',
            '',
            'STYLE-2: skill / rule / agent definition files describe CURRENT state.',
            'History belongs in git log + commit messages + .ai/BRANCH_PLAN.md Decisions Log,',
            'not in the rule text itself.',
            '',
            'Violations:',
        ]
        lines.extend(violations)
        lines.append('')
        return lines, len(violations)

    scanned = sum(len(glob.glob(os.path.join(d, '**', '*.md'), recursive=True)) for d in scan_dirs)
    lines = [f'PASS: No history-narrative violations in {scanned} canonical .md files.',
             'Scanned directories:']
    lines.extend(f'  - {d}' for d in scan_dirs)
    return lines, 0


def _check_agent_instructions(root: str) -> tuple:
    """Checks agent-instructions/*.md files for the 5 standard sections. Returns (lines, issues)."""
    lines = ['### Check: agent-instructions section format', '']
    orch = _orch_dir(root)

    files = sorted(glob.glob(
        os.path.join(orch, '**', 'agent-instructions', '*.md'), recursive=True,
    ))
    issues = 0
    for f in files:
        short = os.path.relpath(f, orch).replace(os.sep, '/')
        with open(f, encoding='utf-8') as fh:
            content = fh.read()
        missing = [s for s in _checks.REQUIRED_AGENT_INSTRUCTION_SECTIONS if f'## {s}' not in content]
        if missing:
            lines.append(f"  VIOLATION: {short} - missing: {' '.join(missing)}")
            issues += 1

    lines.append('')
    if issues == 0:
        lines.append(f'  CLEAN: All {len(files)} agent instructions have 5 standard sections')
    return lines, issues


_CHECKS = (
    _check_headings,
    _check_links,
    _check_structure,
    _check_inline_commands,
    _check_history_narrative,
    _check_agent_instructions,
)


def run(argv: list) -> int:
    """Runs all 6 checks, prints (or writes) the report. Returns 0 if clean, else 1."""
    root = project_root()
    branch = subprocess.check_output(
        ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
        stderr=subprocess.DEVNULL, text=True,
    ).strip()

    report = [
        '# Skill Validation Report',
        f"Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f'Branch: {branch}',
        '',
    ]
    total_violations = 0
    for check in _CHECKS:
        report.append('---')
        report.append('')
        lines, issues = check(root)
        report.extend(lines)
        report.append('')
        total_violations += issues

    report.append('---')
    report.append('')

    report.append('## Summary')
    report.append(f'Total violations: {total_violations}')
    if total_violations == 0:
        report.append('Status: ALL CLEAN')
    else:
        report.append(f'Status: {total_violations} issues found - fix before proceeding')

    report_text = '\n'.join(report)
    output_path = argv[0] if argv else None
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as fh:
            fh.write(report_text + '\n')
        print(f'Report written to: {output_path}')
        print(f'Violations: {total_violations}')
    else:
        print(report_text)

    return 0 if total_violations == 0 else 1
