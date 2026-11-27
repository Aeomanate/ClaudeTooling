#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Extract .ai/BRANCH_PLAN.md from the open MR for the current branch, or scaffold
a new one from template + Jira + branch diffs.  Provides both:
  - cmd_cache_swap() — fast local cache swap for post-checkout
  - cmd_extract_plan() — full MR fetch for post-merge/post-rewrite
Never blocks git operations.
"""

import json
import os
import re
import shutil
import sys
import time
import traceback
import uuid

from git_hooks_impl.ai_provider import AnthropicProvider
from git_hooks_impl.branch_utils import parse_branch, visible_body_for_reconstruction
from git_hooks_impl.content_extractor import ContentExtractor
from git_hooks_impl.jira import jira_summary
from git_hooks_impl.logger import dbg, err, log, ok, warn
from git_hooks_impl.plan.cache import (
    _CACHE_DIR,
    _prune_stale_caches,
    _read_deleted_branches,
    _resolve_branch_from_ref,
    _restore_cache,
    _sanitize_branch_name,
    _save_cache,
    _save_mr_description,
    load_gen_cache,
)
from git_hooks_impl.plan.context import PlanContext
from git_hooks_impl.plan.generator import PlanGenerator
from git_hooks_impl.plan.merge import _print_diff, _resolve_conflict
from git_hooks_impl.plan.parser import (
    embed_meta,
    embed_plan_hash,
    extract_footer_meta,
    extract_meta,
    plan_was_edited_on_mr,
    reconstruct_plan_content,
    strip_meta,
)
from git_hooks_impl.templates import template_skeleton
from git_hooks_impl.utils import (
    PLAN_FILE,
    TARGET_BRANCH,
    find_tool,
    is_master_or_main,
    prompt_yn,
    run,
    run_async,
)

# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------

# Token budget for single claude call (~150k tokens, ~4 chars/token)
_TOKEN_BUDGET_CHARS = 600_000

# Committed files alongside this module
_MODULE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TEMPLATE_PATH = os.path.join(_MODULE_DIR, 'prompt_templates', 'plan_template.md')

# Cooldown for "tool not found" hint messages (24 hours)
_NAG_COOLDOWN_SECS = 86400
_NAG_FILE = os.path.join('.ai', 'tool_hint_setup_suppressor')

# File patterns for omission tiers (multi-call mode)
_TEST_PATTERNS = re.compile(r'(^|/)test_[^/]*$|(^|/)tests/|(^|/)[^/]*_test\.[^/]*$')
_CONFIG_PATTERNS = re.compile(r'\.(json|lock|cmake)$|(^|/)docs/')


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _should_nag():
    """Return True if we should show a 'tool not found' hint (respects 24h cooldown)."""
    try:
        if os.path.isfile(_NAG_FILE):
            age = time.time() - os.path.getmtime(_NAG_FILE)
            if age < _NAG_COOLDOWN_SECS:
                return False
    except OSError:
        pass
    return True


def _touch_nag():
    """Update the nag cooldown file."""
    try:
        os.makedirs(os.path.dirname(_NAG_FILE), exist_ok=True)
        with open(_NAG_FILE, 'w') as f:
            f.write('')
    except OSError:
        pass


def cmd_cache_prune():
    """Delete cache directories for branches deleted in this transaction.

    Called by the reference-transaction hook on committed state.
    Reads deleted branch names from stdin and removes their cache dirs.
    """
    deleted = _read_deleted_branches()
    if not deleted:
        return 0
    for branch in deleted:
        cache_dir = os.path.join(_CACHE_DIR, _sanitize_branch_name(branch))
        if os.path.isdir(cache_dir):
            shutil.rmtree(cache_dir, ignore_errors=True)
            log(f'Pruned cache for deleted branch: {branch}')
        else:
            dbg(f'No cache dir for deleted branch: {branch}')
    return 0


def _write_plan(content):
    """Write content to .ai/BRANCH_PLAN.md, creating the directory if needed.

    Embeds the plan hash so future extract-plan calls can detect
    whether the MR version was edited since this write.
    Generates a plan-uuid if missing — new/scaffolded plans get a fresh UUID,
    plans extracted from MR keep their existing one.
    """
    content = embed_plan_hash(content)
    if 'plan-uuid' not in extract_meta(content):
        content = embed_meta(content, **{'plan-uuid': str(uuid.uuid4())})
    os.makedirs(os.path.dirname(PLAN_FILE), exist_ok=True)
    with open(PLAN_FILE, 'w', encoding='utf-8') as f:
        f.write(content)
    ok(f'Wrote {PLAN_FILE} ({len(content)} chars)')


_FALLBACK_TEMPLATE = (
    '# [{{TITLE}}]\n\n'
    '## Context\n\n{{CONTEXT}}\n\n'
    '## Implementation Plan\n\n- [ ] Step 1: ...\n\n'
    '## Decisions Log\n\n(Record key decisions and alternatives considered)\n'
)


def _load_template():
    """Load the plan template from the committed template file.

    Returns a minimal inline fallback if the template file is missing.
    """
    try:
        with open(_TEMPLATE_PATH, encoding='utf-8') as f:
            return f.read()
    except OSError as exc:
        warn(f'Could not load plan template ({_TEMPLATE_PATH}): {exc}')
        dbg(f'Template load failed: {exc} — using inline fallback')
        return _FALLBACK_TEMPLATE


def _title_from_branch(branch, jira_ticket='', jira_sum=''):
    """Derive a plan title from branch name and optional Jira info."""
    if jira_ticket and jira_sum:
        return f'[{jira_ticket}] {jira_sum}'
    tail = branch.rsplit('/', 1)[-1]
    title = re.sub(r'^[A-Za-z]+-\d+_', '', tail).replace('_', ' ')
    if title:
        title = title[0].upper() + title[1:]
    if jira_ticket:
        return f'[{jira_ticket}] {title}' if title else f'[{jira_ticket}]'
    if not title:
        return tail
    return title


# ---------------------------------------------------------------------------
#  Branch diff collection
# ---------------------------------------------------------------------------

def _get_merge_base():
    """Find the merge-base between HEAD and the closest base branch."""
    for ref in (TARGET_BRANCH, 'main'):
        exit_code, out, _ = run(['git', 'merge-base', ref, 'HEAD'])
        if exit_code == 0 and out.strip():
            return out.strip()
    dbg('git merge-base failed for all refs')
    return ''


def _get_diff_stat(merge_base):
    """Get diffstat (summary) from merge-base to HEAD."""
    exit_code, out, _ = run(['git', 'diff', '--stat', f'{merge_base}..HEAD'])
    if exit_code != 0:
        dbg(f'git diff --stat failed (exit_code={exit_code})')
        return ''
    return out


def _get_full_diff(merge_base):
    """Get the complete unified diff from merge-base to HEAD.

    Returns the raw diff text, or empty string on failure.
    Used as the primary context source for Claude plan generation.
    """
    exit_code, out, _ = run(['git', 'diff', f'{merge_base}..HEAD'])
    if exit_code != 0:
        dbg(f'git diff failed (exit_code={exit_code})')
        return ''
    return out


def _get_commit_messages(merge_base):
    """Get one-line commit messages (hash + subject) from merge-base to HEAD.

    Returns newline-separated '<hash> <subject>' lines, or empty string on failure.
    """
    exit_code, out, _ = run(['git', 'log', '--format=%H %s', f'{merge_base}..HEAD'])
    if exit_code != 0:
        dbg(f'git log failed (exit_code={exit_code})')
        return ''
    return out


def _get_diff_files(merge_base):
    """Get list of changed files with estimated diff sizes in characters.

    Returns [(path, size_chars), ...] where size_chars is a rough estimate
    based on added+removed lines * 40 chars/line.  Binary files get size 0.
    Returns empty list on failure.
    """
    exit_code, out, _ = run(['git', 'diff', '--numstat', f'{merge_base}..HEAD'])
    if exit_code != 0:
        dbg(f'git diff --numstat failed (exit_code={exit_code})')
        return []
    files = []
    for line in out.strip().splitlines():
        parts = line.split('\t')
        if len(parts) == 3:
            added, removed, path = parts
            try:
                size = (int(added) + int(removed)) * 40  # rough char estimate
            except ValueError:
                size = 0  # binary files show '-'
            files.append((path, size))
    return files


def _categorize_files(files):
    """Categorize files into omission tiers for multi-call diff strategy.

    Returns dict with keys 'tests', 'configs', 'keep', each mapping to
    a list of (path, size) tuples.  Tests are omitted first (tier 1),
    configs second (tier 2), and 'keep' files are always included.
    """
    tiers = {'tests': [], 'configs': [], 'keep': []}
    for path, size in files:
        if _TEST_PATTERNS.search(path):
            tiers['tests'].append((path, size))
        elif _CONFIG_PATTERNS.search(path):
            tiers['configs'].append((path, size))
        else:
            tiers['keep'].append((path, size))
    return tiers


def estimate_tokens(char_count):
    """Estimate token count from character count (~4 chars/token)."""
    return char_count // 4


def _fetch_git_diffs(merge_base):
    """Fetch all git diff data from merge-base to HEAD.

    I/O: calls _get_diff_stat, _get_full_diff, _get_commit_messages, _get_diff_files.
    Returns (diff_stat, full_diff, commit_msgs, diff_files).
    """
    diff_stat = _get_diff_stat(merge_base)
    full_diff = _get_full_diff(merge_base)
    commit_msgs = _get_commit_messages(merge_base)
    diff_files = _get_diff_files(merge_base)
    return diff_stat, full_diff, commit_msgs, diff_files


def _build_tiered_diff(diff_files, merge_base, full_diff, diffstat, budget):
    """Decide tier strategy and return a labelled diff string trimmed to budget.

    Pure logic for file categorization and tier selection; delegates
    _get_filtered_diff for actual git calls when filtering is needed.

    Returns (label, diff_text) where label describes what was omitted,
    or ('fallback', diffstat) when all tiers exceed the budget.
    """
    total_chars = len(full_diff)

    tiers = _categorize_files(diff_files)

    # Tier 1: omit test files
    test_chars = sum(s for _, s in tiers['tests'])
    remaining = total_chars - test_chars
    dbg(f"Omitting {len(tiers['tests'])} test files "
        f"({test_chars} chars), remaining: {remaining} chars")
    log(f"Omitting {len(tiers['tests'])} test files")

    if remaining <= budget:
        keep_paths = [p for p, _ in tiers['configs'] + tiers['keep']]
        filtered = _get_filtered_diff(merge_base, keep_paths)
        return 'Diff (tests omitted)', filtered

    # Tier 2: also omit configs
    config_chars = sum(s for _, s in tiers['configs'])
    remaining -= config_chars
    dbg(f"Omitting {len(tiers['configs'])} config files "
        f"({config_chars} chars), remaining: {remaining} chars")
    log(f"Omitting {len(tiers['configs'])} config/generated files")

    if remaining <= budget:
        keep_paths = [p for p, _ in tiers['keep']]
        filtered = _get_filtered_diff(merge_base, keep_paths)
        return 'Diff (tests + configs omitted)', filtered

    # Tier 3: fall back to commit messages + diffstat only
    dbg(f'Falling back to commit messages + diffstat only ({len(diffstat)} chars)')
    log('Falling back to commit messages + diffstat only')
    return 'Diffstat', diffstat


async def _collect_context_for_generation(branch, jira_ticket, mr_desc=''):
    """Collect context for BRANCH_PLAN.md generation: diffs, commit messages, Jira, MR description.
    Uses single-call or multi-call strategy based on token budget.
    Returns context_parts — a list of strings with collected context.
    """
    context_parts = []

    # MR description
    if mr_desc:
        context_parts.append(f'MR description:\n{mr_desc}')

    # Jira
    if jira_ticket:
        jira_sum, jira_content = await jira_summary(jira_ticket)
        if jira_content:
            context_parts.append(f'Jira ticket ({jira_ticket}):\n{jira_content}')
        else:
            dbg(f'Jira summary for {jira_ticket} returned empty')

    # Branch diffs
    merge_base = _get_merge_base()
    if not merge_base:
        dbg('No merge-base found — skipping diff collection')
        return context_parts

    diffstat, full_diff, commit_msgs, _diff_files = _fetch_git_diffs(merge_base)

    if commit_msgs:
        context_parts.append(f'Commit messages:\n{commit_msgs}')

    total_chars = len(full_diff)
    est_tokens = estimate_tokens(total_chars)

    dbg(f'Diff size: {total_chars} chars, ~{est_tokens} tokens')

    if total_chars == 0:
        dbg('No diff — new branch with no feature commits yet')
    elif total_chars <= _TOKEN_BUDGET_CHARS:
        dbg(f'Single-call mode: {est_tokens} tokens estimated, feeding all diffs')
        log(f'Single-call mode: ~{est_tokens} tokens')
        context_parts.append(f'Full diff:\n{full_diff}')
    else:
        # Multi-call: progressively omit files
        dbg(f'Multi-call mode: {est_tokens} tokens estimated, budget exceeded')
        log(f'Multi-call mode: ~{est_tokens} tokens '
            f'(budget: {estimate_tokens(_TOKEN_BUDGET_CHARS)})')

        diff_files = _get_diff_files(merge_base)
        label, diff_text = _build_tiered_diff(
            diff_files, merge_base, full_diff, diffstat, _TOKEN_BUDGET_CHARS,
        )
        context_parts.append(f'{label}:\n{diff_text}')

    return context_parts


def _get_filtered_diff(merge_base, paths):
    """Get diff for specific file paths only.

    Used in multi-call mode after omitting test/config files from the full diff.
    Returns the filtered diff text, or empty string if no paths or on failure.
    """
    if not paths:
        return ''
    exit_code, out, _ = run(['git', 'diff', f'{merge_base}..HEAD', '--'] + paths)
    if exit_code != 0:
        dbg(f'git diff (filtered, {len(paths)} paths) failed (exit_code={exit_code})')
        return ''
    return out


# ---------------------------------------------------------------------------
#  Scaffold from template
# ---------------------------------------------------------------------------

async def _scaffold_plan(branch, jira_ticket):
    """Scaffold a BRANCH_PLAN.md from the committed template, enriched with Jira if available.

    Returns (plan_text, jira_summary_line) so callers can reuse the Jira
    data without a second fetch.
    """
    template = _load_template()

    jira_sum, jira_content = '', ''
    if jira_ticket:
        jira_sum, jira_content = await jira_summary(jira_ticket)

    title = _title_from_branch(branch, jira_ticket, jira_sum)
    context = jira_content or '(Add context here)'

    plan = template.replace('{{TITLE}}', title).replace('{{CONTEXT}}', context)
    return plan, jira_sum


# ---------------------------------------------------------------------------
#  Main command
# ---------------------------------------------------------------------------

async def cmd_extract_plan(force=False):
    """Extract .ai/BRANCH_PLAN.md from the open MR for the current branch, or scaffold
    a new one from template.  Called by post-merge and post-rewrite hooks.
    Never blocks git operations — always returns 0.
    Also prunes stale cache directories (runs in heavier hooks that
    already do network, not on checkout).

    force=True: ignore hash match, overwrite local file with MR version.
    Used by 'mr plangen --force' when the user wants a fresh copy.
    """
    t0 = time.time()

    if force:
        log('Force mode — will overwrite local plan with MR version')

    try:
        result = await _extract_plan_inner(force=force)
        _prune_stale_caches()
        if not force:
            cmd_cache_save()      # snapshot newly written plan
        return result
    except Exception as exc:
        # Never block git operations
        err(f'Unexpected error: {exc}')
        dbg(f'ERROR: {exc}')
        dbg(traceback.format_exc())
        return 0
    finally:
        elapsed = time.time() - t0
        dbg(f'Finished in {elapsed:.1f}s')


async def cmd_planget():
    """Extract .ai/BRANCH_PLAN.md from the MR body (no AI generation).

    Parses the collapsed PLAN.md section from the MR description.
    If no PLAN section exists, reports it and stops — unlike gen_plan
    which falls back to 5-step AI generation.
    Asks before overriding an existing local plan.
    """
    try:
        branch, _template_type, _jira_ticket = _discover_branch_and_ticket()
        if branch is None:
            return 0

        glab_path = find_tool('glab')
        if not glab_path:
            warn('glab not found — cannot fetch MR')
            dbg('glab not found — cannot fetch MR')
            return 0

        exit_code, mr_json_str, _stderr = await run_async([
            'glab', 'mr', 'list',
            '--source-branch', branch,
            '--output', 'json',
        ])

        mr_data = None
        mr_count = 0
        if exit_code == 0 and mr_json_str.strip():
            try:
                parsed = json.loads(mr_json_str)
                if not isinstance(parsed, list):
                    parsed = [parsed] if isinstance(parsed, dict) and parsed.get('iid') else []
                open_mrs = [m for m in parsed if isinstance(m, dict) and m.get('iid')]
                mr_count = len(open_mrs)
                if mr_count == 1:
                    mr_data = open_mrs[0]
            except (json.JSONDecodeError, ValueError) as exc:
                warn(f'glab mr list returned invalid JSON: {exc}')
                dbg(f'JSON parse error from glab mr list: {exc}')

        if mr_count > 1:
            warn(f"Multiple open MRs for branch '{branch}' — skipping")
            dbg(f'Multiple MRs ({mr_count}) — skipping')
            return 0

        if mr_count == 0:
            log('No open MR found')
            dbg('No open MR found — nothing to extract')
            return 0

        description = mr_data.get('description') or ''
        log(f"Found MR !{mr_data['iid']}")
        dbg(f"MR !{mr_data['iid']}")

        footer_meta = extract_footer_meta(description)
        body = visible_body_for_reconstruction(description)
        content = reconstruct_plan_content(footer_meta, body)
        if content is None:
            log('No PLAN.md section in MR — nothing to extract')
            dbg('No PLAN.md section in MR — nothing to extract')
            return 0

        if os.path.isfile(PLAN_FILE) and os.path.getsize(PLAN_FILE) >= _MIN_PLAN_SIZE:
            with open(PLAN_FILE, encoding='utf-8') as f:
                local_content = f.read()
            local_clean = strip_meta(local_content)
            remote_clean = strip_meta(content)
            if local_clean != remote_clean:
                _print_diff(local_clean, remote_clean)
                if sys.stdin.isatty() and not prompt_yn(
                        'Override local plan with MR version?',
                        default_yes=False):
                    log('Aborted — keeping local plan')
                    dbg('Aborted by user — keeping local plan')
                    return 0
            else:
                ok('Plan already up to date — no changes needed')
                return 0

        _write_plan(content)
        _save_cache(branch)
        dbg(f"Extracted PLAN.md from MR !{mr_data['iid']} ({len(content)} chars)")
        return 0

    except Exception as exc:
        err(f'Unexpected error in get-plan: {exc}')
        dbg(f'ERROR: {exc}')
        dbg(traceback.format_exc())
        return 0


def cmd_cache_save():
    """Post-commit: snapshot BRANCH_PLAN.md to cache for the current branch."""
    exit_code, branch, _ = run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
    branch = branch.strip()
    if exit_code != 0 or not branch or branch == 'HEAD':
        return 0
    if branch in ('master', 'main'):
        return 0
    _save_cache(branch)
    return 0


def cmd_cache_swap(prev_ref=None):
    """Post-checkout entry point: save old branch plan to cache, restore
    new branch plan from cache.  Fast and local — no network calls.
    Falls back to full MR fetch on cache miss.
    Never blocks git operations — always returns 0.
    """
    t0 = time.time()

    try:
        # 1. Get new (current) branch
        exit_code, new_branch, _ = run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
        new_branch = new_branch.strip()
        if exit_code != 0 or not new_branch or new_branch == 'HEAD':
            dbg(f'Cannot determine current branch (exit_code={exit_code}) — skipping')
            return 0

        # 2. Resolve old branch from prev_ref SHA
        old_branch = _resolve_branch_from_ref(prev_ref) if prev_ref else ''

        dbg(f"Switch: {old_branch or '(unknown)'} -> {new_branch}")

        # 3. Save old branch plan to cache (if different from new, skip master/main)
        should_save = (old_branch
                       and old_branch != new_branch
                       and old_branch not in ('master', 'main'))
        if should_save:
            _save_cache(old_branch)

        # 4. Skip restore for master/main (no plan to restore)
        if new_branch in ('master', 'main'):
            dbg('Target is master/main — no plan to restore')
            return 0

        # 5. Try cache restore (instant, no network)
        if _restore_cache(new_branch):
            dbg('Cache hit — restored from local cache')
            return 0

        # 6. Cache miss — print suggestion, exit 0. No AI pipeline on checkout.
        dbg('Cache miss — no cached plan')
        log(f'No cached plan for branch {new_branch}. '
            f'Run `mr gen_plan` to fetch from MR or generate from scratch.')
        return 0

    except Exception as exc:
        err(f'Cache swap error: {exc}')
        dbg(f'ERROR: {exc}')
        dbg(traceback.format_exc())
        return 0
    finally:
        elapsed = time.time() - t0
        dbg(f'Finished in {elapsed:.1f}s')


def _discover_branch_and_ticket():
    """Discover current branch, validate it, and parse Jira ticket.

    I/O: git rev-parse, parse_branch().
    Returns (branch, template_type, jira_ticket) on success,
    or (None, None, None) when the branch should be skipped.
    """
    exit_code, branch, _ = run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
    branch = branch.strip()
    if exit_code != 0 or not branch:
        warn('Could not determine current branch — skipping')
        dbg(f'Branch detection failed (exit_code={exit_code}) — skipping')
        return None, None, None
    if branch == 'HEAD':
        warn('Detached HEAD — skipping extract-plan')
        dbg('Detached HEAD — skipping')
        return None, None, None

    if is_master_or_main(branch):
        return None, None, None

    dbg(f'Branch: {branch}')
    log(f'Branch: {branch}')

    template_type, jira_ticket = parse_branch(branch)
    return branch, template_type, jira_ticket


async def _extract_plan_inner(force=False):
    """Core logic for cmd_extract_plan, separated for cleaner error handling."""
    branch, template_type, jira_ticket = _discover_branch_and_ticket()
    if branch is None:
        return 0

    # 4. Check glab
    glab_path = find_tool('glab')
    if not glab_path:
        # No glab — scaffold from template
        if _should_nag():
            log("glab not found — skipping MR check. Run 'mr setup' to enable.")
            _touch_nag()
        dbg('glab not found — scaffolding from template')
        await scaffold_or_generate(branch, jira_ticket, template_type,
                                    force=False, interactive=False)
        return 0

    # 5. Find open MR for this branch
    exit_code, mr_json_str, stderr = await run_async([
        'glab', 'mr', 'list',
        '--source-branch', branch,
        '--output', 'json',
    ])

    mr_data = None
    mr_count = 0
    if exit_code == 0 and mr_json_str.strip():
        try:
            parsed = json.loads(mr_json_str)
            if not isinstance(parsed, list):
                parsed = [parsed] if isinstance(parsed, dict) and parsed.get('iid') else []
            open_mrs = [m for m in parsed if isinstance(m, dict) and m.get('iid')]
            mr_count = len(open_mrs)
            if mr_count == 1:
                mr_data = open_mrs[0]
        except (json.JSONDecodeError, ValueError) as exc:
            warn(f'glab mr list returned invalid JSON: {exc}')
            dbg(f'JSON parse error from glab mr list: {exc}')

    # 6. Handle based on MR count
    if mr_count > 1:
        warn(f"Multiple open MRs for branch '{branch}' — skipping")
        dbg(f'Multiple MRs ({mr_count}) — skipping')
        return 0

    if mr_count == 1:
        return await _handle_mr(mr_data, branch, jira_ticket, template_type, force=force)

    # 0 MRs — scaffold or generate
    log('No open MR found')
    dbg('No MR found — scaffolding or generating')
    await scaffold_or_generate(branch, jira_ticket, template_type,
                                force=False, interactive=False)
    return 0


_MIN_PLAN_SIZE = 100  # Files smaller than this are treated as empty/stub


def _should_overwrite_plan(mr_content):
    """Decide whether the local plan should be overwritten by MR content.

    Pure comparison logic: checks local file existence/size, compares hashes,
    checks whether MR was edited since last push.

    Returns one of:
        'no_local'   — no local file (or stub); pull from MR.
        'identical'  — content identical after stripping meta; skip.
        'hash_match' — MR plan unchanged since push and local has content; skip.
        'conflict'   — MR was edited and local has real content; needs resolution.
    """
    if not os.path.isfile(PLAN_FILE):
        return 'no_local'

    local_size = os.path.getsize(PLAN_FILE)
    local_is_stub = local_size < _MIN_PLAN_SIZE
    if local_is_stub:
        log(f'Local {PLAN_FILE} is empty or stub ({local_size} chars) — pulling from MR')
        dbg(f'Local plan too small ({local_size} chars), treating as missing')
        return 'no_local'

    # Read local plan once for all comparisons below
    with open(PLAN_FILE, encoding='utf-8') as f:
        local_content = f.read()

    # UUID mismatch = local plan from a different branch (e.g. after switching branches)
    local_uuid = extract_meta(local_content).get('plan-uuid', '')
    mr_uuid = extract_meta(mr_content).get('plan-uuid', '')
    if local_uuid and mr_uuid and local_uuid != mr_uuid:
        log(f'Local plan UUID {local_uuid[:8]} differs from MR {mr_uuid[:8]} — pulling MR version')
        dbg(f'UUID mismatch (local={local_uuid[:8]} mr={mr_uuid[:8]}), treating as no_local')
        return 'no_local'

    # Local has real content — check MR edit state
    if not plan_was_edited_on_mr(mr_content):
        dbg('MR plan hash matches push — keeping local version')
        dbg('Skipped: MR plan unchanged since push')
        return 'hash_match'

    # MR was edited — compare cleaned content
    local_clean = strip_meta(local_content)
    remote_clean = strip_meta(mr_content)

    if local_clean == remote_clean:
        dbg('Local and MR content identical — skipping')
        dbg('Skipped: content identical despite hash mismatch')
        return 'identical'

    return 'conflict'


def _handle_existing_plan(content, mr_iid, branch, force=False):
    """Handle MR that has a PLAN.md section: hash check, conflict resolution.

    Compares the MR plan against local .ai/BRANCH_PLAN.md (if it exists) to decide
    whether to pull, skip, or prompt for conflict resolution.

    force=True bypasses hash check and overwrites local unconditionally.
    Empty/stub local files (< 100 chars) are also treated as missing.
    """
    # Bypass hash check so the developer gets a known-good MR copy immediately
    if force:
        log(f'Force: overwriting local plan with MR !{mr_iid} version')
        if os.path.isfile(PLAN_FILE):
            with open(PLAN_FILE, encoding='utf-8') as f:
                local_content = f.read()
            local_clean = strip_meta(local_content)
            remote_clean = strip_meta(content)
            if local_clean != remote_clean:
                _print_diff(local_clean, remote_clean)
                if sys.stdin.isatty() and not prompt_yn(
                        'Override local plan with MR version?',
                        default_yes=False):
                    log('Aborted — keeping local plan')
                    return 0
            else:
                log('(no content changes — metadata only)')
        _write_plan(content)
        dbg(f'Force-extracted PLAN.md from MR !{mr_iid} ({len(content)} chars)')
        return 0

    decision = _should_overwrite_plan(content)

    if decision == 'hash_match' or decision == 'identical':
        ok('Plan already up to date — no changes needed')
        return 0

    if decision == 'no_local':
        _write_plan(content)
        _save_cache(branch)
        dbg(f'Extracted PLAN.md from MR !{mr_iid} ({len(content)} chars)')
        return 0

    # Both sides diverged — need interactive resolution to avoid data loss
    with open(PLAN_FILE, encoding='utf-8') as f:
        local_content = f.read()
    local_meta = extract_meta(local_content)
    local_clean = strip_meta(local_content)
    remote_clean = strip_meta(content)

    action, resolved = _resolve_conflict(local_clean, remote_clean, branch)
    restored = embed_meta(resolved, **local_meta) if local_meta else resolved
    _write_plan(restored)
    _save_cache(branch)
    dbg(f'Conflict resolved ({action}), wrote {PLAN_FILE}')
    return 0


async def _handle_no_plan_section(mr_data, branch, jira_ticket, template_type='default'):
    """Handle MR that has no PLAN.md section: generate via PlanGenerator or scaffold.

    Tries the 5-step PlanGenerator pipeline first (Anthropic SDK).
    Falls back to template scaffolding if SDK is unavailable or fails.
    """
    log('MR has no PLAN.md section — generating plan')
    dbg('No PLAN section in MR — generating')

    plan, _ = await _try_ai_pipeline(branch, jira_ticket, template_type)
    if plan:
        _write_plan(plan)
        _save_cache(branch)
        return 0

    # Pipeline unavailable or failed — degrade gracefully to a static template
    description = mr_data.get('description') or ''
    dbg('Generation failed — falling back to template scaffold')
    template = _load_template()
    jira_sum = ''
    if jira_ticket:
        jira_sum, _ = await jira_summary(jira_ticket)
    title = _title_from_branch(branch, jira_ticket, jira_sum)

    context = description.strip() if description.strip() else '(Add context here)'

    plan = template.replace('{{TITLE}}', title).replace('{{CONTEXT}}', context)
    _write_plan(plan)
    _save_cache(branch)
    return 0


async def _handle_mr(mr_data, branch, jira_ticket, template_type='default', force=False):
    """Dispatch MR handling: extract existing PLAN section or generate a new one."""
    mr_iid = mr_data['iid']
    description = mr_data.get('description') or ''
    log(f'Found MR !{mr_iid}')
    dbg(f'MR !{mr_iid}')

    # Save full MR body to cache for future comparison
    _save_mr_description(branch, description)

    # Try to reconstruct plan content from the plan-meta footer and MR body
    footer_meta = extract_footer_meta(description)
    body = visible_body_for_reconstruction(description)
    content = reconstruct_plan_content(footer_meta, body)
    if content is not None:
        return _handle_existing_plan(content, mr_iid, branch, force=force)

    return await _handle_no_plan_section(mr_data, branch, jira_ticket, template_type)


def _all_steps_cached(branch: str) -> bool:
    """Return True when a complete gen_cache (all 4 steps) exists for branch."""
    return len(load_gen_cache(branch)) == 4


async def scaffold_or_generate(branch, jira_ticket, template_type='default',
                               force=False, interactive=True):
    """Generate or scaffold BRANCH_PLAN.md when no MR exists.

    Tries the 5-step PlanGenerator pipeline (Anthropic SDK).
    Falls back to template scaffold.

    Returns PlanContext carrying Jira data, labels, and assignees so
    callers (cmd_new, cmd_sync_mr) can create the MR without re-fetching.
    """
    # Prompt BEFORE any network I/O — avoids wasted fetching when user says n.
    if _all_steps_cached(branch) and not force and interactive:
        if not prompt_yn('Re-generate cached plan?'):
            log('Reusing cached plan; no fetching or AI calls.')
            _, labels, assignees = template_skeleton(template_type, jira_ticket)
            return PlanContext(jira_ticket=jira_ticket, labels=labels,
                               assignees=assignees)
        # Y means regenerate from scratch — propagate as force to wipe cache
        # in PlanGenerator.generate() (else the 4-step cache short-circuits).
        force = True

    # Write a stub BRANCH_PLAN.md so subsequent meta operations target the new branch
    stub = '# Generating plan...\n'
    _write_plan(stub)

    plan, context = await _try_ai_pipeline(branch, jira_ticket, template_type,
                                           force=force, interactive=interactive)
    if plan:
        _write_plan(plan)
        _save_cache(branch, force=force)
        return context

    # Fallback: scaffold from template
    plan, jira_sum = await _scaffold_plan(branch, jira_ticket)
    _write_plan(plan)
    _save_cache(branch, force=force)

    if not jira_ticket:
        log('Tip: include Jira ticket in branch name (e.g. PROJECTNAME-1234_desc) '
            'for richer plan scaffolding')
        dbg('No Jira ticket in branch name — plain scaffold')

    # Build minimal PlanContext for the scaffold path — labels from
    # template_skeleton (first call in this code path, no duplicate)
    _, labels, assignees = template_skeleton(template_type, jira_ticket)
    return PlanContext(jira_ticket=jira_ticket, jira_summary=jira_sum,
                       labels=labels, assignees=assignees)


async def _try_ai_pipeline(branch, jira_ticket, template_type,
                           force=False, interactive=True):
    """Try the AI PlanGenerator pipeline.

    Returns (plan_text, PlanContext) on success, ('', PlanContext()) on failure.
    PlanContext carries Jira data, labels, and assignees from ContentExtractor
    so callers don't need to re-fetch.
    """
    empty = ('', PlanContext())

    provider = AnthropicProvider()
    if not provider.is_available():
        log('Falling back to template-only scaffold; full 4-step AI pipeline skipped')
        return empty

    extractor = ContentExtractor(branch, jira_ticket, template_type)
    context = await extractor.extract_initial()

    # Load plan template and rules
    context.plan_template = _load_template()
    try:
        rules_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'prompt_templates', 'PlanGen', 'plan_generation_rules.md',
        )
        with open(rules_path, encoding='utf-8') as f:
            context.plan_rules = f.read()
    except OSError:
        context.plan_rules = ''

    generator = PlanGenerator(context, provider, extractor,
                              force=force, interactive=interactive)
    plan = await generator.generate()
    return plan, context
