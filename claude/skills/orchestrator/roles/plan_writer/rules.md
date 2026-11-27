# Plan Writer rules

How the plan works, section formats, parser constraints, and the per-edit
rules plan-writer enforces.

## Who triggers plan-writer

A mandatory dispatch target for three workflows:

- **gitter / precommit / Phase 3.1** - every commit (G7-mandatory, per the gitter workflow spawn-check)
- **fixer / bugfix / wrap-up** - after the fix lands, record the fix decision
- **featurer / introduction / document** - after the feature lands, record what was built

A role needing plan-writer requests the dispatch through the orchestrator via
`SendMessage` (AGT-1). "Not available" is a blocker to surface, never grounds
to bypass the dispatch.

## Plan-writer scope

Owns standalone repo-prose documents about the project's plan, architecture
or usage:

- `.ai/BRANCH_PLAN.md`, the primary per-branch plan file
- Root READMEs (`README.md`, `README - *.md`, any other top-level `*.md`)
- Module READMEs (`<dir>/README.md` anywhere in the repo)
- Hand-written design docs (`docs/**/*.md`, `*.txt` documentation)

Hands off everything else to the role owning that artifact class:

- **Skill-tree files** (`claude/skills/**/*.md`, `claude/agents/*.md`, `claude/hooks/*`) - orchestrator, per DEL-1.
- **Docstrings and comments inside production or test code** - they land with the code change: coder for production, tester for tests.
- **Scripts, production code, tests** (`*.sh`, `*.py`, `*.ps1`, build scripts, `cmake`, `test_*.py`, `*_test.cpp`) - coder. Plan-writer surfaces the needed change to the orchestrator for a coder dispatch.

**Plan-writer never writes under `.ai/cache/`** - PLAN-3 NO-CACHE-EDITS in
`rules/plan.md` binds it explicitly. The one plan file it edits is the real
`.ai/BRANCH_PLAN.md` in the working tree. `cached_BRANCH_PLAN.md` is a
hook-owned mirror, readable by plan-writer and by any sub-agent it dispatches,
writable by neither.

## How the plan works

- `.ai/BRANCH_PLAN.md` is the primary instruction set. Read it before starting.
- It syncs to the MR description on every push; the pre-push hook fires even with no new commits.
- On checkout: a fast local cache swap from `.ai/cache/{sanitized_branch}/cached_BRANCH_PLAN.md`, hook-performed.
- On pull or rebase: restores from the MR, may detect remote edits, prunes stale caches.
- Hash-based change detection: a plan edited on GitLab raises a conflict resolution dialog on the next pull or rebase, never on checkout.

## MR body mapping

- `## Description` feeds the MR body's Description section on push.
- `## Areas of Impact / Risks` feeds the MR body's Areas of Impact section.
- The push hook syncs both, so both stay current.

## Decisions Log format

- One line each: `- <domain> - <short summary> - <important details>`
- `- Architecture - Shell entry + Python package - matching commit-msg convention`
- `- Cache - checkout=MOVE push=COPY - cache survives restore, self-healing`
- Category shortcuts need a `Categories:` line right after `## Decisions Log`, e.g. `Categories: A=Architecture, C=Cache, L=Logging, D=Docs, T=Testing`, then `- A - Shell entry + Python package - matching commit-msg convention`.
- Without that line, full domain names throughout. All entries take one form or the other, never mixed.
- Append-only: entries go at the end.

## Implementation Plan lifecycle

Current work only, the active TODO list. On every commit, for each completed
task:

1. Check the box, `- [ ]` to `- [x]`, leaving the item text intact. The box
   already marks it done, so strikethrough only duplicates that and costs
   readability. Evidence goes in trailing parentheses or a nested sub-bullet.
2. Append a Decisions Log entry. Even a trivial fix produces one.
3. Once every checkbox in a subsection is checked, remove that whole subsection.

New work adds TODO items here.

## HTML comments in plan text

The parser works on raw text and does not respect backticks or code fences, so
an HTML comment tag written literally in plan text is matched and processed
wherever it sits.

**Never write `<!--` in visible plan text.** Describe the tag in plain English,
"discussion section end marker".

## Plan template - section fill guidance

Each project supplies its own plan-generation rules in its CLAUDE.md or
`.git-hooks/` equivalent. The standard sections are Context, Description,
Areas of Impact, Success Criteria, Architecture, Implementation Plan and
Decisions Log.

**Manual testing plan** - step-by-step verification of every user-facing
workflow, in a collapsed `<details>` section. Rules in manual.md.

Project-specific paths, generated artifacts and submodule layout belong in the
project's own CLAUDE.md or BRANCH_PLAN.md, not in this skill.

## Working with the plan

- Read the plan before committing: confirm the current task matches what is being committed, update checkboxes and the Decisions Log.
- Plan items say what the system can do, not how it was built. Steps, fixes and test counts live in git log and the Decisions Log.
  - Bad: "Add input_data param to run() in utils.py - uses input= ..."
  - Good: "Pipe prompts via stdin to bypass platform line-length limits"
- Update "Areas of Impact / Risks" as new failure modes surface.
- Fill "Important File Paths" with key files as they are found, so a later session on the branch does not re-search.
- A discussion goes under `## Discussions` (plural, created if absent), `####` for sub-headings inside a body, and the discussion-end marker on its own line. PW-6 carries the full contract.

## Plan maintenance workflow

See [plan maintenance workflow](./maintenance/workflow.md) for the 3-phase
audit-fix-review pipeline.

---

## Diagram Rendering

**Statement:** Every BRANCH_PLAN.md diagram is Mermaid, wrapped in a `<details><summary>Title</summary>...</details>` spoiler block.
- Bad: ASCII box-drawing (`+--+`, `|`) for a plan diagram, or a diagram inline with no spoiler wrapper.

---

## Codebase Improvement Candidates

**Statement:** A codebase-wide improvement candidate - a pattern appearing N times and worth fixing systemically - is recorded in project memory and in BRANCH_PLAN.md's visible `## Codebase Improvement Candidates` section.
- Memory is invisible to reviewers and stakeholders, so memory alone does not capture it.

---

# Per-edit rules (PW-2 .. PW-7)

These govern every plan-writer edit pass and are referenced externally by ID,
so the numbering holds. Scope is the "Plan-writer scope" section above, not a
numbered rule.

## PW-2: APPEND-ONLY-LOG

**Statement:** A new Decisions Log entry goes below the last existing line, never inserted between or above them.

## PW-3: FACTS-AND-INTENTIONS

**Statement:** The plan body holds facts - observed behaviour, measured values, real paths, configuration present in the code, decisions made - and intentions, what the code does now or what the MR deliberately changes, stated as commitments.
- Each sentence answers one of: what the code does today, what this MR changes, what was observed or specified, what was deliberately decided. A sentence answering none is speculation and goes.
- "expected to fire / may fire / should fire / will fire": write what the kernel delivers or does not deliver, or what the code subscribes to.
- "may behave / might behave / should behave": write the measured behaviour, or drop it.
- "if X then Y / unless X / could regress": drop, unless X has actually occurred.
- "must be verified / unverified / design-time-unverified": state the open question as a fact ("Behavior on Win10 LTSC is not yet measured"), or the resolution as a fact.
- "claimed / allegedly / suspected / presumed / hypothesized / likely / presumably": no place in a plan body.
- Carve-out: the Decisions Log is append-only history, so an entry may carry the "expected" or "hypothesized" wording that was true when it was logged.

## PW-4: NO-LOCAL-DETAILS

**Statement:** BRANCH_PLAN.md is the team-facing MR artifact, so it reads the same on any machine and survives rebases, branch renames and backup-ref deletion; a spawn prompt offering a machine-specific detail gets it rephrased in branch-portable terms, not copied.

Forbidden in any section, the Decisions Log included:

- Commit SHAs, full or short - they change on every rebase and cherry-pick
- Backup ref names (`refs/heads/backup/<date>`) - local-only, deleted after the recovery window
- Absolute local paths (`C:\Users\<name>\...`, `/Users/<name>/...`) - they leak the machine layout
- Build directory paths (`build/x64/...`) outside the agreed `PROJECTNAME_BUILD.md` convention
- Local agent IDs, task IDs, temp file paths from sub-agent runs
- Force-push output, git stash names, dangling-commit warnings
- Compiler version strings, MSBuild verbose output, lint-staged log lines
- `.ai/cache/` paths of any kind, another branch's cached plan snapshot included

Allowed, all team-portable: branch names, quoted commit subject lines, paths
relative to the repo root, code constants by name (`kKeywordMatchAll`,
`EVENT_TRACE_REAL_TIME_MODE`), function and method names, docs URLs.

- A prompt saying "add an entry mentioning new SHAs ABC123 / DEF456" produces an entry giving which commits in the (N/M) series were reworded, their new subject lines quoted, and why - with the SHAs omitted. Traceability comes from the MR diff plus those subject lines.
- Backup refs and recovery procedures belong in the session log, not the plan. They name one machine's local state for the length of a recovery window, which a reader months later cannot reach.
- A Decisions Log entry needing a prior branch's design cites that branch's merge request, `<project>!<iid>` (`kragle/reponame!12080`), whose description mirrors the branch's plan and is reachable by everyone. Look it up with `glab mr list --search "<TICKET>"` or `glab api "projects/<project>/merge_requests?search=<TICKET>&in=title"` first; never guess an MR number.
- A Decisions Log entry needing a prior branch's design cites that branch's merge request, `<project>!<iid>` (`kragle/reponame!12080`), whose description mirrors the branch's plan and is reachable by everyone. Look it up with `glab mr list --search "<TICKET>"` or `glab api "projects/<project>/merge_requests?search=<TICKET>&in=title"` first; never guess an MR number.

## PW-5: READABILITY-DEFAULTS

**Statement:** New and rewritten BRANCH_PLAN.md prose carries zero `→` characters, list shape wherever content fits it, and sentences at or under 20 words holding one fact each.
- Arrows scan poorly in plain text and degrade on copy-paste into Jira, GitLab and Slack. Replace by meaning: "X causes Y" / "X produces Y" / "X then Y" for causal flow, "X to Y" for an address path ("OpenProcess to QueryFullProcessImageNameW"), "X becomes Y" for a state transition, one bullet per step for a pipeline, "Steam launching Terraria" for an app-launch chain.
- A sentence with 3+ comma-separated items, more than one nested clause, or a first/second/third sequence becomes a bulleted sub-list.
- Fact-shaped bodies - Description items, Workflow steps, Discussion bodies, Areas of Impact rows - default to a short title plus a sub-list.
- Reasoning-shaped bodies - Risks, Decisions Log entries, Rollout Strategy - may stay paragraph prose, still with zero arrows. Decisions Log entries may run longer, split where natural.
- No hedging and no filler openers: "Note that...", "It is worth mentioning...", "In essence...". Microsoft API docs are the register: short declarative statements.
- A spawn prompt giving an exact replacement structure already encodes the shape; apply it as given. An open-ended prompt ("clean up section X") leaves the shape to these defaults.
- Every plan-writer report states the arrow scan result, "zero `→` characters in new content", and a non-zero count is fixed before reporting done.

## PW-6: DISCUSSIONS-FORMAT

**Statement:** `## Discussions` is auto-posted to GitLab MR discussions on push, and `git_hooks_impl/plan/parser.py` (`find_unposted_discussions()`, `validate_discussions()`) is the canonical contract for its shape.

- Heading is `## Discussions`, plural.
- The discussion-end marker closes the section on its own line after the last thread body. Without it the parser falls back to the next `## ` heading or EOF and pulls trailing `<details>` blocks into the section.
- A thread is `### <title>` with an optional body, and the title carries no order numbering - no `Thread N - `, no `1. `. It becomes the GitLab thread subject.
- Sub-headings inside a thread body are `####`. A `###` there parses as a new thread.
- A thread counts as posted when its title is a markdown link, `### [Title](url)`. A plain-text title is unposted, goes out on the next push, and comes back as a linked title with the body stripped from the plan.
- An unposted thread body carries four `**Label:**` inline sections, bold rather than headings so the body stays one block: **Context:** what prompted this, in a sentence or two; **Decision:** the exact option chosen; **Rationale:** why this option over the alternatives; **Implications:** downstream effects, follow-up work, constraints.
- `validate_discussions()` rejects session-internal history in a body: `commit N`, `Phase <letter>`, `(this turn)`, `(NEW)` <!-- VALIDATED -->, `we then`, `we decided after`, `previously`, `see QN`, `per task #N`.
- Durable references are fine: rule IDs (`WF-9`, `G10`, `PW-6`), file paths (`git_hooks_impl/plan/parser.py`), and the GitLab URLs the hook embeds after posting.

Bad:

```
### Why we picked option B  ← (NEW) (this turn) - forbidden markers  <!-- VALIDATED -->

We decided after commit 3 that Phase C results showed ...
```

Good:

```
### Option B selected for ETW flush strategy

**Context:** two strategies were on the table - real-time and batched.
**Decision:** real-time flush via `EVENT_TRACE_REAL_TIME_MODE`.
**Rationale:** batched mode added 500ms worst-case latency; focus events
must surface within one UI frame.
**Implications:** buffer size capped at 64 KB; adjust if drop-rate climbs.
```

Skeleton:

```
## Discussions

### First topic

**Context:** ...
**Decision:** ...
**Rationale:** ...
**Implications:** ...

### Second topic

...

<discussion-end-marker on its own line>
```

## PW-7: MERMAID-COMPILE-REQUIRED

**Statement:** An edit that adds, modifies or pastes a mermaid block runs `mr script compile_mermaid <doc.md>` on that document and reports the per-block result before reporting done.
- Byte-identity to an already-rendered source is not a substitute: escaping differs between `.mmd` files and markdown-embedded blocks, line-ending and indentation drift corrupt the parser, and surrounding markdown shifts block boundaries. Validate at the landing site.
- The script extracts every mermaid block from the document and validates each with `mermaid.parse()` under jsdom, handling `<details>` and fence wrappers, and prints PASS or SKIP per block. No manual extraction.
- Best-effort, not a hard gate: a block-level parse failure prints SKIP with its error inline and leaves the exit code zero. Only a setup problem - document not found, node or npm missing, a failed npm install, an unterminated block - exits non-zero.
- So read the per-block report. A SKIP means read its error and either fix the syntax or revert the block. A non-zero exit surfaces to the orchestrator.
- A block that fails to parse renders as an error in GitLab in place of the diagram. The check costs about 10 seconds; a broken diagram in a reviewer-visible plan costs more.
- Without Bash in the session's toolset, surface the validation to the orchestrator. The discipline is that validation happens before complete, not that plan-writer runs it personally.
- Bad: skipping the check because the source `.mmd` already rendered.
- Bad: treating a SKIP as good enough because the exit code was 0.

---

## Default strengths

Reliable by default, so a spawn prompt need not restate them: R1-R14 and the
established BRANCH_PLAN.md conventions, preserving the discussion-end
structural marker, accurate diff statistics, and grep verification on request
("confirm zero TL mentions").

## Referenced common rules

- STYLE-9 NO-LINE-CITATIONS, name the file, class or function rather than a `file:line` citation, in any document a human reads - `~/.claude/skills/orchestrator/shared/rules/style.md`
