#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""`mr script compile_mermaid` — syntax-validates mermaid blocks in a markdown doc.

Extracts every fenced ```mermaid code block from a markdown document and
validates its syntax with `mermaid.parse()` run under jsdom. Prints
per-block PASS/SKIP with the source line range. Callers: drd-writer,
plan-writer, futurespec-writer, or any persistent sub-agent that just
edited a mermaid block and wants a syntax check.

Usage:
    mr script compile_mermaid <doc.md>
    mr script compile_mermaid        # auto-detect: single *.md under
                                      # $SW_ARCH_DRD_REPO/approved/

This tool does NOT launch mmdc/Puppeteer/headless Chrome, or any browser
of any kind — that behavior was removed on direct developer instruction.
Validation instead runs `mermaid.parse()` (the real mermaid package) under
jsdom, a pure-JS DOM implementation with no rendering engine and no
sandboxing - not Puppeteer/Playwright/Chromium/Firefox/WebKit. Only the
parse/AST-build phase runs; `mermaid.render()` (which additionally needs
real layout measurement) is never called. See _mermaid_validator/validate.mjs.

A block that fails to parse (real syntax error, or any other validator
failure) is reported as SKIP rather than FAIL: this is a best-effort check,
not a gate. The block's own error output is printed inline in the report —
never blocks the caller, never exits non-zero for a block-level failure.
Only setup problems (doc not found, node/npm missing, npm install failure,
unterminated block) return non-zero. Node deps (mermaid, jsdom) are
installed lazily into _mermaid_validator/node_modules on first use.
"""

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

HELP = """\
mr script compile_mermaid <doc.md>
mr script compile_mermaid

Validates every ```mermaid block in a markdown doc with mermaid.parse()
run under jsdom (no browser - see module docstring), and prints PASS or
SKIP per block with its source line range. A block that fails to parse is
SKIPped, not treated as a gate failure — its error is printed inline.

Examples:
  mr script compile_mermaid path/to/design.md
  mr script compile_mermaid    # auto-detects the single *.md under
                                # $SW_ARCH_DRD_REPO/approved/

On PASS/SKIP the block's temp .mmd file is deleted; on SKIP the error is
also printed inline, in full, in the report.

Exit code: 0 unless a setup error prevents validating at all (2: doc not
found, node/npm missing, npm install failure; 3: unterminated block). A
block-level parse failure never affects the exit code.
"""

_VALIDATOR_DIR = Path(__file__).parent / '_mermaid_validator'
_VALIDATOR_SCRIPT = _VALIDATOR_DIR / 'validate.mjs'

_MERMAID_OPEN_RE = re.compile(r'^```mermaid[ \t]*$')
_FENCE_CLOSE_RE = re.compile(r'^```[ \t]*$')
_ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')


def _resolve_doc(argv: list, lines: list) -> Path:
    """Returns the doc path from argv[0], or auto-detects under $SW_ARCH_DRD_REPO/approved/.

    Appends an error message to lines and returns None on any resolution failure.
    """
    if argv and argv[0]:
        return Path(argv[0])

    repo = os.environ.get('SW_ARCH_DRD_REPO')
    if not repo:
        lines.append('ERROR: no doc arg passed and $SW_ARCH_DRD_REPO env var not set.')
        lines.append('Usage: mr script compile_mermaid <doc.md>')
        lines.append('  OR set SW_ARCH_DRD_REPO env var and re-run with no args.')
        return None
    approved = Path(repo) / 'approved'
    if not approved.is_dir():
        lines.append(f'ERROR: no doc arg passed and {approved} not found.')
        lines.append('Usage: mr script compile_mermaid <doc.md>')
        return None
    matches = sorted(approved.glob('*.md'))
    if not matches:
        lines.append(f'ERROR: no *.md found in {approved}')
        return None
    if len(matches) > 1:
        lines.append(f'ERROR: multiple *.md found in {approved} — pass explicit path.')
        for match in matches:
            lines.append(f'  {match}')
        return None
    return matches[0]


def _extract_blocks(doc: Path, tmpdir: Path, lines: list) -> list:
    """Extracts mermaid blocks from doc, writing each body to tmpdir/block-N.mmd.

    Returns a list of (index, start_line, end_line) tuples, or None (after
    appending a WARN to lines) if a block is left unterminated.
    """
    doc_lines = doc.read_text(encoding='utf-8').splitlines()
    blocks = []
    in_block = False
    idx = 0
    start_line = None
    body = []
    for lineno, line in enumerate(doc_lines, start=1):
        if not in_block and _MERMAID_OPEN_RE.match(line):
            in_block = True
            idx += 1
            start_line = lineno + 1
            body = []
            continue
        if in_block and _FENCE_CLOSE_RE.match(line):
            end_line = lineno - 1
            content = '\n'.join(body) + ('\n' if body else '')
            (tmpdir / f'block-{idx}.mmd').write_text(content, encoding='utf-8')
            blocks.append((idx, start_line, end_line))
            in_block = False
            continue
        if in_block:
            body.append(line)

    if in_block:
        lines.append(f'WARN: unterminated mermaid block starting at line {start_line}')
        return None
    return blocks


def _ensure_validator_deps(npm_path: str, lines: list) -> bool:
    """Installs mermaid+jsdom into _mermaid_validator/node_modules if not already present.

    Returns True if the deps are ready to use, False (after appending an
    ERROR to lines) if the install failed.
    """
    if (_VALIDATOR_DIR / 'node_modules' / 'mermaid').is_dir() and \
       (_VALIDATOR_DIR / 'node_modules' / 'jsdom').is_dir():
        return True

    lines.append('Installing mermaid+jsdom into _mermaid_validator/node_modules (one-time)...')
    result = subprocess.run(
        [npm_path, 'install', '--no-audit', '--no-fund'],
        cwd=str(_VALIDATOR_DIR), capture_output=True, text=True, shell=True,
    )
    if result.returncode != 0:
        lines.append('ERROR: npm install failed for the mermaid validator:')
        for line in _ANSI_RE.sub('', result.stderr).splitlines()[:10]:
            lines.append(f'  {line}')
        return False
    return True


def _validate_block(idx: int, start: int, end: int, tmpdir: Path, node_path: str,
                     lines: list) -> bool:
    """Validates one block's syntax via validate.mjs. Appends PASS/SKIP to lines.

    Returns True on PASS. A parse failure is never treated as a gate
    failure - it's reported as SKIP with the error inline, and the caller
    continues. Only PASS/SKIP counts feed the trailer; SKIP never flips the
    overall exit code.
    """
    mmd = tmpdir / f'block-{idx}.mmd'
    result = subprocess.run(
        [node_path, str(_VALIDATOR_SCRIPT), str(mmd)],
        capture_output=True, text=True, shell=True,
    )

    if result.returncode == 0 and 'VALID' in result.stdout:
        lines.append(f'Block {idx} (lines {start}-{end}): PASS')
        mmd.unlink()
        return True

    lines.append(f'Block {idx} (lines {start}-{end}): SKIP (parse failed)')
    lines.append('  error:')
    stderr = _ANSI_RE.sub('', result.stderr).strip()
    for line in (stderr.splitlines() if stderr else ['(no error output)']):
        lines.append(f'    {line}')
    lines.append(f'  .mmd kept for diagnosis: {mmd}')
    return False


def compile_report(argv: list) -> tuple:
    """Validates every mermaid block in the given doc. See module docstring.

    Returns (exit_code, report_text) instead of printing — report_text is
    every line run() would otherwise print, joined with newlines.
    """
    lines = []
    doc = _resolve_doc(argv, lines)
    if doc is None:
        return 2, '\n'.join(lines)
    if not doc.is_file():
        lines.append(f'ERROR: doc not found: {doc}')
        return 2, '\n'.join(lines)

    lines.append(f'Doc: {doc}')

    node_path = shutil.which('node')
    npm_path = shutil.which('npm')
    if node_path is None or npm_path is None:
        lines.append('ERROR: node/npm not found on PATH (need Node.js).')
        return 2, '\n'.join(lines)

    if not _ensure_validator_deps(npm_path, lines):
        return 2, '\n'.join(lines)

    tmpdir = Path(tempfile.mkdtemp())
    lines.append(f'Workdir: {tmpdir}')

    blocks = _extract_blocks(doc, tmpdir, lines)
    if blocks is None:
        return 3, '\n'.join(lines)

    lines.append(f'Found {len(blocks)} mermaid block(s).')
    if not blocks:
        lines.append('Nothing to validate.')
        shutil.rmtree(tmpdir, ignore_errors=True)
        return 0, '\n'.join(lines)

    pass_count = 0
    skip_count = 0
    for idx, start, end in blocks:
        if _validate_block(idx, start, end, tmpdir, node_path, lines):
            pass_count += 1
        else:
            skip_count += 1

    if skip_count == 0:
        lines.append(f'All {pass_count} blocks PASS.')
        shutil.rmtree(tmpdir, ignore_errors=True)
        return 0, '\n'.join(lines)

    lines.append(f'{skip_count} of {len(blocks)} blocks SKIPPED (parse failed, see inline errors above). PASS={pass_count}.')
    lines.append(f'Skipped-block .mmd kept under: {tmpdir}')
    return 0, '\n'.join(lines)


def run(argv: list) -> int:
    """Extracts and reports every mermaid block in the given doc. See module docstring."""
    if argv and argv[0] in ('--help', '-h'):
        print(HELP)
        return 0

    exit_code, report_text = compile_report(argv)
    print(report_text)
    return exit_code
