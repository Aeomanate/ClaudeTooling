#!/usr/bin/env python
"""Shared content-check predicates for the orchestrator skill tree.

Used by claude/hooks/check_content.py (PostToolUse hook, scoped to the
newly inserted text of one edit) and by git_hooks_impl's
validate_skill_conventions / validate_agent_files (mr script, whole-file
and whole-tree scans). One implementation only - the hook is the
constrained environment and owns the logic; the mr script imports it.

No git_hooks_impl import: hooks run standalone as
`python ~/.claude/hooks/<name>.py`, with their own directory on sys.path.
"""
import os
import re

# STYLE-2: history-narrative pollution. Order mirrors expected frequency.
HISTORY_PATTERNS = (
    r'\(NEW\)',
    r'\(this turn\)',
    r'\(just landed\)',
    r'\(just added\)',
    r'as of commit [a-f0-9]+',
    r'as of Phase [A-Z]',
    r'was added in commit',
    r'was added in Phase',
    r'tightening from Phase',
    r'\(landed in commit',
    r'\(landed in Phase',
    r'previously the rule',
    r'previously this clause',
    r'previously this rule',
    r'previous version of this rule',
    r'\(Phase [ABCD]\)',
    r'Phase [ABCD] (commit|landed|added|tightened|deprecated|finished)',
    r'recently added',
    r'recently landed',
    r'recently tightened',
    r'just added in this',
    r'migrated from .* to',
)
_HISTORY_RES = tuple(re.compile(p) for p in HISTORY_PATTERNS)

# Path suffixes exempt from the history-narrative scan (relative to the
# orchestrator dir): the rule file documenting STYLE-2 references these
# patterns as examples.
HISTORY_EXEMPT_SUFFIXES = ('shared/rules/style.md',)

# No '.md' entry: a bare '#'/'##' prefix can't distinguish a markdown
# heading from a comment, so markdown stays excluded from this line-marker
# heuristic rather than false-positive on every heading.
COMMENT_MARKERS = {
    '.py': '#', '.sh': '#', '.bash': '#',
    '.js': '//', '.ts': '//', '.cpp': '//', '.cc': '//',
    '.h': '//', '.hpp': '//', '.c': '//',
    '.rs': '//', '.go': '//', '.hxx': '//', '.cxx': '//',
}

BANNED_REGISTER = (
    (re.compile(r'\bwe\b', re.IGNORECASE), 'first-person plural "we"'),
    (re.compile(r"\blet's\b", re.IGNORECASE), 'first-person plural "let\'s"'),
    (re.compile(r'\bour\b', re.IGNORECASE), 'first-person plural "our"'),
    (re.compile(r'^\s*note that\b', re.IGNORECASE), 'filler opener "Note that"'),
    (re.compile(r'^\s*basically\b', re.IGNORECASE), 'filler opener "Basically"'),
    (re.compile(r'^\s*in other words\b', re.IGNORECASE), 'filler opener "In other words"'),
    (re.compile(r'^\s*here we\b', re.IGNORECASE), 'filler opener "Here we"'),
    (re.compile(r'^\s*this means that\b', re.IGNORECASE), 'filler opener "This means that"'),
)

CROSS_DIR_LINK_RE = re.compile(r'\]\(\.\./')
CROSS_DIR_LINK_EXEMPT_SUFFIXES = ('refactorer/patterns/', 'refactorer/smells/')

BARE_LINK_RE = re.compile(r'\[[a-z_-]+\.md\]\(')
BARE_LINK_EXEMPT_SUFFIXES = ('conventions.md',)

ALLOWED_INLINE_RES = (
    re.compile(r'^mr '),
    re.compile(r'^echo '),
    re.compile(r'^git (log|status|diff|rev-parse|branch|push|stash|checkout) '),
    re.compile(r'^git (log|status|diff|rev-parse|branch|push|stash|checkout)$'),
    re.compile(r'^[A-Z_]+=|^if |^then|^else|^fi|^for |^done|^do'),
    re.compile(r'^(jira |glab |curl )'),
    re.compile(r'^hooks\.tests\.'),
)
INLINE_COMMAND_EXEMPT_DIR_SEGMENTS = ('agent-instructions', 'patterns')

REQUIRED_AGENT_INSTRUCTION_SECTIONS = ('Purpose', 'Inputs', 'Output Format', 'Rules', 'Scope')

KIND_RE = re.compile(r'^kind: agent', re.MULTILINE)
# Accepts an alias (opus/sonnet/haiku), a family name, or a full dated ID -
# different agents intentionally use different tiers.
MODEL_RE = re.compile(
    r'^model: *"?(opus|sonnet|haiku|claude-opus-4-7|claude-sonnet-4-6|claude-haiku-4-5)',
    re.MULTILINE,
)
SELF_ROLE_DIR_RE = re.compile(r'^self_role_dir:', re.MULTILINE)
DISPATCH_INFO_RE = re.compile(r'^# Dispatch info', re.MULTILINE)


def normalize(path):
    return path.replace('\\', '/')


def has_suffix(norm_path, suffixes):
    return any(norm_path.endswith(s) for s in suffixes)


def is_under_orchestrator(norm_path):
    return 'claude/skills/orchestrator/' in norm_path and norm_path.endswith('.md')


def is_agent_file(norm_path):
    return 'claude/agents/' in norm_path and os.path.basename(norm_path).startswith('orchestrator-')


def check_history_narrative(file_path, text):
    """STYLE-2: no history-narrative pollution in canonical skill-tree text."""
    norm = normalize(file_path)
    if not (is_under_orchestrator(norm) or is_agent_file(norm)):
        return []
    if is_under_orchestrator(norm) and has_suffix(norm, HISTORY_EXEMPT_SUFFIXES):
        return []
    findings = []
    for line in text.splitlines():
        if '<!-- VALIDATED -->' in line:
            continue
        for regex in _HISTORY_RES:
            if regex.search(line):
                findings.append(f'history-narrative ({regex.pattern}): {line.strip()}')
                break
    return findings


def check_banned_register(file_path, text):
    """STYLE-8 mechanical half: banned register in newly added comment lines."""
    ext = os.path.splitext(file_path)[1].lower()
    marker = COMMENT_MARKERS.get(ext)
    if not marker:
        return []
    findings = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if not stripped.startswith(marker):
            continue
        comment_text = stripped[len(marker):].strip()
        for pattern, reason in BANNED_REGISTER:
            if pattern.search(comment_text):
                findings.append(f'comment register ({reason}): {line.strip()}')
                break
    return findings


def check_cross_dir_links(file_path, text):
    """DOC-5 shape: no `](../` cross-directory markdown links."""
    norm = normalize(file_path)
    if not (is_under_orchestrator(norm) or norm.endswith('.ai/BRANCH_PLAN.md')):
        return []
    if has_suffix(norm, CROSS_DIR_LINK_EXEMPT_SUFFIXES):
        return []
    return [f'cross-dir link: {line.strip()}' for line in text.splitlines()
            if CROSS_DIR_LINK_RE.search(line)]


def check_bare_link_text(file_path, text):
    """DOC-5 shape: link text must be descriptive, not a bare filename."""
    norm = normalize(file_path)
    if not (is_under_orchestrator(norm) or norm.endswith('.ai/BRANCH_PLAN.md')):
        return []
    if has_suffix(norm, BARE_LINK_EXEMPT_SUFFIXES):
        return []
    return [f'bare link text: {line.strip()}' for line in text.splitlines()
            if BARE_LINK_RE.search(line)]


def check_inline_commands(file_path, text):
    """DOC-3: bash-fenced commands in skill-tree prose should be mr/scripts."""
    norm = normalize(file_path)
    if not is_under_orchestrator(norm):
        return []
    if any(seg in norm.split('/') for seg in INLINE_COMMAND_EXEMPT_DIR_SEGMENTS):
        return []
    findings = []
    in_block = False
    for raw in text.splitlines():
        fence = raw.strip()
        if fence.startswith('```bash'):
            in_block = True
            continue
        if fence.startswith('```'):
            in_block = False
            continue
        if not in_block:
            continue
        cmd = fence
        if not cmd or cmd.startswith('#') or 'VALIDATED' in cmd:
            continue
        if any(allowed.search(cmd) for allowed in ALLOWED_INLINE_RES):
            continue
        findings.append(f'inline command should be mr/script: {cmd}')
    return findings


def check_agent_instruction_sections(file_path, text, tool_name):
    """Every agent-instructions/*.md needs the 5 standard sections.

    Whole-file only: a presence check needs the full document, so this
    fires on Write (full content) and never on Edit (a fragment).
    """
    norm = normalize(file_path)
    if 'agent-instructions/' not in norm or not norm.endswith('.md'):
        return []
    if tool_name != 'Write':
        return []
    missing = [s for s in REQUIRED_AGENT_INSTRUCTION_SECTIONS if f'## {s}' not in text]
    if not missing:
        return []
    return [f'agent-instructions missing section(s): {" ".join(missing)}']


def check_workflow_first_heading(file_path, text, tool_name):
    """A role workflow.md's first heading must be `## `.

    Whole-file only, same reason as check_agent_instruction_sections.
    """
    norm = normalize(file_path)
    if not norm.endswith('/workflow.md') or '/roles/skill-validation/' in norm:
        return []
    if tool_name != 'Write':
        return []
    first_heading = next((line for line in text.splitlines() if line.startswith('#')), None)
    if first_heading and not first_heading.startswith('## '):
        return [f"workflow.md first heading is not '## ': {first_heading}"]
    return []


def check_agent_frontmatter(file_path, text, tool_name):
    """Agent file frontmatter: kind, model, self_role_dir, pre-work, dispatch info.

    The CLAUDE_SKILL_DIR ban is a substring check and fires on any edit.
    The presence checks need the full document, so they fire on Write only.
    """
    norm = normalize(file_path)
    if not is_agent_file(norm):
        return []
    findings = []
    if 'CLAUDE_SKILL_DIR' in text:
        findings.append('forbidden CLAUDE_SKILL_DIR reference (use ~/.claude/skills/orchestrator)')
    if tool_name != 'Write':
        return findings
    dispatch_info_count = len(DISPATCH_INFO_RE.findall(text))
    if dispatch_info_count != 1:
        findings.append(f'expected exactly one "# Dispatch info" section, found {dispatch_info_count}')
    if not KIND_RE.search(text):
        findings.append('missing kind: agent')
    if not MODEL_RE.search(text):
        findings.append('model not a current Claude 4.x declaration')
    if os.path.basename(norm).startswith('orchestrator-persistent-'):
        if not SELF_ROLE_DIR_RE.search(text):
            findings.append('missing self_role_dir:')
        if 'MANDATORY pre-work' not in text:
            findings.append('missing MANDATORY pre-work section')
    return findings


# Checks that operate on (file_path, text) alone.
CONTENT_ONLY_CHECKS = (
    check_history_narrative,
    check_banned_register,
    check_cross_dir_links,
    check_bare_link_text,
    check_inline_commands,
)

# Checks that also need tool_name, since part of their logic only applies
# to a full-file Write.
TOOL_AWARE_CHECKS = (
    check_agent_instruction_sections,
    check_workflow_first_heading,
    check_agent_frontmatter,
)
