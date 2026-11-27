#!/usr/bin/env python
"""SessionStart hook - emits the MANDATORY-TO-READ skill manifest, the
persistent-role list, and branch context (branch, Jira ticket, GitLab
project, local/remote branch-plan status).

Reads SessionStart event JSON from stdin only to stay compatible with the
hook contract; this hook does not otherwise use it.
"""
import json
import os
import re
import subprocess
import sys

try:
    from . import _branch, _manifest, _mode
except ImportError:
    import _branch
    import _manifest
    import _mode

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

_SKILL_ROOT = _manifest.SKILL_ROOT
_MANDATORY_FILES = _manifest.MANDATORY_FILES

_PERSISTENT_ROLES = _manifest.PERSISTENT_ROLES


def _git(*args):
    try:
        return subprocess.run(
            ['git', *args], capture_output=True, text=True, timeout=5
        ).stdout.strip()
    except Exception:
        return ''


def _parse_project_path(remote_url):
    """Extract group/project from https or ssh remote URL."""
    m = re.search(r'[:/]([^/]+/[^/]+?)(?:\.git)?$', remote_url)
    return m.group(1) if m else None


def _emit_mandatory_load_block():
    print(_mode.contract())
    print()

    if not _mode.is_hardening():
        print('Mandatory to read before continue:')
        print('  - .ai/BRANCH_PLAN.md')
        for rel in _manifest.POC_FILES:
            print(f'  - {_SKILL_ROOT}/{rel}')
        print()
        print('That is the whole read list for this mode. The contract above is '
              'the mode in full -- there is no rule file to load for it. Read a '
              'rule file when a specific rule has to be quoted or applied, and '
              'read the full stack only once the developer approves hardening.')
        return

    print('Mandatory to read before continue:')
    print('  - .ai/BRANCH_PLAN.md')
    for rel in _MANDATORY_FILES:
        print(f'  - {_SKILL_ROOT}/{rel}')
    print(f'  - {_SKILL_ROOT}/roles/<chosen-role>/rules.md')
    print(f'  - {_SKILL_ROOT}/roles/<chosen-role>/workflow.md')
    print()
    print(f"Persistent roles available: {', '.join(_PERSISTENT_ROLES)}")


def _emit_branch_context():
    """Prints the BRANCH CONTEXT block.

    Covers branch, default branch, Jira ticket, GitLab project, and local plan.
    """
    no_git = not os.path.isdir('.git')
    if no_git:
        print('=== BRANCH CONTEXT ===')
        print('BRANCH: n/a')
        print('DEFAULT-BRANCH: n/a')
        print('JIRA-TICKET: none')
        print('GITLAB-PROJECT: unknown')
        print('LOCAL-PLAN: n/a')
        print('SANITIZED-BRANCH: n/a')
        return

    branch = _branch.current_branch()
    default = _branch.default_branch()

    remote_url = _git('config', '--get', 'remote.origin.url')
    gitlab_project = _parse_project_path(remote_url) or 'unknown'

    ticket_match = re.search(r'[A-Z][A-Z0-9_]+-\d+', branch)
    jira_ticket = ticket_match.group(0) if ticket_match else 'none'

    local_plan = 'present' if _branch.local_plan_present() else 'absent'

    print('=== BRANCH CONTEXT ===')
    print(f"BRANCH: {branch or 'n/a'}")
    print(f'DEFAULT-BRANCH: {default}')
    print(f'JIRA-TICKET: {jira_ticket}')
    print(f'GITLAB-PROJECT: {gitlab_project}')
    print(f'LOCAL-PLAN: {local_plan}')
    print(f'SANITIZED-BRANCH: {_branch.sanitize_branch(branch) if branch else "n/a"}')

    other_worktrees = _branch.other_worktrees()
    if other_worktrees:
        print('OTHER-WORKTREES:')
        for line in other_worktrees:
            print(f'  {line}')

    if local_plan == 'absent' and branch and branch != default:
        print()
        print('NOTE: no .ai/BRANCH_PLAN.md found for this branch. '
              'Run `mr plangen` to generate one.')


_DOC_DIR_CANDIDATES = ['.ai-stuff', 'docs', 'doc', 'Documentation']


def _emit_doc_search_priority():
    """Lists this repo's doc directories, if any, and states search order."""
    found = [d for d in _DOC_DIR_CANDIDATES if os.path.isdir(d)]
    if not found:
        return
    print()
    print('=== SEARCH PRIORITY ===')
    print(f"Doc directories present: {', '.join(found)}")
    print('For anything a human would have written down (log locations, '
          'deployment/env setup, CI delivery paths, config), check these '
          'directories first. Fall back to a codebase search only when '
          'the docs do not cover it.')


def _remote_has_plan(branch):
    """Returns True if an open MR for this branch has a plan-meta description.

    Detected by the description's first line starting with '<!-- meta'.
    """
    try:
        proj = _git('config', '--get', 'remote.origin.url')
        project_path = _parse_project_path(proj)
        if not project_path:
            return None
        encoded = project_path.replace('/', '%2F')
        out = subprocess.run(
            [
                'glab', 'api', f'projects/{encoded}/merge_requests',
                '-f', f'source_branch={branch}',
                '-f', 'state=opened',
            ],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode != 0:
            return None
        mrs = json.loads(out.stdout or '[]')
        if not mrs:
            return False
        description = mrs[0].get('description') or ''
        first_line = description.splitlines()[0] if description else ''
        return first_line.startswith('<!-- meta')
    except Exception:
        return None


is_tooling_disabled = os.getenv('AI_TOOLING_ENABLED') == 'false'
if is_tooling_disabled:
    sys.exit(0)

# Emit the mode contract, then the read list that mode actually needs.
_emit_mandatory_load_block()

# Emit branch context (branch name, default branch, Jira ticket, GitLab project, local plan).
_emit_branch_context()

# Emit doc-directory search priority, if this repo has any doc directories.
_emit_doc_search_priority()

# Branch-plan status check - only on non-default branches; silent on default.
if not os.path.isdir('.git'):
    sys.exit(0)

branch = _branch.current_branch()
default = _branch.default_branch()

if not branch or branch == default:
    sys.exit(0)

local_exists = _branch.local_plan_present()

remote_has = _remote_has_plan(branch)

if local_exists:
    sys.exit(0)

print()
if remote_has is True:
    print(
        f"NOTE: branch '{branch}' has no local .ai/BRANCH_PLAN.md,"
        " but the open MR has a plan (meta block detected on first line)."
    )
    print('Suggest running `mr planget` to pull it into local before any session work.')
elif remote_has is False:
    print(
        f"NOTE: branch '{branch}' has no local .ai/BRANCH_PLAN.md"
        " and no remote plan exists."
    )
    print('Run `mr plangen` to generate one.')
# remote_has is None - glab call failed; stay silent rather than guess
