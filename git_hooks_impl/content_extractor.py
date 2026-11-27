#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Content extractor — fetches all context for plan generation from Jira,
GitLab, and project docs.  Produces a PlanContext dataclass consumed by
PlanGenerator.
"""

import asyncio
import json
import os
import re

import aiohttp

from git_hooks_impl.jira import jira_summary
from git_hooks_impl.logger import dbg, log, warn
from git_hooks_impl.plan.cache import _CACHE_DIR, _sanitize_branch_name
from git_hooks_impl.plan.context import AvailableResources, Evidence, PlanContext
from git_hooks_impl.plan.git_utils import detect_nearest_parent_branch
from git_hooks_impl.templates import template_skeleton
from git_hooks_impl.utils import find_tool, run, run_async

# -- Jira parsing ----------------------------------------------------------

_JIRA_TICKET_RE = re.compile(r'[A-Z]{2,10}-\d+')
_GITLAB_MR_RE = re.compile(r'!(\d+)')
# Full GitLab URL with project path — for cross-project MR references
# Matches: gitlab.companyname.com/kragle/reponame/-/merge_requests/11211
# Matches: gitlab.companyname.com/kragle/reponame/-/merge_requests/11211
_GITLAB_MR_FULL_URL_RE = re.compile(
    r'gitlab\.companyname\.com/([^/]+/[^/]+)/-/merge_requests/(\d+)')


def _extract_mr_refs(text):
    """Extract GitLab MR references from text, handling both formats.

    Returns set of (project_path, mr_id) tuples.
    Full URLs give explicit project, bare !N refs give project=''.
    Deduplicates: if a full URL and bare !N match the same ID, keeps the URL.
    """
    mr_tuples = set()
    for project_path, mr_id in _GITLAB_MR_FULL_URL_RE.findall(text):
        mr_tuples.add((project_path, mr_id))
    known_ids = {t[1] for t in mr_tuples}
    for mr_id in _GITLAB_MR_RE.findall(text):
        if mr_id not in known_ids:
            mr_tuples.add(('', mr_id))
            known_ids.add(mr_id)
    return mr_tuples


def _parse_jira_links(raw_json):
    """Extract linked ticket IDs and MR references from Jira raw JSON.

    Parses structured issuelinks, parent ticket, description text (Jira
    ticket refs + GitLab MR URLs), comments, and attachments.
    Returns AvailableResources.
    """
    resources = AvailableResources()

    try:
        data = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError):
        return resources

    fields = data.get('fields', {})

    # Structured issuelinks
    for link in fields.get('issuelinks', []):
        for direction in ('outwardIssue', 'inwardIssue'):
            issue = link.get(direction)
            if not issue:
                continue
            relation = link.get('type', {}).get('outward', '?')
            if direction == 'inwardIssue':
                relation = link.get('type', {}).get('inward', '?')
            resources.jira_tickets.append({
                'id': issue['key'],
                'relation': relation,
                'summary': issue.get('fields', {}).get('summary', ''),
            })

    # Parent ticket
    parent = fields.get('parent', {})
    existing_ids = {t['id'] for t in resources.jira_tickets}
    if parent and parent.get('key') and parent['key'] not in existing_ids:
        resources.jira_tickets.append({
            'id': parent['key'],
            'relation': 'parent',
            'summary': parent.get('fields', {}).get('summary', ''),
        })
        existing_ids.add(parent['key'])

    # Jira ticket refs from description text
    # Jira Cloud ADF: description may be a dict — stringify for regex search
    description = fields.get('description') or ''
    if not isinstance(description, str):
        description = json.dumps(description)
    for ticket_id in set(_JIRA_TICKET_RE.findall(description)):
        if ticket_id not in existing_ids:
            resources.jira_tickets.append({
                'id': ticket_id,
                'relation': 'mentioned in description',
                'summary': '',
            })
            existing_ids.add(ticket_id)

    # Attachments
    for attachment in fields.get('attachment', []):
        resources.attachments.append({
            'filename': attachment.get('filename', ''),
            'type': attachment.get('mimeType', ''),
            'size': attachment.get('size', 0),
            'url': attachment.get('content', ''),
        })

    # GitLab MR references — full URLs (cross-project) + bare !N
    mr_tuples = _extract_mr_refs(description)

    comments = fields.get('comment', {}).get('comments', [])
    for comment in comments:
        body = comment.get('body', '')
        # Jira Cloud ADF: comment body may be a dict — stringify for regex search
        if not isinstance(body, str):
            body = json.dumps(body)
        mr_tuples.update(_extract_mr_refs(body))
        # Jira ticket refs from comments
        for ticket_id in set(_JIRA_TICKET_RE.findall(body)):
            if ticket_id not in existing_ids:
                resources.jira_tickets.append({
                    'id': ticket_id,
                    'relation': 'mentioned in comments',
                    'summary': '',
                })
                existing_ids.add(ticket_id)

    for project_path, mr_id in mr_tuples:
        resources.gitlab_mrs.append({
            'id': mr_id,
            'project': project_path,
            'title': '',
            'state': '',
            'mentioned_in': 'Jira ticket body or comments',
        })

    return resources


async def _discover_sub_resources(available):
    """Fetch sub-resources from 1st-level links. Mutates available in-place.

    For each linked Jira ticket: fetch --raw, parse its attachments, MR refs,
    and sub-tickets. For each GitLab MR ref: fetch metadata, fill title/state,
    parse MR description for Jira ticket refs.

    Depth=1 only — tickets discovered from sub-tickets are added as metadata
    but NOT recursed into (the for-loop iterates a snapshot).
    Fetches are parallelized via asyncio.gather for lower wall-clock time.
    """
    existing_mr_ids = {m['id'] for m in available.gitlab_mrs}
    existing_ticket_ids = {t['id'] for t in available.jira_tickets}

    # Sub-resources from linked Jira tickets — parallel fetch
    linked_tickets = list(available.jira_tickets)
    if linked_tickets:
        log(f'Discovering sub-resources from {len(linked_tickets)} Jira tickets in parallel...')
        ticket_results = await asyncio.gather(*[
            run_async(['jira', 'issue', 'view', linked['id'], '--raw'])
            for linked in linked_tickets
        ], return_exceptions=True)

        for linked, result in zip(linked_tickets, ticket_results, strict=True):
            linked_id = linked['id']
            if isinstance(result, Exception):
                dbg(f'Could not fetch {linked_id} --raw: {result}')
                continue
            exit_code, raw, _ = result
            if exit_code != 0:
                dbg(f'Could not fetch {linked_id} --raw (exit_code={exit_code})')
                continue
            sub = _parse_jira_links(raw)
            for attachment in sub.attachments:
                attachment['via'] = linked_id
                available.attachments.append(attachment)
            for mr_ref in sub.gitlab_mrs:
                if mr_ref['id'] not in existing_mr_ids:
                    mr_ref['mentioned_in'] = f'{linked_id} body or comments'
                    available.gitlab_mrs.append(mr_ref)
                    existing_mr_ids.add(mr_ref['id'])
            for ticket in sub.jira_tickets:
                if ticket['id'] not in existing_ticket_ids:
                    ticket['via'] = linked_id
                    available.jira_tickets.append(ticket)
                    existing_ticket_ids.add(ticket['id'])
            dbg(f'Sub-resources from {linked_id}: '
                f'{len(sub.jira_tickets)} tickets, '
                f'{len(sub.attachments)} att, {len(sub.gitlab_mrs)} MRs')

    # Sub-resources from GitLab MR refs — parallel fetch
    if not find_tool('glab'):
        return
    mr_refs = list(available.gitlab_mrs)
    if mr_refs:
        log(f'Discovering metadata for {len(mr_refs)} GitLab MR refs in parallel...')
        mr_cmds = []
        for mr_ref in mr_refs:
            cmd = ['glab', 'mr', 'view', mr_ref['id'], '--output', 'json']
            if mr_ref.get('project', ''):
                cmd += ['--repo', mr_ref['project']]
            mr_cmds.append(cmd)

        mr_results = await asyncio.gather(*[run_async(cmd) for cmd in mr_cmds],
                                          return_exceptions=True)
        for mr_ref, result in zip(mr_refs, mr_results, strict=True):
            mr_id = mr_ref['id']
            if isinstance(result, Exception):
                dbg(f'Could not fetch MR !{mr_id} metadata: {result}')
                continue
            exit_code, meta_json, _ = result
            if exit_code != 0:
                dbg(f'Could not fetch MR !{mr_id} metadata (exit_code={exit_code})')
                continue
            try:
                meta = json.loads(meta_json)
            except json.JSONDecodeError:
                continue
            mr_ref['title'] = meta.get('title', '')
            mr_ref['state'] = meta.get('state', '')
            mr_description = meta.get('description', '') or ''
            for ticket_id in set(_JIRA_TICKET_RE.findall(mr_description)):
                if ticket_id not in existing_ticket_ids:
                    available.jira_tickets.append({
                        'id': ticket_id,
                        'relation': 'referenced in MR',
                        'summary': '',
                        'via': f'!{mr_id}',
                    })
                    existing_ticket_ids.add(ticket_id)
            dbg(f"Sub-resources from !{mr_id}: title={mr_ref['title']!r}, "
                f"state={mr_ref['state']!r}")


def _parse_required_resources(step1_output, available, debug_out=None):
    """Parse REQUIRED_RESOURCES JSON from step 1 output.

    Validates each item against available resources. IDs not in the
    pre-discovered pool are still accepted (as an on-demand fetch) when
    they are well-formed (Jira ticket pattern / numeric MR id) — the
    downstream fetch handler fails gracefully if the id turns out to be
    invalid. Returns list of validated (type, id_or_filename) tuples.

    If debug_out is a dict, it is populated with available/requested/
    validated/dropped info for debugging (gen_cache/resources.json).
    """
    match = re.search(
        r'<!-- REQUIRED_RESOURCES -->\s*(.*?)\s*<!-- /REQUIRED_RESOURCES -->',
        step1_output, re.DOTALL,
    )
    if not match:
        dbg('No REQUIRED_RESOURCES section in step 1 output')
        return []

    try:
        requested = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        warn(f'Malformed REQUIRED_RESOURCES JSON: {exc}')
        return []

    validated = []
    dropped = []
    on_demand_count = 0
    available_ticket_ids = {t['id'] for t in available.jira_tickets}
    available_mr_ids = {m['id'] for m in available.gitlab_mrs}
    available_filenames = {a['filename'] for a in available.attachments}

    for ticket_id in requested.get('jira_tickets', []):
        if ticket_id in available_ticket_ids:
            validated.append(('jira_ticket', ticket_id))
        elif _JIRA_TICKET_RE.fullmatch(ticket_id):
            dbg(f'Jira ticket {ticket_id} not pre-discovered — fetching on demand')
            validated.append(('jira_ticket', ticket_id))
            on_demand_count += 1
        else:
            dbg(f'Ignoring unknown Jira ticket: {ticket_id}')
            dropped.append(('jira_ticket', ticket_id))

    for mr_id in requested.get('gitlab_mrs', []):
        if mr_id in available_mr_ids:
            validated.append(('gitlab_mr', mr_id))
        elif str(mr_id).lstrip('!').isdigit():
            dbg(f'GitLab MR !{mr_id} not pre-discovered — fetching on demand')
            validated.append(('gitlab_mr', mr_id))
            on_demand_count += 1
        else:
            dbg(f'Ignoring unknown GitLab MR: {mr_id}')
            dropped.append(('gitlab_mr', mr_id))

    for filename in requested.get('attachments', []):
        if filename in available_filenames:
            validated.append(('attachment', filename))
        else:
            dbg(f'Ignoring unknown attachment: {filename}')
            dropped.append(('attachment', filename))

    log(f'Required resources: {len(validated)} validated '
        f'({on_demand_count} on-demand) out of '
        f'{sum(len(v) for v in requested.values())} requested')

    if debug_out is not None:
        debug_out.update({
            'available': {
                'jira_tickets': sorted(available_ticket_ids),
                'gitlab_mrs': sorted(available_mr_ids),
                'attachments': sorted(available_filenames),
            },
            'requested': requested,
            'validated': validated,
            'dropped': dropped,
        })

    return validated


def _write_resources_debug_cache(debug_info):
    """Write requested/validated/dropped resource info to gen_cache for debugging.

    Purely a debugging artifact — never raises, never blocks generation.
    """
    if not debug_info:
        return
    try:
        exit_code, branch_out, _ = run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
        if exit_code != 0:
            return
        cache_dir = os.path.join(
            _CACHE_DIR, _sanitize_branch_name(branch_out.strip()), 'gen_cache')
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, 'resources.json')
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(debug_info, f, indent=2)
    except OSError as exc:
        dbg(f'Resources debug cache write failed (non-critical): {exc}')


# -- Download helpers -------------------------------------------------------

_MAX_TEXT_SIZE = 50_000
_MAX_DIFF_SIZE = 50_000


async def _download_jira_ticket(ticket_id, original_ticket):
    """Fetch a linked Jira ticket + its attachments. Returns list of Evidence."""
    summary_line, content = await jira_summary(ticket_id)
    if not content:
        warn(f'Could not fetch linked ticket {ticket_id}')
        return []

    evidences = [Evidence(
        source_type='jira_ticket',
        source_id=ticket_id,
        title=summary_line,
        relation='linked',
        mentioned_in=f'{original_ticket} Linked Issues',
        content=content[:_MAX_TEXT_SIZE],
    )]

    # Also download attachments discovered during sub-resource discovery
    exit_code, raw, _ = await run_async(['jira', 'issue', 'view', ticket_id, '--raw'])
    if exit_code == 0:
        sub_resources = _parse_jira_links(raw)
        for attachment_meta in sub_resources.attachments:
            attachment_evidence = await _download_attachment(attachment_meta, ticket_id)
            if attachment_evidence:
                evidences.append(attachment_evidence)
                dbg(f"Fetched attachment from {ticket_id}: "
                    f"{attachment_meta['filename']}")

    return evidences


async def _download_gitlab_mr(mr_id, original_ticket, project=''):
    """Fetch GitLab MR metadata + description + diff. Returns Evidence or None.

    project='' means current project; otherwise passes --repo for cross-project.
    """
    if not find_tool('glab'):
        return None

    # Metadata + description
    cmd = ['glab', 'mr', 'view', mr_id, '--output', 'json']
    if project:
        cmd += ['--repo', project]
    exit_code, meta_json, _ = await run_async(cmd)
    title = ''
    description = ''
    if exit_code == 0:
        try:
            meta = json.loads(meta_json)
            title = meta.get('title', '')
            description = meta.get('description', '')
        except json.JSONDecodeError:
            pass

    # Diff
    diff_cmd = ['glab', 'mr', 'diff', mr_id, '--color=never']
    if project:
        diff_cmd += ['--repo', project]
    exit_code, diff_text, _ = await run_async(diff_cmd)
    if exit_code != 0:
        warn(f'Could not fetch diff for MR !{mr_id}')
        diff_text = ''

    # Combine MR body + diff as evidence content
    content_parts = []
    if description:
        content_parts.append(f'MR Description:\n{description}')
    if diff_text:
        content_parts.append(f'Diff:\n{diff_text[:_MAX_DIFF_SIZE]}')
    combined_content = '\n\n'.join(content_parts)

    source_id = f'{project}!{mr_id}' if project else mr_id
    return Evidence(
        source_type='gitlab_mr',
        source_id=source_id,
        title=title,
        relation='mentioned',
        mentioned_in=f'{original_ticket} comments',
        content=combined_content[:_MAX_TEXT_SIZE],
    )


async def _download_attachment(attachment_meta, original_ticket):
    """Download a Jira attachment. Returns Evidence or None."""
    filename = attachment_meta['filename']
    mime_type = attachment_meta.get('type', '')
    url = attachment_meta.get('url', '')
    size = attachment_meta.get('size', 0)

    if not url:
        return None

    token = os.environ.get('JIRA_API_TOKEN', '')
    if not token:
        warn('JIRA_API_TOKEN not set — cannot download attachments')
        return None

    is_image = mime_type.startswith('image/')
    is_text = not is_image and size < _MAX_TEXT_SIZE

    # aiohttp ClientSession docs: "session = aiohttp.ClientSession();
    # async with session.get(url) as resp: data = await resp.read()"
    # (docs.aiohttp.org/en/stable/client_quickstart.html)
    headers = {'Authorization': f'Bearer {token}'}
    try:
        async with aiohttp.ClientSession(headers=headers) as session, \
                session.get(url) as resp:
            raw_bytes = await resp.read()
    except (aiohttp.ClientError, OSError) as exc:
        warn(f'Failed to download attachment {filename}: {exc}')
        return None

    if is_image:
        return Evidence(
            source_type='image',
            source_id=filename,
            title=filename,
            relation='attachment',
            mentioned_in=f'{original_ticket} attachments',
            image_bytes=raw_bytes,
            mime_type=mime_type,
        )

    if is_text:
        text = raw_bytes.decode('utf-8', errors='replace')
        return Evidence(
            source_type='text_file',
            source_id=filename,
            title=filename,
            relation='attachment',
            mentioned_in=f'{original_ticket} attachments',
            content=text[:_MAX_TEXT_SIZE],
        )

    # Video, archive, or large file — mention only
    dbg(f'Skipping non-downloadable attachment: {filename} ({mime_type}, {size} bytes)')
    return None


# -- Main class -------------------------------------------------------------

class ContentExtractor:
    """Fetch all context for plan generation from Jira, GitLab, project docs."""

    def __init__(self, branch, jira_ticket, template_type='default'):
        self.branch = branch
        self.jira_ticket = jira_ticket
        self.template_type = template_type
        self._available = AvailableResources()
        self._jira_raw = ''
        self._diff_base = None  # cached (parent_branch_name, parent_sha)

    async def extract_initial(self):
        """Fetch Jira ticket + branch diffs. Called before step 1.

        Returns PlanContext with all initially available data.
        """
        context = PlanContext(jira_ticket=self.jira_ticket)

        # MR body template + labels/assignees (branch-type dependent)
        mr_template, labels, assignees = template_skeleton(self.template_type, self.jira_ticket)
        context.mr_body_template = mr_template
        context.labels = labels
        context.assignees = assignees

        # Jira
        if self.jira_ticket and find_tool('jira'):
            context.jira_summary, context.jira_content = await jira_summary(self.jira_ticket)

            # Raw JSON for link/attachment parsing
            exit_code, raw, _ = await run_async([
                'jira', 'issue', 'view', self.jira_ticket, '--raw',
            ])
            if exit_code == 0:
                self._jira_raw = raw
                self._available = _parse_jira_links(raw)
                dbg(f'Initial resources from {self.jira_ticket}: '
                    f'{len(self._available.jira_tickets)} tickets, '
                    f'{len(self._available.gitlab_mrs)} MRs, '
                    f'{len(self._available.attachments)} attachments')
                # Discover sub-resources from all 1st-level links
                await _discover_sub_resources(self._available)
                log(f'Available resources (after discovery): '
                    f'{len(self._available.jira_tickets)} tickets, '
                    f'{len(self._available.gitlab_mrs)} MRs, '
                    f'{len(self._available.attachments)} attachments')
                context.available_resources = self._available

        # Branch diffs — use nearest parent branch as diff base
        parent_name, parent_sha = self._get_diff_base()
        context.parent_branch_name = parent_name
        context.parent_branch_sha = parent_sha
        context.branch_diffs = self._get_branch_diffs()
        context.commit_messages = self._get_commit_messages()

        # Project docs for fact-checking
        context.file_paths_manifest = self._load_docs_manifest()

        return context

    def parse_required_resources(self, step1_output):
        """Parse REQUIRED_RESOURCES from step 1 output.

        Returns list of (type, id_or_filename) tuples validated against
        available resources.
        """
        debug_info = {}
        validated = _parse_required_resources(step1_output, self._available, debug_info)
        _write_resources_debug_cache(debug_info)
        return validated

    async def _handle_jira_ticket(self, resource_id):
        """Download a linked Jira ticket. Returns list of Evidence."""
        return await _download_jira_ticket(resource_id, self.jira_ticket)

    async def _handle_gitlab_mr(self, resource_id):
        """Download a GitLab MR. Returns list of Evidence."""
        mr_meta = next((m for m in self._available.gitlab_mrs
                        if m['id'] == resource_id), {})
        project = mr_meta.get('project', '')
        evidence = await _download_gitlab_mr(resource_id, self.jira_ticket, project)
        return [evidence] if evidence else []

    async def _handle_attachment(self, resource_id):
        """Download a Jira attachment. Returns list of Evidence."""
        attachment_meta = next(
            (a for a in self._available.attachments
             if a['filename'] == resource_id),
            None,
        )
        if not attachment_meta:
            return []
        evidence = await _download_attachment(attachment_meta, self.jira_ticket)
        return [evidence] if evidence else []

    _DOWNLOAD_HANDLERS = {
        'jira_ticket': _handle_jira_ticket,
        'gitlab_mr': _handle_gitlab_mr,
        'attachment': _handle_attachment,
    }

    async def download_references(self, required):
        """Download all required references. Returns list of Evidence."""
        evidences = []

        for resource_type, resource_id in required:
            handler = self._DOWNLOAD_HANDLERS.get(resource_type)
            if handler is None:
                dbg(f'Unknown resource type: {resource_type}')
                continue
            for evidence in await handler(self, resource_id):
                evidences.append(evidence)
                log(f'Downloaded: {evidence.source_type} {evidence.source_id}')

        return evidences

    def _get_diff_base(self) -> tuple:
        """Return (parent_branch_name, parent_sha) for the nearest non-default
        ancestor of HEAD. Cached per-extractor instance.
        """
        if self._diff_base is None:
            self._diff_base = detect_nearest_parent_branch()
        return self._diff_base

    def _get_branch_diffs(self):
        """Get diffs between nearest parent branch and HEAD."""
        _, parent_sha = self._get_diff_base()
        if not parent_sha:
            return ''
        exit_code, diff, _ = run(['git', 'diff', f'{parent_sha}..HEAD'])
        return diff if exit_code == 0 else ''

    def _get_commit_messages(self):
        """Get commit messages since nearest parent branch."""
        _, parent_sha = self._get_diff_base()
        if not parent_sha:
            return ''
        exit_code, messages, _ = run([
            'git', 'log', '--format=%H %s', f'{parent_sha}..HEAD',
        ])
        return messages if exit_code == 0 else ''

    def _get_merge_base(self):
        """Find merge base — delegates to _get_diff_base for parent SHA."""
        _, sha = self._get_diff_base()
        return sha or None

    def _load_docs_manifest(self):
        """Load project docs for fact-checking (productname_files.rst etc.)."""
        """Load project docs for fact-checking (productname_files.rst etc.)."""
        docs_path = os.path.join('docs', 'sphinx', 'src', 'productname_files.rst')
        docs_path = os.path.join('docs', 'sphinx', 'src', 'productname_files.rst')
        try:
            with open(docs_path, encoding='utf-8') as f:
                return f.read()
        except OSError:
            dbg(f'Docs manifest not found: {docs_path}')
            return ''
