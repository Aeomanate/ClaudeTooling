#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""evt_compile.py - compile EVT Coverage tables from QA test-case docs.

Canonical QA case format (see docs/EVT-QA-Scenarios/README.md's case
format, or a repo's equivalent index): a heading naming the case,

    ### QA-ID - v1
    #### QA-ID (GATE) - v1
    #### QA-ID - v1 (design not yet on this branch)

followed by a `| Field | Value |` table. Only `Expected` is read out of
it - `Result`/`Dev Result`/`QA Result`/`Note` describe the dev's own
verification and stay in the doc; the compiled sheet ships blank there
for QA to fill in (EVT-2's "ship a template with Results empty").

Every doc compiles to its own CSV, one file per doc - a `<stem>_corner.md`
split out from its base `<stem>.md` (EVT-14) compiles separately, not
merged into the base doc's output. Tier itself is not carried into the
compiled sheet: Core cases already precede Corner cases in doc order
within whichever doc they live in, and the canonical template has no
Tier column to begin with.

Output goes to .ai/evt_compiled/<doc-stem>.csv, one file per doc, with
columns Case Id, Expected, Results, Note - the canonical EVT template's
own three Coverage columns (Expected, Results, Note) plus the one
deviation this project actually needs, Case Id, because its cases moved
to a repo doc the sheet only indexes (EVT-16). Only Case Id/Expected are
filled in; Results/Note ship blank for QA. Ahead of that table, a
Story/Feature-info
header is generated per EVT-2: fields mechanically derivable from the
environment (Story Owner from git config, System info from dxdiag,
Branch/Pipeline and doc links from git, Case set version from the doc's
own case headings, Read this first from the doc's own intro paragraph -
the text between its `# Title` and its first `## ` heading, which by
convention already IS that doc's "read this first" summary and a pointer
to the README) are filled in automatically. Every other header field -
Story/Feature, JIRA Link, Build #, Device(s), Host, Elevation, Select
Degree of Impact, Describe impact - is a human judgment call, never
guessed (EVT-10, REQUIRED_HEADER_FIELDS): each needs its own flag, and
the run fails with a clear error, before writing anything, if one is
missing and this run would generate a fresh header. If a same-named file
already exists under .ai/evt/, its header rows are carried over instead
of generating a fresh one - but EVT-10 still applies to it: any required
field the carried-over header lacks a non-empty value for still needs
its flag this run, or the run fails the same way a fresh header would.
A flag given this run fills only that gap; every other carried-over
value is left untouched.

Run this once per changed doc set, after its cases are finished and
human-approved - never mid-edit, since it has no way to distinguish a
draft case from a finished one. Read-only on the docs; safe to re-run.

Usage:
    mr script evt_compile [TARGET] --story TEXT --jira URL --build TEXT
                           --devices TEXT --host TEXT --elevation TEXT
                           --impact LOW|MEDIUM|HIGH --impact-desc TEXT

TARGET is a QA doc file or a folder of them; defaults to docs/QA/ under
the project root. Omit a flag only when the doc set's existing
`.ai/evt/<stem>.csv` already carries a non-empty value for that field -
otherwise the run fails before writing anything (see above).
"""
import csv
import getpass
import os
import re
import subprocess
import sys
import tempfile

from git_hooks_impl.entry_points.commands._shared import project_root

HELP = """\
mr script evt_compile [TARGET] [OPTIONS]

Regenerates EVT Coverage CSVs from QA test-case docs. TARGET is a single
doc or a folder; defaults to docs/QA/ under the repo root. Output goes to
.ai/evt_compiled/<doc-stem>.csv, one file per doc - a `<stem>_corner.md`
split out from its base `<stem>.md` compiles to its own CSV, not merged.

When to run this: after a QA doc's cases are finished and a human has
reviewed/approved them - not before. This command only reads the doc as
it stands; it has no way to tell a still-being-drafted case apart from a
finished one, so running it mid-edit just compiles a stale or partial
snapshot. Once approved, run it once per changed doc set as the last
step before handing the coverage sheet off (e.g. for upload to the EVT
Drive sheet) - it is read-only on the docs and safe to re-run any number
of times; each run fully overwrites its own .ai/evt_compiled/ output,
nothing else.

Case format expected in the doc (the template for any new case):

    ### QA-ID - v1

    | Field | Value |
    |---|---|
    | Expected | <one-sentence expected outcome> |
    | Dev Result | Pass. <evidence> |
    | QA Result | Not Tested |
    | Note | <current-behavior fact the tester needs, if any> |

Only `Expected` reaches the compiled sheet. `Result`/`Dev Result`/
`QA Result`/`Note` are the dev's own verification record and stay in the
doc - the sheet's Results/Note columns ship blank for QA to fill in.

Required whenever a doc's header (fresh, or an existing
.ai/evt/<stem>.csv's) doesn't already carry a non-empty value for one of
these - the run fails with a clear error before writing anything if any
is still missing after the flags below are applied. If you (or the agent
invoking this) don't already know one of these, ask the developer -
never guess:
  --story TEXT               Story/Feature
  --jira URL                 JIRA Link
  --build TEXT               Build #
  --devices TEXT             Device(s)
  --host TEXT                Host
  --elevation TEXT           Elevation
  --impact LOW|MEDIUM|HIGH   Select Degree of Impact (EVT-7)
  --impact-desc TEXT         Describe impact

A flag is only needed for a field an existing .ai/evt/<stem>.csv doesn't
already have a non-empty value for - every other carried-over value is
left untouched, not overwritten.

Auto-filled without a flag:
  Story Owner        git config user.name, else the user.email local
                      part, else the OS login name.
  System info        A short line from `dxdiag /t`: OS build, system
                      model, display card + resolution, audio device.
                      Blank if dxdiag isn't available or times out.
  Branch/Pipeline     "<repo>: <current branch>", from git.
  Case document /
  Full test flows /
  Glossary link       GitLab blob URLs built from the origin remote,
                      current branch, and doc path.
  Case set version    The version (e.g. "v1") the doc's own case
                      headings declare (EVT-17); "mixed (v1, v2)" if
                      they disagree.
  Read this first     The doc's own intro paragraph(s) - everything
                      between its `# Title` and its first `## ` heading.
                      By convention this is already that doc's onboarding
                      summary and a pointer to README.md (EVT-19).

Output columns: Case Id, Expected, Results, Note - the canonical EVT
template's own Coverage columns (Expected, Results, Note) plus the one
deviation this project needs, Case Id, because its cases moved to a repo
doc the sheet only indexes (EVT-16). Tier is deliberately not a column:
Core cases already precede Corner cases in doc order. Only Case
Id/Expected are filled in; Results and Note ship blank for QA to fill in
when they run the case. If .ai/evt/<stem>.csv already exists, its header
rows (everything before the EVT Coverage table) are reused as a base and
patched with this run's flags wherever a required field's carried-over
value is empty; only the Coverage table itself is always regenerated
fresh from the doc.

Examples:
  mr script evt_compile   # only when every target doc already has a
                           # .ai/evt/<stem>.csv header to carry over
  mr script evt_compile docs/QA/1_lib.md \\
      --story "Include ETW lib into Updater with fallbacks" \\
      --jira https://jira.companyname.io/browse/PROJECTNAME-53721 \\
      --build "https://gitlab.../pipelines/12345" \\
      --devices "any device" --host "console mode, direct" \\
      --elevation "Administrator PowerShell at the repository root" \\
      --impact HIGH --impact-desc "..."

Exit code: 0 on success, 1 if TARGET does not exist, no docs are found,
or a required header field is missing (no flag given, and no existing
.ai/evt/<stem>.csv value to fall back on) for some doc.
"""

HEADER = ['Case Id', 'Expected', 'Results', 'Note']

# The header fields that are a human/AI judgment call, never derivable
# from git or dxdiag and never guessed (EVT-10): each needs its own flag
# whenever the doc's header (fresh, or an existing .ai/evt/<stem>.csv's)
# doesn't already carry a non-empty value for it - the run fails loudly
# rather than shipping the sheet with a silently blank or stale cell.
# (flag, opts key, header label) - the single source of truth
# _parse_args, _default_header_rows, _reconcile_header, and the
# pre-flight check in run() all read from.
REQUIRED_HEADER_FIELDS = [
    ('--story', 'story', 'Story/Feature'),
    ('--jira', 'jira', 'JIRA Link'),
    ('--build', 'build', 'Build #'),
    ('--devices', 'devices', 'Device(s)'),
    ('--host', 'host', 'Host'),
    ('--elevation', 'elevation', 'Elevation'),
    ('--impact', 'impact', 'Select Degree of Impact'),
    ('--impact-desc', 'impact_desc', 'Describe impact'),
]

# Which of the header's three sections each required field belongs to -
# _reconcile_header uses this to know where to insert a new row when an
# existing header is missing one of these entirely (not just blank).
_FIELD_SECTION = {
    'story': 'Story/Feature info',
    'jira': 'Story/Feature info',
    'build': 'Build & Test environment Info',
    'devices': 'Build & Test environment Info',
    'host': 'Build & Test environment Info',
    'elevation': 'Build & Test environment Info',
    'impact': 'Change Impact Assessment',
    'impact_desc': 'Change Impact Assessment',
}

# Case headings separate the id from "vN" with a hyphen or a dash; built
# from chr() rather than literal dash characters, so the em-dash auto-fix
# hook has nothing in this file to mangle.
_DASH_CLASS = '[-' + chr(0x2013) + chr(0x2014) + ']'
_CASE_HEADING_RE = re.compile(
    r'^#{2,6}\s+(QA-[A-Za-z0-9_-]+)\s*((?:\([^)]*\)\s*)*)' + _DASH_CLASS
    + r'\s*v(\d+)\s*((?:\([^)]*\)\s*)*)$'
)
_H1_RE = re.compile(r'^#\s+.+$')
_ANY_H2_RE = re.compile(r'^##\s+')
_TABLE_HEADER_RE = re.compile(r'^\|\s*Field\s*\|\s*Value\s*\|\s*$', re.IGNORECASE)
_TABLE_SEP_RE = re.compile(r'^\|[\s:-]+\|[\s:-]+\|\s*$')

_DXDIAG_OS_RE = re.compile(r'^\s*Operating System:\s*(.+)$', re.MULTILINE)
_DXDIAG_MODEL_RE = re.compile(r'^\s*System Model:\s*(.+)$', re.MULTILINE)
_DXDIAG_CARD_RE = re.compile(r'^\s*Card name:\s*(.+)$', re.MULTILINE)
_DXDIAG_MODE_RE = re.compile(r'^\s*Current Mode:\s*(.+)$', re.MULTILINE)
_DXDIAG_SOUND_RE = re.compile(r'^Sound Devices\s*\n-+\s*\n\s*Description:\s*(.+)$', re.MULTILINE)


# ---------------------------------------------------------------------------
# Case parsing
# ---------------------------------------------------------------------------

def _parse_table_row(line):
    """Splits a `| Field | Value |` row into (field, value), or None if malformed.

    Only the first remaining `|` after the outer pipes is treated as the
    field/value boundary, so a Value cell containing further `|` characters
    (a PowerShell pipe, an inline table) survives intact.
    """
    s = line.strip()
    if not s.startswith('|'):
        return None
    inner = s[1:]
    if inner.endswith('|'):
        inner = inner[:-1]
    if '|' not in inner:
        return None
    field, value = inner.split('|', 1)
    return field.strip(), value.strip()


def _parse_case_table(lines, start):
    """Parses the `| Field | Value |` table starting at or after index start.

    Returns (fields, next_index) where fields maps field name to a list of
    values (a field may repeat, e.g. multiple Note rows). Stops at the next
    heading, `---` separator, or blank line following the table.
    """
    i = start
    n = len(lines)
    while i < n:
        stripped = lines[i].strip()
        if stripped.startswith('#') or stripped == '---':
            return {}, i
        if _TABLE_HEADER_RE.match(stripped):
            break
        i += 1
    else:
        return {}, i

    i += 1
    if i < n and _TABLE_SEP_RE.match(lines[i].strip()):
        i += 1

    fields = {}
    while i < n and lines[i].strip().startswith('|'):
        parsed = _parse_table_row(lines[i])
        if parsed:
            key, value = parsed
            fields.setdefault(key, []).append(value)
        i += 1

    return fields, i


def parse_doc(text):
    """Returns a list of case dicts (id, expected, version), in doc order.

    Only the case id, Expected text, and case-set version are pulled out
    of the doc - Result/Dev Result/QA Result/Note are the dev's own
    verification record and stay in the doc; the compiled sheet ships
    blank there for QA. Tier (EVT-14) is not carried into the compiled
    sheet at all - Core cases already precede Corner cases in doc order,
    so the sheet's own row order already reflects it; a Case Id column is
    the one deviation from the canonical template this project actually
    needs (EVT-24), and no more.
    """
    lines = text.splitlines()
    cases = []
    i = 0
    n = len(lines)

    while i < n:
        heading_match = _CASE_HEADING_RE.match(lines[i].strip())
        if heading_match:
            case_id = heading_match.group(1)
            version = 'v' + heading_match.group(3)
            fields, i = _parse_case_table(lines, i + 1)
            expected = fields.get('Expected', [''])[0]
            cases.append({'id': case_id, 'expected': expected, 'version': version})
            continue

        i += 1

    return cases


def _rows_for_doc(cases):
    return [[c['id'], c['expected'], '', ''] for c in cases]


def _extract_intro(text):
    """Returns the doc's own intro: everything between its `# Title` line and
    its first `## ` heading. By convention every doc in this format opens
    with exactly this - a short "read this first" summary plus a pointer
    to the shared README - so it needs no separate authoring or flag."""
    lines = text.splitlines()
    start = 0
    for i, line in enumerate(lines):
        if _H1_RE.match(line):
            start = i + 1
            break

    end = len(lines)
    for i in range(start, len(lines)):
        if _ANY_H2_RE.match(lines[i]):
            end = i
            break

    intro_lines = lines[start:end]
    while intro_lines and not intro_lines[0].strip():
        intro_lines.pop(0)
    while intro_lines and not intro_lines[-1].strip():
        intro_lines.pop()
    return '\n'.join(intro_lines).strip()


# ---------------------------------------------------------------------------
# Header generation - EVT-2's five sections, auto-filled where derivable
# ---------------------------------------------------------------------------

def _run_capture(cmd, timeout=None):
    try:
        return subprocess.check_output(
            cmd, stderr=subprocess.DEVNULL, text=True, timeout=timeout,
        ).strip()
    except Exception:
        return ''


def _story_owner(root):
    name = _run_capture(['git', '-C', root, 'config', 'user.name'])
    if name:
        return name
    email = _run_capture(['git', '-C', root, 'config', 'user.email'])
    if email:
        return email.split('@')[0]
    try:
        return getpass.getuser()
    except Exception:
        return ''


def _current_branch(root):
    return _run_capture(['git', '-C', root, 'branch', '--show-current'])


def _gitlab_project_url(root):
    remote = _run_capture(['git', '-C', root, 'remote', 'get-url', 'origin'])
    if not remote:
        return ''
    remote = remote[:-4] if remote.endswith('.git') else remote
    if remote.startswith('git@'):
        host_and_path = remote[len('git@'):].replace(':', '/', 1)
        remote = 'https://' + host_and_path
    return remote


def _dxdiag_summary(timeout=25):
    """Returns a short one-line system summary from `dxdiag /t`, or '' on failure."""
    if sys.platform != 'win32':
        return ''
    fd, path = tempfile.mkstemp(suffix='.txt', prefix='evt_compile_dxdiag_')
    os.close(fd)
    try:
        subprocess.run(['dxdiag', '/t', path], timeout=timeout, check=False)
        with open(path, encoding='utf-8', errors='ignore') as f:
            text = f.read()
    except Exception:
        return ''
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

    if not text.strip():
        return ''

    parts = []
    m = _DXDIAG_OS_RE.search(text)
    if m:
        parts.append(m.group(1).strip())
    m = _DXDIAG_MODEL_RE.search(text)
    if m:
        parts.append(m.group(1).strip())
    card = _DXDIAG_CARD_RE.search(text)
    mode = _DXDIAG_MODE_RE.search(text)
    if card:
        display = card.group(1).strip()
        if mode:
            display += f', {mode.group(1).strip()}'
        parts.append('Display: ' + display)
    sound = _DXDIAG_SOUND_RE.search(text)
    if sound:
        parts.append('Audio: ' + sound.group(1).strip())

    # A real newline, not "\n" the two characters - csv.writer quotes a
    # field containing one automatically, and Sheets renders it as a
    # wrapped multi-line cell (EVT-20: a real line break, never a literal
    # backslash-n, belongs in a CSV cell).
    return '\n'.join(parts)


class _RunContext:
    """Everything one `run()` invocation needs that doesn't vary per doc group:
    the repo root, parsed --flags, output/source directories, and the
    machine/repo-wide values (git config, dxdiag) a header can draw on.

    The latter are computed at most once, on first use, and cached here -
    a folder of N docs must not re-run `dxdiag` (which takes real
    wall-clock time) or re-shell out to git N times for the same answer.
    """

    def __init__(self, root, opts):
        self.root = root
        self.opts = opts
        self.out_dir = os.path.join(root, '.ai', 'evt_compiled')
        self.evt_dir = os.path.join(root, '.ai', 'evt')
        self._branch = None
        self._project_url = None
        self._story_owner = None
        self._system_info = None

    @property
    def branch(self):
        if self._branch is None:
            self._branch = _current_branch(self.root)
        return self._branch

    @property
    def project_url(self):
        if self._project_url is None:
            self._project_url = _gitlab_project_url(self.root)
        return self._project_url

    @property
    def story_owner(self):
        if self._story_owner is None:
            self._story_owner = _story_owner(self.root)
        return self._story_owner

    @property
    def system_info(self):
        if self._system_info is None:
            self._system_info = _dxdiag_summary()
        return self._system_info


def _default_header_rows(doc_path, ctx, case_version, intro):
    """Builds the EVT-2 five-section header, filling in what's derivable and
    leaving the rest blank rather than guessing (EVT-10).

    Genuinely per-run/human fields - Build #, Device(s), Host, Elevation,
    Select Degree of Impact/Describe impact without a flag - stay blank
    on purpose: none of them are derivable from git or dxdiag, and
    borrowing one case's own Preconditions text to speak for the whole
    story would misrepresent every other case.
    """
    branch = ctx.branch
    project_url = ctx.project_url
    # The GitLab project path, not the local worktree directory name - a
    # worktree checkout (e.g. "reponame_etw-qa-fix") would otherwise leak its
    # own folder name into the generated links and Branch/Pipeline text.
    repo_name = project_url.rstrip('/').rsplit('/', 1)[-1] if project_url else os.path.basename(ctx.root)
    rel_doc_path = os.path.relpath(doc_path, ctx.root).replace(os.sep, '/')
    readme_path = os.path.join(os.path.dirname(doc_path), 'README.md')
    rel_readme_path = os.path.relpath(readme_path, ctx.root).replace(os.sep, '/')

    def blob_url(rel_path):
        if not project_url or not branch:
            return ''
        return f'{project_url}/-/blob/{branch}/{rel_path}'

    def row(*cells):
        return list(cells) + [''] * (7 - len(cells))

    opts = ctx.opts
    return [
        row('Story/Feature info'),
        row('Story/Feature', opts.get('story', '')),
        row('Story Owner', ctx.story_owner),
        row('JIRA Link', opts.get('jira', '')),
        row(),
        row('Build & Test environment Info'),
        row('Build #', opts.get('build', '')),
        row('Branch/Pipeline', f'{repo_name}: {branch}' if branch else ''),
        row('System info', ctx.system_info),
        row('Device(s)', opts.get('devices', '')),
        row('Host', opts.get('host', '')),
        row('Elevation', opts.get('elevation', '')),
        row(),
        row('Change Impact Assessment'),
        row('Select Degree of Impact', opts.get('impact', '')),
        row('Describe impact', opts.get('impact_desc', '')),
        row(),
        row('Additional Info'),
        row('Full test flows',
            f'{rel_doc_path} in the {repo_name} repo. Each Case Id below is a heading in that file.'),
        row('Case document', blob_url(rel_doc_path)),
        row('Glossary and setup commands', blob_url(rel_readme_path)),
        row('Case set version', case_version),
        row('Read this first', intro),
        row(),
    ]


def _existing_header_rows(evt_dir, stem):
    """Returns the header rows of .ai/evt/<stem>.csv up to (not including) its
    own Coverage column-header row, or None if no such file exists."""
    path = os.path.join(evt_dir, stem + '.csv')
    if not os.path.isfile(path):
        return None
    with open(path, newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))
    for idx, row in enumerate(rows):
        if row and row[0] == 'Case Id':
            return rows[:idx]
    return rows


def _find_label_row(rows, label):
    for i, row in enumerate(rows):
        if row and row[0] == label:
            return i
    return None


def _find_section_insert_point(rows, section_label):
    """Index to insert a new row at: right after the last non-blank row of
    'section_label's section, before its trailing blank separator row. Falls
    back to the end of 'rows' if the section itself isn't present."""
    start = _find_label_row(rows, section_label)
    if start is None:
        return len(rows)
    i = start + 1
    while i < len(rows) and rows[i] and rows[i][0]:
        i += 1
    return i


def _reconcile_header(header_rows, opts):
    """Ensures every REQUIRED_HEADER_FIELDS label has a non-empty value,
    filling gaps from opts and reporting any that remain unfillable (EVT-10:
    never guessed, and never silently left blank or stale).

    Used both for a carried-over .ai/evt/<stem>.csv header (patching only
    the fields it's missing, leaving every other carried-over value as-is)
    and, with an empty header_rows, for computing which flags a fresh doc
    still needs.

    Returns (updated_rows, missing_labels) - a copy of header_rows with
    gaps filled from opts where possible, and the labels that could not be
    filled because neither the existing header nor opts had a value.
    """
    rows = [list(r) for r in header_rows]
    missing = []
    for flag, key, label in REQUIRED_HEADER_FIELDS:
        idx = _find_label_row(rows, label)
        existing_value = rows[idx][1] if idx is not None and len(rows[idx]) > 1 else ''
        if existing_value:
            continue
        value = opts.get(key, '')
        if not value:
            missing.append(label)
            continue
        if idx is not None:
            rows[idx][1] = value
        else:
            insert_at = _find_section_insert_point(rows, _FIELD_SECTION[key])
            rows.insert(insert_at, [label, value, '', '', '', '', ''])
    return rows, missing


def _case_set_version(cases):
    """Returns the case set's edition version (EVT-17): the version most of
    its cases declare, or "mixed (v1, v2)" if they disagree, or '' if none
    were parsed at all."""
    versions = [c['version'] for c in cases if c.get('version')]
    if not versions:
        return ''
    distinct = sorted(set(versions), key=lambda v: int(v[1:]))
    if len(distinct) == 1:
        return distinct[0]
    return 'mixed (' + ', '.join(distinct) + ')'


def _compile_doc(doc_path, ctx):
    stem = os.path.splitext(os.path.basename(doc_path))[0]
    with open(doc_path, encoding='utf-8') as f:
        text = f.read()
    cases = parse_doc(text)

    header_rows = _existing_header_rows(ctx.evt_dir, stem)
    if header_rows is None:
        header_rows = _default_header_rows(
            doc_path, ctx, _case_set_version(cases), _extract_intro(text),
        )
    else:
        header_rows, _ = _reconcile_header(header_rows, ctx.opts)

    out_path = os.path.join(ctx.out_dir, stem + '.csv')
    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerows(header_rows)
        writer.writerow(HEADER)
        writer.writerows(_rows_for_doc(cases))

    return out_path, len(cases)


def _collect_docs(target):
    if os.path.isfile(target):
        return [target]
    if os.path.isdir(target):
        return sorted(
            os.path.join(target, name)
            for name in os.listdir(target)
            if name.endswith('.md') and name.lower() != 'readme.md'
        )
    return []


def _parse_args(argv):
    opts = {}
    positional = []
    flags = {flag: key for flag, key, _ in REQUIRED_HEADER_FIELDS}
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in flags:
            i += 1
            opts[flags[arg]] = argv[i] if i < len(argv) else ''
        else:
            positional.append(arg)
        i += 1
    return positional, opts


def run(argv: list) -> int:
    """Regenerates EVT Coverage CSVs from QA test-case docs under .ai/evt_compiled/."""
    if argv and argv[0] in ('--help', '-h'):
        print(HELP)
        return 0

    positional, opts = _parse_args(argv)

    root = project_root()
    target = os.path.join(root, positional[0]) if positional else os.path.join(root, 'docs', 'QA')

    if not os.path.exists(target):
        print(f'ERR: {target} not found')
        return 1

    docs = _collect_docs(target)
    if not docs:
        print(f'ERR: no QA docs found under {target}')
        return 1

    ctx = _RunContext(root, opts)

    # Every REQUIRED_HEADER_FIELDS entry is a human/AI judgment call, never
    # a guess (EVT-10) - required whenever a doc's header, fresh or carried
    # over from an existing .ai/evt/<stem>.csv, doesn't already have a
    # non-empty value for it. An agent invoking this command that doesn't
    # already know one of these must ask the developer for it first, not
    # fabricate a value or leave it blank.
    gaps = {}
    for doc_path in docs:
        stem = os.path.splitext(os.path.basename(doc_path))[0]
        existing = _existing_header_rows(ctx.evt_dir, stem) or []
        _, missing = _reconcile_header(existing, opts)
        if missing:
            gaps[stem] = missing
    if gaps:
        for stem, missing in gaps.items():
            print(f'ERR: {stem} is missing required header field(s): {", ".join(missing)}. '
                  f'Pass the matching flag(s) (see --help) - ask the developer for whatever '
                  f'you do not already know, never guess.')
        return 1

    os.makedirs(ctx.out_dir, exist_ok=True)

    for doc_path in docs:
        out_path, count = _compile_doc(doc_path, ctx)
        rel = os.path.relpath(out_path, root)
        print(f'{rel}: {count} cases')

    return 0
