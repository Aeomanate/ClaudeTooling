#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Step 2: create or update the GitLab MR for the current branch.
Called automatically by the git pre-push hook. Never blocks the push.
"""

import json
import os
import re
import sys
import time

from git_hooks_impl.branch_utils import (
    _CHECKLIST_RE,
    _embed_body_hash,
    body_was_edited,
    parse_branch,
    read_plan,
    visible_body_for_reconstruction,
)
from git_hooks_impl.dialogs import plan_check_dialog
from git_hooks_impl.entry_points.extract_plan import _write_plan
from git_hooks_impl.first_push import create_mr
from git_hooks_impl.glab import (
    GITLAB_HOST,
    current_user,
    get_project_path,
    glab_api_post,
    glab_api_write,
)
from git_hooks_impl.logger import config, dbg, err, log, ok, warn
from git_hooks_impl.plan.cache import (
    _CACHE_DIR,
    _load_base,
    _sanitize_branch_name,
    _save_base,
    _save_cache,
    _save_mr_description,
)
from git_hooks_impl.plan.merge import (
    _print_diff,
    _show_merge_result,
    _try_auto_merge,
    _write_local_backup,
    _write_remote,
)
from git_hooks_impl.plan.parser import (
    _DISCUSSIONS_BLOCK_RE,
    PLAN_FOOTER_PATTERN,
    canonical_plan,
    compute_body_hash,
    embed_meta,
    embed_plan_hash,
    extract_body_hash,
    extract_footer_meta,
    extract_meta,
    find_unposted_discussions,
    plan_footer,
    plan_was_edited_on_mr,
    reconstruct_plan_content,
    strip_meta,
    validate_discussions,
    visible_plan_body,
)
from git_hooks_impl.utils import (
    PLAN_FILE,
    find_tool,
    is_master_or_main,
    run,
    run_async,
)


def _body_content_changed(plan_content):
    """Check if visible MR body content changed since last push.

    Compares the embedded body-hash (set at push time) against a freshly
    computed hash of only the visible content (after stripping hidden blocks
    and meta). Returns True when body update should run:
    - No body-hash embedded (first push or never pushed)
    - Hash mismatch (visible content was edited locally)

    Changes inside hidden blocks (TODOs, decisions, timing) do NOT trigger
    an update — only Description, Context, Areas of Impact, etc.
    """
    stored = extract_body_hash(plan_content)
    if stored is None:
        dbg('No body-hash found — first push, body update needed')
        return True
    current = compute_body_hash(plan_content)
    changed = stored != current
    if changed:
        dbg(f'Visible plan body changed (stored={stored}, current={current})')
    else:
        dbg('Visible plan body unchanged (body-hash match)')
    return changed


def _update_local_plan_hash():
    """Re-embed plan-hash and body-hash in local PLAN.md after successful push.

    Reads the file from disk, recomputes and embeds fresh hashes, writes back.
    This marks the local
    file as "in sync" so the next push can detect real changes.
    Best-effort — never fails.
    """
    try:
        with open(PLAN_FILE, encoding='utf-8') as f:
            content = f.read()
        stamped = embed_plan_hash(content)
        with open(PLAN_FILE, 'w', encoding='utf-8') as f:
            f.write(stamped)
        dbg('Local plan hash updated after push')
    except OSError:
        pass


def _extract_checklist(body):
    """Extract the ## Checklist section (and everything after) from MR body.

    '## Description\\n...\\n## Checklist\\n- [ ] Tests\\n/label ~bug'
    -> '## Checklist\\n- [ ] Tests\\n/label ~bug'

    Returns the matched text, or empty string if no Checklist section.
    """
    m = _CHECKLIST_RE.search(body)
    return m.group(0) if m else ''


def _map_plan_to_body(clean_body, plan_content):
    """Deterministic Python mapping: visible plan content becomes the MR body.

    Extracts visible plan sections (Context, Description, Areas of Impact)
    and appends the existing Checklist from the MR body (if any).

    clean_body:   current MR body (managed sections stripped)
    plan_content: raw PLAN.md content
    """
    visible = visible_plan_body(plan_content)
    if not visible.strip():
        return clean_body  # no visible plan content — keep existing body

    checklist = _extract_checklist(clean_body)
    if checklist:
        return visible.rstrip() + '\n\n' + checklist
    return visible


def _write_divergent(branch, clean_body):
    """Save the remote MR body to the branch cache. Returns the path, or ''.

    Returns '' when no branch is known or the write fails — the caller still
    reports the divergence, it just cannot name a recovery file.
    """
    if not branch:
        return ''
    cache_dir = os.path.join(_CACHE_DIR, _sanitize_branch_name(branch))
    divergent_path = os.path.join(cache_dir, 'last_mr_description.divergent')
    try:
        os.makedirs(cache_dir, exist_ok=True)
        with open(divergent_path, 'w', encoding='utf-8') as f:
            f.write(clean_body)
    except OSError:
        return ''
    return divergent_path


async def update_mr(mr_iid, current_desc, plan_content, branch=None, force=False):
    """Replace the PLAN.md and Discussions sections in an existing MR description.

    Uses body-hash to detect manual edits on GitLab. If edited, writes the
    edited body to a divergent artifact and exits without overwriting — the
    user must resolve manually. If not edited, maps plan content to body.

    force=True skips the edit check and overwrites the remote body. The
    divergent artifact is still written first, so the overwritten text is
    recoverable from the cache directory.
    """
    # Detect if body was manually edited on GitLab
    edited, clean_body = body_was_edited(current_desc)

    if edited and force:
        _write_divergent(branch, clean_body)
        warn('MR body differs from last push — overwriting anyway (--force)')
        edited = False

    if edited:
        # Body edited on GitLab — write divergent artifact, do not overwrite.
        divergent_path = _write_divergent(branch, clean_body)
        if divergent_path:
            log(f'MR body edited remotely; not overwritten. '
                f'Divergent body saved to {divergent_path}')
        else:
            log('MR body edited remotely; not overwritten.')
        return

    # Body not edited — deterministic Python mapping
    base_desc = _map_plan_to_body(clean_body, plan_content)

    # Assemble: body + plan-meta footer + body-hash
    new_desc = base_desc + plan_footer(plan_content)
    new_desc = _embed_body_hash(new_desc)

    if re.search(PLAN_FOOTER_PATTERN, current_desc, re.MULTILINE | re.DOTALL):
        log(f'Replacing existing plan-meta footer in MR !{mr_iid}')
    else:
        log(f'Appending plan-meta footer to MR !{mr_iid}')

    dbg(f'New description length: {len(new_desc)} chars')
    if branch:
        _save_mr_description(branch, new_desc)

    project_path = await get_project_path()
    if not project_path:
        err(f'Cannot update MR !{mr_iid} — could not resolve project path')
        dbg(f'glab api PUT !{mr_iid} failed: no project path')
        return
    api_path = f"projects/{project_path.replace('/', '%2F')}/merge_requests/{mr_iid}"
    exit_code, _, stderr = await glab_api_write(api_path, {'description': new_desc}, method='PUT')
    if exit_code == 0:
        ok(f'MR !{mr_iid} PLAN.md section updated')
        _update_local_plan_hash()
    else:
        err(f'Failed to update MR !{mr_iid}: {stderr.strip()}')
        dbg(f'glab api PUT !{mr_iid} failed (exit_code={exit_code}): {stderr.strip()}')


def _build_thread_url(project_path, mr_iid, api_result):
    """Build a direct URL to the posted discussion thread.

    'group/productname/reponame', 42, {'notes': [{'id': 789}]} -> 'https://host/group/productname/reponame/-/merge_requests/42#note_789'
    'group/productname/reponame', 42, {'notes': [{'id': 789}]} -> 'https://host/group/productname/reponame/-/merge_requests/42#note_789'
    """
    mr_url = f'https://{GITLAB_HOST}/{project_path}/-/merge_requests/{mr_iid}'
    try:
        note_id = api_result['notes'][0]['id']
        return f'{mr_url}#note_{note_id}'
    except (KeyError, IndexError, TypeError):
        return mr_url


async def _post_discussions(mr_iid, plan_content):
    """Post unposted ### <topic> entries under ## Discussions as MR threads.

    After posting, strips the body and embeds the URL in the header:
    ### [Title](url). Returns updated plan_content, or original if nothing posted.
    """
    violations = validate_discussions(plan_content)
    for title, violation_type in violations:
        warn(f"Discussion '{title}': {violation_type} — fix before pushing")

    discussions = find_unposted_discussions(plan_content)
    if not discussions:
        return plan_content

    # Get project path for API calls
    project_path = await get_project_path()
    if not project_path:
        warn('Skipping discussion posting — could not resolve project path')
        return plan_content
    api_path = f"projects/{project_path.replace('/', '%2F')}/merge_requests/{mr_iid}/discussions"

    updated = plan_content
    for title, body in discussions:
        # Format as a thread: title as heading + body
        thread_body = f'## {title}\n\n{body}'
        result = await glab_api_post(api_path, {'body': thread_body})
        if result:
            ok(f"Posted discussion thread: '{title}' on MR !{mr_iid}")
            dbg(f"Posted discussion '{title}' to MR !{mr_iid}")
            # Replace ### Title\n<body> with ### [Title](url)
            # Scoped to the discussions block to avoid matching ### headings
            # earlier in the plan (e.g. Architecture sub-sections).
            thread_url = _build_thread_url(project_path, mr_iid, result)
            replacement = f'### [{title}]({thread_url})\n'
            section_re = re.compile(
                r'^### ' + re.escape(title) + r'\n'
                r'.*?'
                r'(?=\n### |\n## |\Z)',
                re.DOTALL | re.MULTILINE,
            )
            block_m = _DISCUSSIONS_BLOCK_RE.search(updated)
            if block_m:
                block = block_m.group(0)
                new_block = section_re.sub(replacement, block, count=1)
                updated = updated[:block_m.start()] + new_block + updated[block_m.end():]
        else:
            warn(f"Failed to post discussion '{title}' — will retry on next push")

    # Write back updated BRANCH_PLAN.md with discussion links
    if updated != plan_content:
        try:
            with open(PLAN_FILE, 'w', encoding='utf-8') as f:
                f.write(updated)
            dbg('Updated BRANCH_PLAN.md with discussion links')
        except OSError as exc:
            warn(f'Could not write discussion links to {PLAN_FILE}: {exc}')

    return updated


def _detect_plan_divergence(current_desc, plan_content):
    """Detect whether the MR plan section diverged from the local plan.

    Pure logic: extracts the plan from the MR description, checks if it was
    edited on GitLab, strips meta for clean comparison.

    Returns (diverged, mr_plan, local_clean, remote_clean, local_meta):
      diverged     — True when local and remote plans differ meaningfully
      mr_plan      — raw plan text extracted from MR description (or '')
      local_clean  — plan_content with meta stripped (or '')
      remote_clean — mr_plan with meta stripped (or '')
      local_meta   — dict of meta fields from local plan (may be empty)
    """
    footer_meta = extract_footer_meta(current_desc)
    body = visible_body_for_reconstruction(current_desc)
    mr_plan = reconstruct_plan_content(footer_meta, body)
    if mr_plan is None:
        return False, '', '', '', {}

    if not plan_was_edited_on_mr(mr_plan):
        return False, mr_plan, '', '', {}

    local_meta = extract_meta(plan_content)
    local_clean = strip_meta(plan_content)
    remote_clean = strip_meta(mr_plan)

    if local_clean == remote_clean:
        return False, mr_plan, local_clean, remote_clean, local_meta

    return True, mr_plan, local_clean, remote_clean, local_meta


def _resolve_push_plan_conflict(current_desc, plan_content, branch):
    """Check if the MR plan was edited on GitLab and resolve before overwriting.

    During push, git pipes ref data to stdin so isatty() is False — but a
    display IS available (plan_check_dialog already works).  We rely on
    conflict_dialog's tkinter try/except for no-display fallback (CI),
    not on isatty().

    Returns (plan_content, should_continue):
      plan_content   — possibly updated (remote/merged) or original (local)
      should_continue — False to abort push (manual edit mode)
    """
    diverged, mr_plan, local_clean, remote_clean, local_meta = (
        _detect_plan_divergence(current_desc, plan_content))
    if not diverged:
        return plan_content, True

    log('PLAN.md was edited on the MR since last push')
    _write_local_backup(branch, plan_content)
    _print_diff(local_clean, remote_clean)

    # Try auto-merge when base exists and changes don't overlap
    base = _load_base(branch)
    if base:
        merged = _try_auto_merge(base, local_clean, remote_clean)
        if merged:
            log('Auto-merged (no overlapping changes)')
            _show_merge_result(branch, local_clean, merged)
            dbg('Push conflict resolved: auto-merged')
            restored = embed_meta(merged, **local_meta) if local_meta else merged
            _write_plan(restored)
            return merged, True

    _write_local_backup(branch, plan_content)
    _write_remote(branch, remote_clean)
    local_path = os.path.join(_CACHE_DIR, _sanitize_branch_name(branch), 'local_PLAN.md')
    remote_path = os.path.join(_CACHE_DIR, _sanitize_branch_name(branch), 'remote_PLAN.md')
    warn(
        f'Plan conflict detected. Resolve manually then re-push, '
        f'or `mr gen_plan --force` to take MR version.\n'
        f'  Local:  {local_path}\n'
        f'  Remote: {remote_path}'
    )
    dbg('Push conflict: artifacts written, manual resolution required')
    return plan_content, False


def _check_plan_uuid_mismatch(plan_content, mr_description):
    """Return True if local plan UUID doesn't match the MR's plan UUID.

    Prevents overwriting an MR with a plan from a different branch
    (e.g. after git reset --hard left the wrong plan in .ai/BRANCH_PLAN.md).
    """
    local_uuid = extract_meta(plan_content).get('plan-uuid', '')
    if not local_uuid:
        return False

    footer_meta = extract_footer_meta(mr_description)
    if footer_meta is None:
        return False

    mr_uuid = footer_meta.get('plan-uuid', '')
    if not mr_uuid:
        return False

    if local_uuid == mr_uuid:
        return False

    err(f'Plan UUID mismatch — local {local_uuid[:8]} vs '
        f'MR {mr_uuid[:8]}. Wrong plan loaded?')
    err('Aborting MR update. Run: mr plangen')
    return True


_NULL_SHA = '0' * 40


def _is_delete_push():
    """Check if git is pushing a branch deletion (all refs have null local SHA).

    Git pre-push hook receives lines on stdin:
      <local_ref> <local_sha> <remote_ref> <remote_sha>
    For `git push origin -d branch`, local_sha is all zeros.
    Returns False when stdin is empty, unavailable, or a TTY (manual runs).
    """
    try:
        if not sys.stdin or not sys.stdin.readable():
            return False
        # Only read stdin when it's a pipe (git hook).
        # On a TTY (terminal / mr sync), os.read blocks forever.
        if sys.stdin.isatty():
            return False
        raw = os.read(sys.stdin.fileno(), 65536)
        text = raw.decode('utf-8', errors='replace').strip()
    except (OSError, ValueError, AttributeError):
        return False
    if not text:
        return False
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] != _NULL_SHA:
            return False
    return True


def _validate_sync_preconditions(branch):
    """Check whether MR sync should proceed for the given branch.

    Pure logic — no subprocess calls.  Skips on detached HEAD or master/main.

    Returns (should_continue, error_msg):
      should_continue — True when sync should proceed
      error_msg       — None for graceful skips, non-None string for errors
    """
    if branch == 'HEAD':
        return False, None
    if is_master_or_main(branch):
        return False, None
    return True, None


def _branch_on_remote(branch):
    """Return True when <branch> exists on origin."""
    exit_code, out, _ = run(['git', 'ls-remote', '--heads', 'origin', branch])
    return exit_code == 0 and bool(out.strip())


async def _discover_open_mr(branch):
    """Run glab mr list and parse the JSON to find a single open MR.

    I/O: calls glab CLI.

    Returns (mr_data, should_skip):
      mr_data     — dict with MR fields (including 'iid') or None
      should_skip — True when the caller should return 0 immediately
                    (e.g. multiple open MRs found)
    """
    exit_code, mr_json_str, stderr = run([
        'glab', 'mr', 'list',
        '--source-branch', branch,
        '--output', 'json',
    ])

    if exit_code == 0 and mr_json_str.strip():
        try:
            parsed = json.loads(mr_json_str)
            if not isinstance(parsed, list):
                parsed = [parsed] if isinstance(parsed, dict) and parsed.get('iid') else []
            open_mrs = [m for m in parsed if isinstance(m, dict) and m.get('iid')]
            if len(open_mrs) == 1:
                mr_data = open_mrs[0]
                log(f"Found open MR !{mr_data['iid']}: \"{mr_data.get('title', '?')}\"")
                return mr_data, False
            if len(open_mrs) > 1:
                warn(f"Multiple open MRs for branch '{branch}':")
                for m in open_mrs:
                    warn(f"  !{m['iid']}: \"{m.get('title', '?')}\"")
                warn('Skipping MR sync — close duplicates so only one remains.')
                return None, True
            log('No open MR found — will create one')
            return None, False
        except (json.JSONDecodeError, ValueError) as exc:
            dbg(f'glab mr list returned invalid JSON: {exc}')
            dbg(f'JSON parse error from glab mr list: {exc}')
            log('No open MR found — will create one')
            return None, False
    else:
        if exit_code != 0:
            dbg(f'glab mr list exit_code={exit_code}: {stderr.strip()}')
            dbg(f'glab mr list failed (exit_code={exit_code}): {stderr.strip()}')
        log('No open MR found — will create one')
        return None, False


async def cmd_sync_mr(force=False):
    """Create or update the GitLab MR for the current branch.

    force=True overwrites an MR body that differs from the last push instead
    of stopping. Only the `mr sync` CLI path sets it; hook runs never do.
    """
    if _is_delete_push():
        dbg('Delete push detected — skipping MR sync')
        return 0

    t0 = time.time()
    log('Running...')

    if not find_tool('glab'):
        warn("'glab' not found — skipping MR sync. Run: mr setup")
        return 0

    exit_code, branch, _ = run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
    branch = branch.strip()
    if exit_code != 0 or not branch:
        warn(f'Could not determine current branch (exit_code={exit_code}) — skipping MR sync')
        return 0

    should_continue, error_msg = _validate_sync_preconditions(branch)

    if not should_continue:
        if error_msg:
            err(error_msg)
            return 1
        if branch == 'HEAD':
            warn('Detached HEAD state — skipping MR sync')
        else:
            log(f'Skipping MR sync on {branch}')
        return 0

    log(f'Branch: {branch}')

    template, jira_ticket = parse_branch(branch)
    plan_content = read_plan()

    if plan_content:
        canonical = canonical_plan(plan_content)
        if canonical != plan_content:
            plan_content = canonical
            try:
                with open(PLAN_FILE, 'w', encoding='utf-8') as f:
                    f.write(plan_content)
                dbg('Canonicalized local plan before sync')
            except OSError as exc:
                warn(f'Could not write canonicalized plan to {PLAN_FILE}: {exc}')

    if plan_content and find_tool('claude') and not plan_check_dialog():
        log('Push aborted — update .ai/BRANCH_PLAN.md and push again')
        return 1

    exit_code, _, stderr = await run_async(['glab', 'auth', 'status', '--hostname', GITLAB_HOST])
    if exit_code != 0:
        warn('glab auth status failed — may be a network issue or missing token.')
        dbg(f'  stderr: {stderr.strip()}')
        warn(f'  If not authenticated, run: glab auth login --hostname {GITLAB_HOST}')
        warn('  Continuing anyway — MR commands will fail on their own if auth is broken.')

    username = await current_user()
    if username:
        log(f'Current user: {username}')

    log('Checking for open MRs...')
    mr_data, should_skip = await _discover_open_mr(branch)
    if should_skip:
        return 0

    if mr_data:
        mr_iid = mr_data['iid']
        current_desc = mr_data.get('description') or ''
        if not plan_content:
            dbg('No plan content — skipping MR update')
            return 0

        # UUID guard: refuse to overwrite MR with a plan from a different branch
        uuid_mismatch = _check_plan_uuid_mismatch(plan_content, current_desc)
        if uuid_mismatch:
            return 1

        # Check if remote plan was edited on GitLab since last push
        if plan_content:
            plan_content, should_continue = _resolve_push_plan_conflict(
                current_desc, plan_content, branch)
            if not should_continue:
                return 1

            # Post discussions FIRST — embeds URLs in ### headers.
            # This must happen before update_mr so the MR body includes URLs;
            # otherwise extract-plan restores URL-less content and duplicates
            # discussions on the next push.
            plan_content = await _post_discussions(mr_iid, plan_content)
            await update_mr(mr_iid, current_desc, plan_content, branch=branch,
                            force=force)

            # Save base AFTER push — represents what's now on the MR.
            # Must be after update_mr so the 3-way merge on the NEXT push
            # correctly identifies local vs remote changes.
            _save_base(branch, strip_meta(plan_content))
        else:
            log('No local PLAN.md — leaving existing MR description unchanged')
    else:
        # `mr sync` (not the pre-push hook) publishes a branch that mr new
        # created locally. Push it first so the MR has a source branch.
        # Hook path (config.command == 'sync-mr') is skipped — git is
        # already pushing.
        if config.command == 'sync' and not _branch_on_remote(branch):
            log(f"Branch '{branch}' not on remote — pushing")
            exit_code, _, push_err = run(['git', 'push', '-u', 'origin', branch])
            if exit_code:
                err(f'git push failed: {push_err.strip()}')
                return 1
        footer = plan_footer(plan_content) if plan_content else ''
        await create_mr(branch, template, jira_ticket, plan_content, footer, username)

    # Keep cache fresh after successful MR sync
    _save_cache(branch)

    elapsed = time.time() - t0
    log(f'Done ({elapsed:.1f}s)')
    return 0
