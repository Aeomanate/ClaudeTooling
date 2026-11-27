#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""publish_review_subtask.py - publish one review-segmentation segment as a Jira sub-task.

Reads a segment file written by the dev-review-writer role (under
.ai/human-review-segmentation/ in the calling repo) and turns it into a
Jira Sub-task under a parent story. Two-phase, split so a human or an
agent can look at exactly what will be sent before it goes out:

  build   - parses the segment file, writes .ai/temp/review_subtasks/<stem>/
            {description.md, acceptance_criteria.md, meta.json} - no
            network call. Skips re-parsing if that folder already exists,
            so a hand-edit (e.g. adding cross-segment context the parser
            cannot infer) survives until --force says otherwise.
  publish - reads those three files back and creates the sub-task, or
            updates it if meta.json already carries a jira_key from an
            earlier publish.

Conversion from the segment's own prose into Jira wiki markup:
  - `code` spans become {{code}} (Jira's monospace token). A literal
    backtick sent as-is renders as a literal backtick in Jira, not as
    code - only {{...}} produces the ADF `code` mark.
  - `## ` / `### ` headings become `h2. ` / `h3. `.
  - `- ` bullets become `* `; `1. ` numbered items become `# `.
  - `**bold**` becomes `*bold*` (Jira's single-asterisk bold).
  - Each hard-wrapped prose paragraph (the segment files wrap at ~80
    columns) is rejoined onto one line. Jira treats every newline as a
    paragraph break, so sending the wrapped source as-is turns each
    wrapped line into its own paragraph with a visible gap - list items,
    headings and checklist lines are already one physical line each in
    these files and are left alone.
  - The segment's "## Reviewer checklist" section is not sent to the
    Description at all - it becomes the sub-task's Acceptance Criteria
    field. That field is a plain multi-line textarea with no markup
    engine and no interactivity: Jira's only real (clickable) checkbox
    is an ADF action-item list, which exists solely inside the
    Description's rich-text document, not in a custom text field. So
    this checklist is bare text wherever it ends up; moving it to
    Acceptance Criteria trades away the small chance of a real checkbox
    for keeping the Description focused on findings.

Estimation is never guessed, the same rule evt_compile applies to its
required header fields: pass --estimate yourself. Rule of thumb - 3 days
minimum; 5 days if the segment needs roughly double the context of a
typical one (its LOC/file count); 2 weeks if it requires understanding
reponame's parts or Windows service internals.
reponame's parts or Windows service internals.

A second pair of actions, `story build` / `story publish`, does the same
two-phase thing for the readme's own remainder: the content that names no
single segment (scope table, merge order, priority rubric, cross-cutting
items, the verified-no-action list, any merge-readiness verdict) and so
has nowhere to live in a per-segment sub-task. It replaces the parent
story's own Description field - once, after the segment sub-tasks exist,
never duplicated into any of them. Markdown pipe tables convert to Jira's
`||header||` / `|cell|` table syntax.

Usage:
    mr script publish_review_subtask build <segment-file> --parent KEY
        --estimate 3d|5d|2w [--assignee EMAIL]
    mr script publish_review_subtask publish <segment-file> [--force]
    mr script publish_review_subtask story build [readme-file] --parent KEY
    mr script publish_review_subtask story publish

<segment-file> and [readme-file] are repo-relative, e.g.
.ai/human-review-segmentation/segment-1-etw-core-lifecycle.md and
.ai/human-review-segmentation/readme.md (the default if omitted).

Requires JIRA_API_TOKEN in the environment, and jira-cli's own
~/.config/.jira/.config.yml for the server URL and login (the same file
`jira init` writes - only `server:` and `login:` are read here).
"""

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

from git_hooks_impl.entry_points.commands._shared import project_root

HELP = __doc__

_HEADER_LINE_RE = re.compile(r'^\*\*Priority:\*\*.*\*\*LOC:\*\*.*$', re.MULTILINE)
_HEADER_FIELD_RE = re.compile(r'\*\*([\w\s]+):\*\*\s*(.+)')
_HEADER_SEP_RE = re.compile(r'[·•]')
_TITLE_RE = re.compile(r'^#\s+Segment\s+\d+:\s*(.+)$', re.MULTILINE)
_SEGMENT_NUM_RE = re.compile(r'segment-(\d+)-', re.IGNORECASE)
_CHECKLIST_ITEM_RE = re.compile(r'^-\s*\[\s*\]\s*(.+)$')
_CODE_SPAN_RE = re.compile(r'`([^`\n]+)`')
_BOLD_RE = re.compile(r'\*\*([^*\n]+)\*\*')
_BULLET_RE = re.compile(r'^-\s+')
_NUMBERED_RE = re.compile(r'^\d+\.\s+')
_H2_RE = re.compile(r'^##\s+')
_H3_RE = re.compile(r'^###\s+')
_HARD_MARKER_RE = re.compile(r'^(#{1,6}\s|\-\s|\*\s|\d+\.\s)')
_PARA_MARKER_RE = re.compile(r'^\*\*[^*\n]+:\*\*')

VALID_ESTIMATES = {'3d', '5d', '1w', '2w'}
SUBTASK_ISSUETYPE_ID = '10144'
ACCEPTANCE_CRITERIA_FIELD = 'customfield_10195'


# ---------------------------------------------------------------------------
# Segment parsing
# ---------------------------------------------------------------------------

def _find_section(text, heading):
    """Returns the body text between a `## heading` (or `### heading`) line
    and the next heading of the same or higher level, or None if heading
    is not present."""
    lines = text.splitlines()
    start = None
    heading_level = None
    for i, line in enumerate(lines):
        m = re.match(r'^(#{2,3})\s+' + re.escape(heading) + r'\s*$', line)
        if m:
            start = i + 1
            heading_level = len(m.group(1))
            break
    if start is None:
        return None

    stop_re = re.compile(r'^#{1,' + str(heading_level) + r'}\s+')
    end = len(lines)
    for i in range(start, len(lines)):
        if stop_re.match(lines[i]):
            end = i
            break
    return '\n'.join(lines[start:end]).strip('\n')


def _reflow(text):
    """Rejoins hard-wrapped prose lines into one line per paragraph.

    Two kinds of line start a fresh paragraph: a heading/bullet/numbered
    item (always one physical line already in these files, so it is
    emitted as-is and never absorbs what follows), and a bold label line
    like `**Recommendation:**`/`**Test:**` (the start of a wrapped
    paragraph that shares no blank line with its neighbour, so it DOES
    absorb the wrapped continuation lines that follow it, up to the next
    marker or blank line). Blank lines are preserved as paragraph
    separators.
    """
    out_lines = []
    buf = []

    def flush():
        if buf:
            out_lines.append(' '.join(buf))
            buf.clear()

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            flush()
            out_lines.append('')
        elif _HARD_MARKER_RE.match(stripped):
            flush()
            out_lines.append(stripped)
        elif _PARA_MARKER_RE.match(stripped):
            flush()
            buf.append(stripped)
        else:
            buf.append(stripped)
    flush()
    return '\n'.join(out_lines)


def _to_wiki_markup(text):
    """Converts this project's segment-file markdown dialect to Jira wiki
    markup. Order matters: bold before bullets, since both use `*` but in
    different positions, and code spans first so a code span's own text
    (e.g. a `**` that is never actually inside one here) is never re-read
    by the bold pass."""
    text = _CODE_SPAN_RE.sub(r'{{\1}}', text)
    text = _BOLD_RE.sub(r'*\1*', text)

    out = []
    for line in text.splitlines():
        if _H2_RE.match(line):
            out.append('h2. ' + _H2_RE.sub('', line))
        elif _H3_RE.match(line):
            out.append('h3. ' + _H3_RE.sub('', line))
        elif _BULLET_RE.match(line):
            out.append('* ' + _BULLET_RE.sub('', line))
        elif _NUMBERED_RE.match(line):
            out.append('# ' + _NUMBERED_RE.sub('', line))
        else:
            out.append(line)
    return '\n'.join(out)


def parse_segment(text, filename):
    """Extracts everything a sub-task needs from one segment file's text.

    Raises ValueError naming the missing piece rather than guessing -
    every field here is a fact the segment file is expected to state.
    """
    header_line_match = _HEADER_LINE_RE.search(text)
    if not header_line_match:
        raise ValueError(
            f'{filename}: could not find the "**Priority:** ... **LOC:**" header line')
    header_fields = {}
    for chunk in _HEADER_SEP_RE.split(header_line_match.group(0)):
        field_match = _HEADER_FIELD_RE.match(chunk.strip())
        if field_match:
            header_fields[field_match.group(1).strip().lower()] = field_match.group(2).strip()
    for required in ('priority', 'repo', 'files', 'loc'):
        if required not in header_fields:
            raise ValueError(
                f'{filename}: header line is missing "**{required.capitalize()}:**"')
    # Repo may carry trailing detail after its backtick-quoted name - a
    # parenthetical like "(whole-repo)", or for a reponame segment a branch
    # parenthetical like "(whole-repo)", or for a reponame segment a branch
    # and MR reference like ", branch `productname/...` (\`kragle/reponame!12708\`,
    # and MR reference like ", branch `productname/...` (\`kragle/reponame!12708\`,
    # and MR reference like ", branch `productname/...` (\`kragle/reponame!12708\`,
    # and MR reference like ", branch `productname/...` (\`kragle/reponame!12708\`,
    # Draft)". None of that is the repo name, and all of it duplicates the
    # readme's own Scope table, which is posted to the parent story once
    # (DRW-16/Phase 10.3) rather than repeated per sub-task - so only the
    # first backtick-quoted token is kept.
    repo_token_match = re.match(r'`([^`]+)`', header_fields['repo'])
    repo_value = (repo_token_match.group(1).strip() if repo_token_match
                  else re.sub(r'\s*\([^)]*\)\s*$', '', header_fields['repo']).strip('`').strip())

    title_match = _TITLE_RE.search(text)
    if not title_match:
        raise ValueError(f'{filename}: could not find the "# Segment N: Title" line')
    seg_num_match = _SEGMENT_NUM_RE.search(os.path.basename(filename))
    seg_num = seg_num_match.group(1) if seg_num_match else '?'

    dims = _find_section(text, 'Review dimensions')
    checklist_section = _find_section(text, 'Reviewer checklist')
    guard_section = _find_section(text, 'Guard against future change')
    spots_section = _find_section(text, 'Pay-attention-to spots')
    patterns_section = _find_section(text, 'Frequent bug patterns in this class of code')

    for name, section in (
        ('Review dimensions', dims),
        ('Reviewer checklist', checklist_section),
        ('Pay-attention-to spots', spots_section),
        ('Frequent bug patterns in this class of code', patterns_section),
    ):
        if section is None:
            raise ValueError(f'{filename}: missing required section "## {name}"')

    # Intro block: everything between the title line and the first "##" -
    # the "**Priority:** ..." header line, then the segment's own summary
    # paragraph, then a "**Files:** ..." detail line. The header line is
    # dropped since it is parsed separately above.
    lines = text.splitlines()
    title_line_idx = next(i for i, l in enumerate(lines) if _TITLE_RE.match(l))
    first_h2_idx = next(i for i in range(title_line_idx, len(lines)) if _H2_RE.match(lines[i]))
    intro_lines = lines[title_line_idx + 1:first_h2_idx]
    intro = '\n'.join(l for l in intro_lines if not _HEADER_LINE_RE.match(l)).strip('\n')

    checklist_items = []
    for line in checklist_section.splitlines():
        m = _CHECKLIST_ITEM_RE.match(line.strip())
        if m:
            checklist_items.append(m.group(1).strip())

    return {
        'title': title_match.group(1).strip(),
        'segment_number': seg_num,
        'priority': header_fields['priority'],
        'repo': repo_value,
        'files': header_fields['files'],
        'loc': header_fields['loc'],
        'intro': intro,
        'dims': dims,
        'guard': guard_section,
        'spots': spots_section,
        'patterns': patterns_section,
        'checklist_items': checklist_items,
    }


def build_description(parsed):
    parts = [
        'h2. Scope',
        '',
        f"Repo: {parsed['repo']}. Files: {parsed['files']}. LOC: {parsed['loc']}. "
        f"Priority: {parsed['priority']}.",
        '',
        parsed['intro'],
        '',
        'h2. Review dimensions',
        '',
        parsed['dims'],
    ]
    if parsed['guard']:
        parts += ['', 'h3. Guard against future change', '', parsed['guard']]
    parts += [
        '',
        'h2. Pay-attention-to spots',
        '',
        parsed['spots'],
        '',
        'h2. Frequent bug patterns in this class of code',
        '',
        parsed['patterns'],
    ]
    return _to_wiki_markup(_reflow('\n'.join(parts)))


def build_acceptance_criteria(parsed):
    lines = [f'- {item}' for item in parsed['checklist_items']]
    return _to_wiki_markup('\n'.join(lines))


# ---------------------------------------------------------------------------
# Jira HTTP
# ---------------------------------------------------------------------------

def _jira_config():
    """Reads server/login out of jira-cli's own config.yml (only those two
    keys - no YAML dependency needed for a file this flat)."""
    config_path = os.environ.get(
        'JIRA_CONFIG_FILE',
        os.path.expanduser('~/.config/.jira/.config.yml'),
    )
    values = {}
    try:
        with open(config_path, encoding='utf-8') as f:
            for line in f:
                m = re.match(r'^(server|login):\s*(.+?)\s*$', line)
                if m:
                    values[m.group(1)] = m.group(2)
    except OSError:
        pass
    return values


def _jira_request(method, path, login, token, payload=None):
    url = _jira_config().get('server', '').rstrip('/') + path
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    import base64
    auth = base64.b64encode(f'{login}:{token}'.encode()).decode()
    req.add_header('Authorization', f'Basic {auth}')
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read()
            return resp.status, json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        return e.code, {'error': body}


def _verify_project_config(project_key, login, token):
    """Re-checks this module's hardcoded Jira ids against the target
    project's live create-metadata before any write. SUBTASK_ISSUETYPE_ID
    and ACCEPTANCE_CRITERIA_FIELD are specific to one Jira project's
    configuration - copying this script to point at a different project,
    or a Jira admin renaming/removing the Acceptance Criteria field,
    would otherwise silently post a sub-task with a missing or
    misdirected field. Never trust the constant; always confirm.

    Returns None if both ids check out, else an error string.
    """
    status, resp = _jira_request(
        'GET', f'/rest/api/3/issue/createmeta/{project_key}/issuetypes/{SUBTASK_ISSUETYPE_ID}',
        login, token,
    )
    if status != 200:
        return f'could not read create-metadata for {project_key}/{SUBTASK_ISSUETYPE_ID}: HTTP {status}'

    field_ids = {f['fieldId'] for f in resp.get('fields', [])}
    problems = []
    if ACCEPTANCE_CRITERIA_FIELD not in field_ids:
        problems.append(
            f'{ACCEPTANCE_CRITERIA_FIELD} (Acceptance Criteria) is not on the {project_key} '
            f'Sub-task create screen - it was moved, renamed, or this project uses a different id')
    for required in ('description', 'parent', 'summary', 'timetracking'):
        if required not in field_ids:
            problems.append(f'field "{required}" is not on the {project_key} Sub-task create screen')
    if problems:
        return '; '.join(problems)
    return None


def _resolve_assignee(email, login, token):
    status, resp = _jira_request(
        'GET', f'/rest/api/3/user/search?query={urllib.parse.quote(email)}',
        login, token,
    )
    if status != 200 or not resp:
        raise RuntimeError(f'could not resolve assignee {email}: HTTP {status} {resp}')
    return resp[0]['accountId']


# ---------------------------------------------------------------------------
# build / publish
# ---------------------------------------------------------------------------

def _out_dir(root, segment_path):
    stem = os.path.splitext(os.path.basename(segment_path))[0]
    return os.path.join(root, '.ai', 'temp', 'review_subtasks', stem)


def _cmd_build(argv):
    if not argv:
        print('ERR: missing <segment-file>')
        return 1
    segment_path = argv[0]
    opts = _parse_flags(argv[1:])

    if 'parent' not in opts:
        print('ERR: --parent KEY is required (the Jira story this sub-task belongs to)')
        return 1
    if opts.get('estimate') not in VALID_ESTIMATES:
        print(f'ERR: --estimate is required and must be one of {sorted(VALID_ESTIMATES)}. '
              f'Never guessed - 3d minimum, 5d for roughly double the usual context, '
              f'2w for reponame or Windows-service depth.')
              f'2w for reponame or Windows-service depth.')
        return 1

    root = project_root()
    full_path = os.path.join(root, segment_path)
    if not os.path.isfile(full_path):
        print(f'ERR: {full_path} not found')
        return 1

    out_dir = _out_dir(root, segment_path)
    if os.path.isdir(out_dir) and not opts.get('force'):
        print(f'{os.path.relpath(out_dir, root)} already exists - edit it directly, '
              f'or re-run with --force to regenerate from the segment file (this discards edits).')
        return 0

    with open(full_path, encoding='utf-8') as f:
        text = f.read()

    parsed = parse_segment(text, segment_path)
    description = build_description(parsed)
    acceptance_criteria = build_acceptance_criteria(parsed)

    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, 'description.md'), 'w', encoding='utf-8') as f:
        f.write(description)
    with open(os.path.join(out_dir, 'acceptance_criteria.md'), 'w', encoding='utf-8') as f:
        f.write(acceptance_criteria)

    meta = {
        'segment_file': segment_path,
        'summary': f"[Segment {parsed['segment_number']}] {parsed['title']} - code review",
        'parent': opts['parent'],
        'estimate': opts['estimate'],
        'assignee': opts.get('assignee'),
        'jira_key': None,
        'jira_url': None,
        'assignee_account_id': None,
    }
    with open(os.path.join(out_dir, 'meta.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2)

    rel = os.path.relpath(out_dir, root)
    print(f'Built {rel}/ - review description.md and acceptance_criteria.md, '
          f'edit either, then run:\n  mr script publish_review_subtask publish {segment_path}')
    return 0


def _cmd_publish(argv):
    if not argv:
        print('ERR: missing <segment-file>')
        return 1
    segment_path = argv[0]
    opts = _parse_flags(argv[1:])

    root = project_root()
    out_dir = _out_dir(root, segment_path)
    meta_path = os.path.join(out_dir, 'meta.json')
    if not os.path.isfile(meta_path):
        print(f'ERR: {os.path.relpath(out_dir, root)}/meta.json not found - '
              f'run the "build" step first.')
        return 1

    with open(meta_path, encoding='utf-8') as f:
        meta = json.load(f)
    with open(os.path.join(out_dir, 'description.md'), encoding='utf-8') as f:
        description = f.read()
    with open(os.path.join(out_dir, 'acceptance_criteria.md'), encoding='utf-8') as f:
        acceptance_criteria = f.read()

    token = os.environ.get('JIRA_API_TOKEN')
    if not token:
        print('ERR: JIRA_API_TOKEN is not set')
        return 1
    login = _jira_config().get('login')
    if not login:
        print('ERR: no login found in jira-cli config - run `jira init` once, or set JIRA_CONFIG_FILE')
        return 1

    project_key = meta['parent'].split('-')[0]
    config_problem = _verify_project_config(project_key, login, token)
    if config_problem:
        print(f'ERR: Jira config check failed before any write - {config_problem}')
        return 1

    fields = {
        'description': description,
        ACCEPTANCE_CRITERIA_FIELD: acceptance_criteria,
    }

    if meta.get('assignee') and not meta.get('assignee_account_id'):
        meta['assignee_account_id'] = _resolve_assignee(meta['assignee'], login, token)
    if meta.get('assignee_account_id'):
        fields['assignee'] = {'accountId': meta['assignee_account_id']}

    if meta.get('jira_key'):
        status, resp = _jira_request(
            'PUT', f"/rest/api/2/issue/{meta['jira_key']}", login, token, {'fields': fields})
        if status != 204:
            print(f'ERR: update failed, HTTP {status}: {resp}')
            return 1
        print(f"Updated {meta['jira_key']} ({meta['jira_url']})")
    else:
        fields.update({
            'project': {'key': project_key},
            'issuetype': {'id': SUBTASK_ISSUETYPE_ID},
            'parent': {'key': meta['parent']},
            'summary': meta['summary'],
            'timetracking': {'originalEstimate': meta['estimate']},
        })
        status, resp = _jira_request(
            'POST', '/rest/api/2/issue', login, token, {'fields': fields})
        if status != 201:
            print(f'ERR: create failed, HTTP {status}: {resp}')
            return 1
        meta['jira_key'] = resp['key']
        meta['jira_url'] = _jira_config().get('server', '').rstrip('/') + f"/browse/{resp['key']}"
        print(f"Created {meta['jira_key']} ({meta['jira_url']})")

    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2)
    return 0


def _parse_flags(argv):
    opts = {}
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == '--force':
            opts['force'] = True
        elif arg in ('--parent', '--estimate', '--assignee'):
            i += 1
            opts[arg.lstrip('-')] = argv[i] if i < len(argv) else ''
        i += 1
    return opts


def run(argv: list) -> int:
    """Publishes a review-segmentation segment as a Jira sub-task (two-phase: build, publish)."""
    if not argv or argv[0] in ('--help', '-h'):
        print(HELP)
        return 0
    action, rest = argv[0], argv[1:]
    if action == 'build':
        return _cmd_build(rest)
    if action == 'publish':
        return _cmd_publish(rest)
    print(f'ERR: unknown action "{action}" - expected "build" or "publish"')
    return 1


if __name__ == '__main__':
    sys.exit(run(sys.argv[1:]))
