#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Plan generator — 4-step AI pipeline that produces BRANCH_PLAN.md from context.

Step 1: Fill MR body from Jira + diffs + identify required resources  (Sonnet)
Step 2: Enhance with plan sections (parallel: download required resources)    (Sonnet)
Step 3: Enrich with downloaded evidence (batch or loop)                        (Opus)
Step 4: Validate + polish — TODOs, compliance, linkification, mermaid repair   (Opus)
"""

import asyncio
import contextlib
import json
import os
import re
import time

from git_hooks_impl.entry_points.commands import compile_mermaid
from git_hooks_impl.logger import dbg, err, log, warn
from git_hooks_impl.plan import cache as plan_cache
from git_hooks_impl.plan.cache import _CACHE_DIR, _sanitize_branch_name
from git_hooks_impl.plan.parser import embed_meta, extract_meta, strip_meta
from git_hooks_impl.progress import run_with_progress
from git_hooks_impl.utils import PLAN_FILE, run

_PROMPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'prompt_templates', 'PlanGen',
)

# Step 3 batch threshold — if total text + plan exceeds this, loop instead
_BATCH_THRESHOLD_CHARS = 600_000

# Defensive outer bound against a hung mermaid-check subprocess (see _run_mermaid_check)
_MERMAID_CHECK_TIMEOUT_SECONDS = 120

_CONTENT_RE = re.compile(
    r'<!-- PLAN_CONTENT -->\s*(.*?)\s*<!-- PLAN_STEP: OK -->',
    re.DOTALL,
)
_ABORT_RE = re.compile(r'<!-- PLAN_STEP: ABORT \| (.+?) -->')
_REQUIRED_RE = re.compile(
    r'<!-- REQUIRED_RESOURCES -->\s*(.*?)\s*<!-- /REQUIRED_RESOURCES -->',
    re.DOTALL,
)

# System message shared by all steps
_SYSTEM_MESSAGE = (
    'You are generating a BRANCH_PLAN.md for a software development branch. '
    'OUTPUT FORMAT REQUIREMENT: You MUST wrap your entire response in '
    '<!-- PLAN_CONTENT --> (opening, on its own line) and '
    '<!-- PLAN_STEP: OK --> (closing, on its own line). '
    'Do NOT begin with any heading or text before <!-- PLAN_CONTENT -->. '
    'Responses without these exact markers are discarded by the parser. '
    'RULES: '
    'Preserve ALL facts, numbers, dates, and references from previous steps. '
    'Do NOT paraphrase metrics (keep exact numbers from Jira). '
    'Do NOT rephrase the title (set in step 1, frozen for all steps). '
    'Only add new information — never remove or rewrite existing content. '
    'Observations from evidence are marked with `> [!note]`.'
)


def _load_prompt(filename):
    """Load a prompt template from prompt_templates/PlanGen/."""
    path = os.path.join(_PROMPTS_DIR, filename)
    with open(path, encoding='utf-8') as f:
        return f.read()


def _extract_content(response):
    """Extract plan content between PLAN_CONTENT/PLAN_STEP tags.

    Returns the content string, or '' if tags are missing or ABORT.
    """
    abort_match = _ABORT_RE.search(response)
    if abort_match:
        reason = abort_match.group(1)
        warn(f'Plan step aborted: {reason}')
        return ''

    content_match = _CONTENT_RE.search(response)
    if content_match:
        return content_match.group(1).strip()

    # No start marker — try stripping just the end marker
    if '<!-- PLAN_STEP: OK -->' in response:
        dbg('No PLAN_CONTENT start marker — using content before OK tag')
        end_index = response.find('<!-- PLAN_STEP: OK -->')
        return response[:end_index].strip()

    warn('Plan step has no quality gate markers — rejecting output')
    return ''


def _extract_required_resources(response):
    """Extract REQUIRED_RESOURCES JSON from step 1 response."""
    match = _REQUIRED_RE.search(response)
    if not match:
        return {}
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        warn(f'Malformed REQUIRED_RESOURCES: {exc}')
        return {}


def _format_evidence_block(evidence):
    """Format one evidence item for prompt injection."""
    header = (
        f'Source: {evidence.source_type} {evidence.source_id}\n'
        f'Relation: {evidence.relation}\n'
        f'Mentioned in: {evidence.mentioned_in}\n'
        f'Title: {evidence.title}\n'
    )
    if evidence.content:
        return f'{header}Content:\n{evidence.content}'
    if evidence.image_bytes:
        return f'{header}[Image — passed separately via multimodal]'
    return header


async def _run_mermaid_check(plan_text, plan_file_path):
    """Validate every mermaid block in plan_text. Return error output or ''.

    Runs compile_mermaid.compile_report() in a thread. Its node/npm
    subprocess.run() calls have no internal timeout, so asyncio.wait_for
    gives the caller a defensive outer bound against a hung subprocess.
    """
    candidate_path = plan_file_path + '.mermaid_check'
    try:
        with open(candidate_path, 'w', encoding='utf-8') as f:
            f.write(plan_text)
    except OSError as exc:
        dbg(f'mermaid check: cannot write temp file: {exc}')
        return ''
    try:
        returncode, output_text = await asyncio.wait_for(
            asyncio.to_thread(compile_mermaid.compile_report, [candidate_path]),
            timeout=_MERMAID_CHECK_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        dbg('mermaid check timed out')
        return ''
    except OSError as exc:
        dbg(f'mermaid check error: {exc}')
        return ''
    finally:
        with contextlib.suppress(OSError):
            os.remove(candidate_path)
    if returncode == 0:
        return ''
    return output_text


class PlanGenerator:
    """Generate BRANCH_PLAN.md via a 4-step AI pipeline.

    Uses AIProvider for all AI calls. ContentExtractor handles fetching.
    Each step flushes to BRANCH_PLAN.md and gen_cache for resume.
    """

    def __init__(self, context, provider, extractor=None, plan_file=None,
                 force=False, interactive=True):
        self.context = context
        self.provider = provider
        self.extractor = extractor
        self.plan_file = plan_file or PLAN_FILE
        self.evidences = []
        self.force = force
        self.interactive = interactive

    async def _text(self, prompt, label, system='', model_override=None):
        """Call provider.text_completion with progress display."""
        self._save_prompt_cache(label, prompt)
        return await run_with_progress(
            lambda: self.provider.text_completion(
                prompt, system=system, model_override=model_override),
            label)

    async def _vision(self, prompt, images, label, system='', model_override=None):
        """Call provider.vision_completion with progress display."""
        self._save_prompt_cache(label, prompt, image_count=len(images))
        return await run_with_progress(
            lambda: self.provider.vision_completion(
                prompt, images, system=system, model_override=model_override),
            label)

    def _save_prompt_cache(self, label, prompt, image_count=None):
        """Write the exact prompt sent to the model to gen_cache/stepN_prompt.md.

        Purely a debugging artifact — never raises, never blocks generation.
        """
        try:
            step_match = re.search(r'Step (\d+)/', label)
            if not step_match:
                return
            exit_code, branch_out, _ = run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
            if exit_code != 0:
                return
            cache_dir = os.path.join(
                _CACHE_DIR, _sanitize_branch_name(branch_out.strip()), 'gen_cache')
            os.makedirs(cache_dir, exist_ok=True)
            cache_path = os.path.join(cache_dir, f'step{step_match.group(1)}_prompt.md')
            content = prompt
            if image_count is not None:
                content = f'<!-- {image_count} images attached -->\n{content}'
            with open(cache_path, 'w', encoding='utf-8') as f:
                f.write(content)
        except OSError as exc:
            dbg(f'Prompt cache write failed (non-critical): {exc}')

    async def generate(self):
        """Run the full pipeline with cache-resume logic. Returns plan content or ''."""
        if not self.provider.is_available():
            dbg('AI provider not available — skipping plan generation')
            return ''

        # Resolve current branch for cache operations
        exit_code, branch_out, _ = run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
        current_branch = branch_out.strip() if exit_code == 0 else ''

        cached = plan_cache.load_gen_cache(current_branch)

        if len(cached) == 4:
            if self.force:
                log('--force: discarding complete cache, regenerating from step 1')
                plan_cache.invalidate_gen_cache(current_branch)
                cached = {}
            elif not self.interactive:
                dbg('Non-interactive: complete cache present — returning existing BRANCH_PLAN.md')
                try:
                    with open(self.plan_file, encoding='utf-8') as f:
                        return f.read()
                except OSError:
                    return cached.get(4, '')

        first_missing = next((s for s in range(1, 5) if s not in cached), 1)
        if 0 < len(cached) < 4:
            log(f'Resuming from step {first_missing}/4 '
                f'(steps {sorted(cached.keys())} cached)')

        start_time = time.monotonic()
        log('Plan generation starting...')
        warn('Plan generation in progress (~5-15 min). '
             'Do not edit .ai/BRANCH_PLAN.md until complete.')

        # Step 1: Fill MR body + identify required resources
        if 1 in cached:
            filled_body = strip_meta(cached[1])
            required = _extract_required_resources(cached[1])
        else:
            filled_body, required = await self._step1_fill_body()
            if not filled_body:
                return ''
            self._flush(filled_body, 1)

        # Start downloads in parallel with step 2 (skip if resuming past step 4)
        download_task = None
        if required and self.extractor and first_missing <= 4:
            download_task = asyncio.create_task(self._wait_for_download(required))

        # Step 2: Enhance with plan sections
        if 2 in cached:
            plan = strip_meta(cached[2])
            if not plan:
                err('Step 2 cache load failed — pipeline aborted')
                return ''
        else:
            plan = await self._step2_enhance(filled_body)
            if not plan:
                err('Step 2 failed — pipeline aborted')
                return ''
            self._flush(plan, 2)

        # Wait for downloads
        if download_task:
            await download_task

        # Step 3: Evidence enrichment
        if 3 in cached:
            plan = strip_meta(cached[3])
            if not plan:
                err('Step 3 cache load failed — pipeline aborted')
                return ''
        elif self.evidences:
            plan = await self._step3_enrich(plan)
            if not plan:
                err('Step 3 failed — pipeline aborted')
                return ''
            self._flush(plan, 3)

        # Step 4: Validate + polish (merged from old 4+5+6)
        if 4 in cached:
            plan = strip_meta(cached[4])
            if not plan:
                err('Step 4 cache load failed — pipeline aborted')
                return ''
        else:
            plan = await self._step4_validate_polish(plan)
            if not plan:
                err('Step 4 failed — pipeline aborted')
                return ''
            self._flush(plan, 4)

        elapsed = time.monotonic() - start_time
        elapsed_min = int(elapsed) // 60
        elapsed_sec = int(elapsed) % 60
        log(f'Plan generation complete: {len(plan)} chars, '
            f'total time {elapsed_min}m {elapsed_sec}s')
        return plan

    # -- Steps --------------------------------------------------------------

    async def _step1_fill_body(self):
        """Fill MR body template from Jira context. Returns (body, required_dict)."""
        log('Step 1/4: Filling MR body...')
        prompt = _load_prompt('step1_fill_body.md')
        prompt = prompt.replace('{{MR_BODY_TEMPLATE}}', self.context.mr_body_template)
        prompt = prompt.replace('{{JIRA_CONTENT}}', self.context.jira_content)
        parent_name = self.context.parent_branch_name or 'master'
        prompt = prompt.replace('{{PARENT_BRANCH_NAME}}', parent_name)
        diff_stats = (self.context.current_branch_diff_stats
                      or self.context.branch_diffs
                      or '(no diff stats)')
        if self.context.stacked_branch_warning:
            diff_stats = self.context.stacked_branch_warning + '\n\n' + diff_stats
        prompt = prompt.replace('{{BRANCH_DIFFS}}', diff_stats)
        prompt = prompt.replace(
            '{{AVAILABLE_RESOURCES}}',
            self.context.available_resources.to_json(),
        )

        response = await self._text(prompt, 'Step 1/4: Filling MR body...',
                               system=_SYSTEM_MESSAGE,
                               model_override='claude-sonnet-4-6')
        body = _extract_content(response)
        required = _extract_required_resources(response)

        if body:
            list_count = sum(len(v) for v in required.values() if isinstance(v, list))
            log(f'Step 1/4 done: {len(body)} chars, {list_count} resources requested')
        else:
            warn('Step 1 failed')

        return body, required

    async def _step2_enhance(self, filled_body):
        """Enhance filled body with plan sections."""
        prompt = _load_prompt('step2_enhance.md')
        prompt = prompt.replace('{{PLAN_TEMPLATE}}', self.context.plan_template)
        prompt = prompt.replace('{{PLAN_RULES}}', self.context.plan_rules)
        prompt = prompt.replace('{{FILLED_BODY}}', filled_body)

        response = await self._text(prompt,
                               'Step 2/4: Enhancing plan...',
                               system=_SYSTEM_MESSAGE,
                               model_override='claude-sonnet-4-6')
        plan = _extract_content(response)

        if plan:
            log(f'Step 2/4 done: {len(plan)} chars')
        else:
            err('Step 2 failed')

        return plan

    async def _step3_enrich(self, plan):
        """Enrich plan with downloaded evidence. Batch or loop."""
        text_evidences = [e for e in self.evidences if e.content]
        image_evidences = [e for e in self.evidences if e.image_bytes]
        total_text = sum(len(e.content) for e in text_evidences)

        total_chars = len(plan) + total_text
        can_batch = total_chars < _BATCH_THRESHOLD_CHARS

        if can_batch:
            return await self._step3_batch(plan, text_evidences, image_evidences)
        return await self._step3_loop(plan, text_evidences, image_evidences)

    async def _step3_batch(self, plan, text_evidences, image_evidences):
        """Feed all evidence in one call."""
        log(f'Step 3/4: Enriching plan (batch, {len(text_evidences)} text + '
            f'{len(image_evidences)} images)...')

        prompt = _load_prompt('step3_evidence.md')
        evidence_blocks = '\n\n---\n\n'.join(
            f'EVIDENCE {i + 1}/{len(text_evidences)}:\n{_format_evidence_block(e)}'
            for i, e in enumerate(text_evidences)
        )
        prompt = prompt.replace('{{PLAN}}', plan)
        prompt = prompt.replace('{{EVIDENCE_BLOCKS}}', evidence_blocks)
        prompt = prompt.replace('{{AVAILABLE_EVIDENCE}}', json.dumps(
            [{'id': e.source_id, 'type': e.source_type} for e in self.evidences],
        ))

        # Use vision if images, text otherwise
        if image_evidences:
            images = [(e.image_bytes, e.mime_type) for e in image_evidences]
            response = await self._vision(prompt, images,
                                    'Step 3/4: Enriching (batch)...',
                                    system=_SYSTEM_MESSAGE,
                                    model_override='claude-opus-4-6')
        else:
            response = await self._text(prompt, 'Step 3/4: Enriching (batch)...',
                                  system=_SYSTEM_MESSAGE,
                                  model_override='claude-opus-4-6')

        result = _extract_content(response)
        if result:
            log(f'Step 3/4 done: {len(result)} chars')
        else:
            err('Step 3 failed')
        return result

    async def _step3_loop(self, plan, text_evidences, image_evidences):
        """Feed evidence one at a time in a loop."""
        all_evidences = text_evidences + image_evidences
        log(f'Step 3/4: Enriching plan (loop, {len(all_evidences)} items)...')

        for i, evidence in enumerate(all_evidences):
            label = f'{evidence.source_type} {evidence.source_id}'
            log(f'  Enriching ({label}) {i + 1}/{len(all_evidences)}...')

            prompt = _load_prompt('step3_evidence.md')
            prompt = prompt.replace('{{PLAN}}', plan)
            prompt = prompt.replace('{{EVIDENCE_BLOCKS}}',
                                    f'EVIDENCE 1/1:\n{_format_evidence_block(evidence)}')
            prompt = prompt.replace('{{AVAILABLE_EVIDENCE}}', json.dumps(
                [{'id': evidence.source_id, 'type': evidence.source_type}],
            ))

            step_label = f'Step 3/4: Enriching ({label})...'
            if evidence.image_bytes:
                response = await self._vision(
                    prompt, [(evidence.image_bytes, evidence.mime_type)],
                    step_label, system=_SYSTEM_MESSAGE,
                    model_override='claude-opus-4-6')
            else:
                response = await self._text(prompt, step_label,
                                      system=_SYSTEM_MESSAGE,
                                      model_override='claude-opus-4-6')

            result = _extract_content(response)
            if result:
                plan = result
            else:
                err(f'Step 3 failed on evidence {label}')
                return ''

        log(f'Step 3/4 done: {len(plan)} chars')
        return plan

    async def _step4_validate_polish(self, plan):
        """Validate + polish in one pass: TODOs, compliance, linkification, mermaid."""
        log('Step 4/4: Validating and polishing...')
        mermaid_errors = await _run_mermaid_check(plan, self.plan_file)
        prompt = _load_prompt('step4_validate_polish.md')
        prompt = prompt.replace('{{PLAN}}', plan)
        prompt = prompt.replace('{{MERMAID_ERRORS}}', mermaid_errors)
        prompt = prompt.replace('{{PLAN_TEMPLATE}}', self.context.plan_template)
        prompt = prompt.replace('{{MR_BODY_TEMPLATE}}', self.context.mr_body_template)
        prompt = prompt.replace('{{DOCS_MANIFEST}}',
                                self.context.file_paths_manifest or '(no docs)')
        prompt = prompt.replace('{{JIRA_TICKET}}', self.context.jira_ticket)
        prompt = prompt.replace('{{JIRA_SUMMARY}}', self.context.jira_summary)

        response = await self._text(prompt, 'Step 4/4: Validating and polishing...',
                               system=_SYSTEM_MESSAGE,
                               model_override='claude-opus-4-6')
        result = _extract_content(response)

        if result:
            log(f'Step 4/4 done: {len(result)} chars')
        else:
            err('Step 4 failed')
        return result

    # -- Helpers ------------------------------------------------------------

    async def _wait_for_download(self, required, timeout=300):
        """Wait for async download of required resources, with timeout.

        asyncio.wait_for docs: "coroutine asyncio.wait_for(aw, timeout) —
        Wait for the aw awaitable to complete with a timeout."
        (docs.python.org/3/library/asyncio-task.html#asyncio.wait_for)
        """
        download_task = asyncio.create_task(self._download_worker_async(required))
        try:
            await asyncio.wait_for(download_task, timeout=timeout)
        except asyncio.TimeoutError:
            download_task.cancel()
            log('download timeout')

    async def _download_worker_async(self, required):
        """Download required resources using the extractor."""
        if not self.extractor:
            return
        validated = self.extractor.parse_required_resources(
            f'<!-- REQUIRED_RESOURCES -->\n{json.dumps(required)}\n<!-- /REQUIRED_RESOURCES -->')
        self.evidences = await self.extractor.download_references(validated)
        log(f'Downloads complete: {len(self.evidences)} evidences')

    def _flush(self, plan, step_number):
        """Write plan to disk + gen_cache for resume.

        Preserves the meta block from disk (hashes, UUID) so
        run_with_progress can update it between steps.
        """
        # Preserve existing meta block (has UUID from prior steps)
        try:
            with open(self.plan_file, encoding='utf-8') as f:
                existing_meta = extract_meta(f.read())
        except OSError:
            existing_meta = {}
        if existing_meta:
            plan = embed_meta(plan, **existing_meta)

        # Flush to BRANCH_PLAN.md
        try:
            os.makedirs(os.path.dirname(self.plan_file), exist_ok=True)
            with open(self.plan_file, 'w', encoding='utf-8') as f:
                f.write(plan)
        except OSError as exc:
            warn(f'Failed to flush plan: {exc}')

        # Flush to gen_cache
        try:
            exit_code, branch_out, _ = run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
            if exit_code == 0:
                cache_dir = os.path.join(
                    _CACHE_DIR, _sanitize_branch_name(branch_out.strip()), 'gen_cache'
                )
                os.makedirs(cache_dir, exist_ok=True)
                cache_path = os.path.join(cache_dir, f'step{step_number}.md')
                with open(cache_path, 'w', encoding='utf-8') as f:
                    f.write(plan)
                dbg(f'Cached step {step_number} output ({len(plan)} chars)')
        except OSError as exc:
            dbg(f'Cache flush failed (non-critical): {exc}')
