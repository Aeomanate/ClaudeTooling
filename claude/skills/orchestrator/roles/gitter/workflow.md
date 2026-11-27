## Pre-Commit Workflow

WORKFLOW NAME: precommit

Mandatory before EVERY `git add` + `git commit`, for all file types - code,
shell scripts, skill instructions, configs - regardless of which role is
active. No exceptions.

**GATE RULE**: Phase N's gate condition must be satisfied before Phase N+1
starts.

**ROLLBACK RULE**: A phase failing after Phase 1 means: STOP, EXPLAIN which
phase failed and what the violation was, SUGGEST recovery options, then WAIT
for the developer's decision. No action before that decision.

**SKIP RULE**: Each skippable phase requires explicit developer permission
via G10's structured skip token. These cannot be skipped under any
circumstances (G7); a skip token naming one is auto-rejected per G10's G7
carve-out and the dispatch returns to the orchestrator unmodified:
- Step 3.1 (Plan + README audit) - fresh plan-writer dispatch, always
- Step 3.2 (Consistency check) - fresh analyzer agent, always
- Step 3.3 (Tests-vs-plan delta check) - orchestrator handoff; auto-skipped only when no test files in diff (auto-skip is NOT a G7 violation - it's a "no work to do" pass, not a dispatcher override)
- Phase 4 (APPROVE) and Phase 5 (COMMIT)

An undispatched refactorer (Phase 2.1) or plan-writer (Phase 3.1) is never
grounds for silently skipping the phase. Gitter requests the dispatch from
the orchestrator via SendMessage, waits for confirmation the role is
reachable, then resumes at the same phase. Tester is dispatched transitively
by refactorer when test work is needed, through refactorer's own workflow.

---

### Phase 1: GATHER - collect commit context (PLAN MODE)

> Skip requires developer permission.

#### Step 1.1: Collect commit information

Gitter gathers the commit context inline, since the scope is small and
bounded:

- `git status` + `git rev-parse --abbrev-ref HEAD` - verify correct branch
- `git diff` (or `git diff --staged` if already staged) - the actual diff
- `git log --oneline -5` - recent commits for message style consistency

Output: branch name, changed file paths, diff summary (what changed and why),
proposed commit message following G2 format.

For unfamiliar diff scope or cross-file impact questions, dispatch the
built-in `Explore` agent - preferred over inline Grep when "what files also
reference X" is unclear.

Audit the diff's production/test split here (G14): a production change with
no test counterpart is rejected unless the commit is purely additive
coverage, a test-side refactor, or carries a `(dirty)` subject.

**GATE**: Non-empty diff, and a branch name matching project conventions
(G3). An empty diff means STOP - nothing to commit.

#### Step 1.2: Pre-flight staged-file check

Run `git diff --cached --stat` before staging anything new. Files already in
the index that the orchestrator did not name as part of this commit are
reported, and gitter WAITS for instruction - never commit blindly when the
index holds files outside the dispatch's named scope.

The index carries over staged files from workflow runs that aborted
mid-pipeline, from Edit-tool side effects on symlinked files, and from
explicit developer staging. Catching them here prevents bundling unrelated
logical units, a G1 violation.

---

### Phase 2: REVIEW - delegate code quality to refactorer (PLAN MODE)

> Skip requires developer permission.
>
> **Auto-allowed skip:** A diff with no Python (`.py`) or C++ (`.cpp` / `.h`
> / `.hpp` / `.cc` / `.cxx` / `.c`) source edits - only markdown, yaml, json,
> shell-script or config edits - is outside R1-R14's reach, since those are
> code-refactoring rules. The orchestrator may pre-approve the skip in the
> dispatch prompt in WF-1 SKIP-PERMISSION format, sparing a separate dialog.
> Phase 2 still runs when ANY code file is edited, even alongside markdown.

#### Step 2.1: Delegate code-review + refactor + test verification to refactorer

> **Spawn check:** If refactorer has not been dispatched yet this session,
> SendMessage the orchestrator `refactorer needed for Phase 2.1; blocking
> commit. Please dispatch it.`, WAIT for confirmation it is reachable, then
> proceed. Never skip Phase 2.1 on grounds of the role being undispatched.

Per the cross-role-dependencies table in SKILL.md, refactorer owns the
code-review umbrella: it scans the diff against R1-R14, proposes refactors,
and delegates test writing to tester when its proposals need new or updated
tests. Gitter spawns no review agents of its own.

Send to `refactorer` via `SendMessage`:

- The diff content (or target file paths)
- The proposed commit scope
- Request: scan for R1-R14 violations + propose refactor patches if needed + verify
  test coverage of changed code (refactorer will delegate to tester as needed)

Refactorer spawns its own general-purpose sub-agents for the R1-R14 scan and
project-memory convention checks, per AGT-1 DISPATCH-DISCIPLINE and AGT-3
FRESH-CONTEXT, and reaches
`orchestrator-agent-tester_mock_auditor` through tester for test
verification. Its own final RULES CHECK phase holds the convergence loop that
scan feeds.

The refactorer reports status - CLEAN, VIOLATIONS FOUND or TESTS NEEDED -
plus any proposed coder hand-off specs.

**GATE**: Refactorer reports CLEAN. Violations or test gaps route through the
orchestrator to coder/tester, and gitter waits for that work to complete.

#### Step 2.2: RULES CHECK - verify against gitter's own rules

Gitter's own G-rules govern the pre-commit pipeline itself - commit cadence,
message format, staging discipline - separate from the R1-R14 code-quality
scan Step 2.1 delegates.

Run `mr script classify_diff` once, before dispatching. Both Step 2.2 and
Step 3.2 read this same tag (G7A MECHANICAL-DIFF-TIER) - do not re-run it.

On a `standard` diff, follow the procedure at
`~/.claude/skills/orchestrator/shared/rules-check-procedure.md` against
`~/.claude/skills/orchestrator/roles/gitter/rules.md` (all G-rules),
scoped to the proposed commit subject + body + changed-file paths. If
Step 2.1's refactorer delegation is still active for this commit, also
check `roles/refactorer/rules.md` in the same dispatch - this one run is
the refactorer rules check, per its Phase 5 handoff.

On a `mechanical` diff, fold Step 3.2's consistency-check rubric into this
same dispatch: the sub-agent gets both the G-rules scope above and Step 3.2's
rubric in one prompt, one output path, one verdict. Report Step 3.2 as
`combined with Step 2.2`.

---

### Phase 3: VERIFY - plan + consistency (PLAN MODE)

> Skip requires developer permission.

#### Step 3.1: Plan + README audit - delegate to plan-writer

> **Spawn check:** If plan-writer has not been dispatched yet this session,
> SendMessage the orchestrator `plan-writer needed for Phase 3.1; blocking
> commit. Please dispatch it.` and WAIT for confirmation it is reachable.
> Step 3.1 is G7-mandatory - never skipped on grounds of the role being
> undispatched.

Request the orchestrator dispatch `orchestrator-persistent-plan-writer` if
not already reachable, then SendMessage it directly for this exchange.

Send the list of changed files plus the BRANCH_PLAN.md path
(`.ai/BRANCH_PLAN.md`). Plan-writer audits every section the changes could
affect - descriptions, commands, paths, numbers, checkboxes, feature
descriptions - and applies fixes per PW-2 through PW-7.

**README audit:** Every commit shifts the project's solution shape, so
plan-writer also reads the project's READMEs (ai_tooling's `README.md`,
`README - Plan management.md`, `README - AI-assisted workflow.md`) for drift
in cited file paths, command tables, agent-count and rule-count summaries,
and architectural descriptions. Plan-writer owns repo-prose documentation -
BRANCH_PLAN.md, root and module READMEs, hand-written design docs - so it
applies README edits directly and ensures they are in the staged file set
before reporting back. Skill-tree docs (`claude/skills/**`) are outside that
scope per DEL-1 and route to the orchestrator.

Manual plan edits made earlier in the session do not satisfy this step: they
may be incomplete or stale, and plan-writer verifies BRANCH_PLAN.md
independently against the committed changes.

**GATE**: Plan-writer reports the plan up to date AND the READMEs audited -
either no changes needed, or the edits already applied to the working tree. A
skip needs explicit developer approval per WF-1 SKIP-PERMISSION.

#### Step 3.2: Consistency check - dispatch fresh analyzer (Rule G6)

On a `mechanical` diff (per G7A, tagged once at Step 2.2), this rubric
already ran inside Step 2.2's combined dispatch - report `combined with Step
2.2` and skip the separate dispatch below.

On a `standard` diff, gitter dispatches a fresh general-purpose sub-agent
(sonnet model) directly via `Agent`, per AGT-1 DISPATCH-DISCIPLINE, and reads
its report for triage.

The sub-agent receives ONLY the list of changed files and a pointer to the
rubric below - no context from the editing session, since fresh context is
the entire point (AGT-3 FRESH-CONTEXT). It is read-only and reports a
pass/fail table.

Rubric - point the analyzer at what to check and let it read the changed
files itself, per AGT-3 FRESH-CONTEXT:
- Stale cross-references (old rule IDs, old file names, broken links)
- Terminology consistency (same concept must use same name everywhere)
- No contradictions between files
- Project-relative path convention (bare `.ai/...`, no `${CLAUDE_PROJECT_ROOT}` refs)
- Output cache path

**GATE**: Zero stale references. Issues route to coder through the
orchestrator, then Step 3.2 re-runs.

#### Step 3.3: Tests-vs-plan delta check - orchestrator handoff

Gitter PAUSES and hands off to the orchestrator, which reads ONLY the test
files in the diff - not full source - and compares them against the plan or
dispatch spec. Flags: tests not in spec, missing tests, deviated
implementation, tests that don't catch the regression they claim to.

**Auto-skip:** A diff with no test files auto-passes, no `user-accepted`
token required. Report `Step 3.3: auto-skip (no test files in diff)`.

**GATE:** Orchestrator reports CLEAN, or auto-skip applies → proceed to Step
3.4. QUIRKS reported → re-dispatch tester first.

#### Step 3.4: Standalone-buildability check (Rule G13)

All three cases below run through one registered command,
`mr script verify_commit_builds <build_dir> <config> [sha]` - never a raw
`cmake` or `git checkout` in this workflow, per DOC-3 SCRIPT-CONVENTION. Omit
`sha` to build the working tree as-is; pass it to build one specific commit.
The script owns the checkout-detach-restore sequence, popping any stash it
pushed on every exit path - success, build failure, or unexpected error - so
it never leaves the repo on a detached HEAD.

**Single commit (no stack):** `mr script verify_commit_builds <dir> <config>`
against the working tree, diff staged but not committed. Commit only after
that build passes.

**Multi-commit stack, commits already exist** - a re-run of Step 3.4 after
Phase 5 created them, or a stack being amended: for each commit, oldest
first, `mr script verify_commit_builds <dir> <config> <sha>`.

**Multi-commit stack, commits do not exist yet** - the normal case, since
Phase 4 approval precedes Phase 5's `git commit` and no per-commit SHA exists
at Step 3.4 time. Checkout-per-commit does not apply; the resolution is two
parts:
1. **Now, as the Step 3.4 proxy:** `mr script verify_commit_builds <dir>
   <config>` against the full cumulative diff, staged but not committed. This
   proves the end state compiles, not that each individual commit tip is
   standalone-buildable.
2. **During Phase 5 execution, as the real check:** build after each commit
   as it is created - commit, `mr script verify_commit_builds <dir> <config>`
   (no `sha`, it is already HEAD), confirm green, move on. A commit tip that
   fails to build stops the stack: fix the underlying issue through coder and
   `git reset --soft` the bad commit before recommitting, rather than
   continuing on a broken tip.

Report which path applied, and why, in the Step 3.4 status line.

**Auto-skip:** No compiled source in the diff means no check. Report
`Step 3.4: auto-skip (no compiled code in diff)`.

**GATE:** Green for whichever case applies - the single-commit build, or the
full-diff proxy plus every per-commit build during Phase 5, or every commit
already in the stack. A failure routes to coder, typically for a missing
CMake link dep, a hallucinated header, or commit reordering. Never enter
Phase 4 on a failing proxy build, and never continue past a failing
per-commit build during Phase 5.

---

### Phase 4: APPROVE - developer sign-off (EXIT PLAN MODE)

> This phase CANNOT be skipped.

#### Step 4.1: Print checklist table

Show the developer this status table:

| Step | Status | Details |
|------|--------|---------|
| 1. Gather commit info | DONE | branch: `{name}`, files: `{list}`, diff: `{summary}` |
| 2. Refactorer review (R1-R14 + tests) | DONE/SKIP | `{refactorer result or skip reason}` |
| 3. Plan update (plan-writer) | DONE/SKIP | `{what was updated or skip reason}` |
| 4. Consistency check (analyzer) | DONE/COMBINED-WITH-STEP-2.2/SKIP | `{analyzer result, "combined with Step 2.2" on a mechanical diff, or skip reason}` |
| 5. Tests-vs-plan delta check (orchestrator) | DONE/AUTO-SKIP | `{CLEAN or auto-skip (no test files)}` |
| 6. Standalone-buildability check (G13) | DONE/AUTO-SKIP | `{PASS or auto-skip (no compiled code)}` |
| 6b. Production/test split (G14) | DONE/EXEMPT | `{test counterparts present, or exemption: additive coverage / test-side refactor / dirty}` |
| 7. Print checklist | DONE | this table |
| 8. G7 mandatory phases | EXECUTED / DENIED-SKIP | Phase 3.1 + 3.2 + 4 + 5 status (DENIED-SKIP means a dispatch tried to skip them and gitter rejected per G10's G7 carve-out) |
| 9. Commit | PENDING | `{proposed message}` |

Step 1's Details must carry the branch name, the changed file paths, and a
brief summary of what changed and why.

Every skip is relayed to the orchestrator for an AskUserQuestion dialog
BEFORE this table is printed - never approved as inline text.

#### Step 4.2: Print G1-G10 commit checklist

Run `python ${AI_TOOLING_SRC}/git_hooks_impl/commit_checklist.py` and include
its output in the report to the orchestrator before requesting approval.

#### Step 4.3: Developer approval gate

Gitter has no `AskUserQuestion` access, so it relays the commit message to the
orchestrator via `SendMessage(to: "main", ...)` and asks for a formal dialog
per conventions.md's Approval Dialog Convention - never plain text. Options:
- Approve (commit with this message)
- Modify (I want to change the message)
- Reject (don't commit)

The user normally watches only the orchestrator's context, so the relayed
question and every option is answerable without opening gitter's transcript.
The orchestrator leads with which sub-agent asked and what it is working on,
per AGT-26 RELAY-IDENTIFY.

**GATE**: Explicit developer approval via dialog. Wait for the orchestrator's
reply before Phase 5 begins.

---

### Phase 5: COMMIT - execute git commands (EXIT PLAN MODE)

> This phase CANNOT be skipped.

#### Step 5.1: Stage and commit

Execute: `git add -u -- {files} && git commit -m "{approved message}"`

Add and commit always chain in a single command per G4, never separated, and
the plan file is never staged.

#### Step 5.2: Post-commit verification

After the commit succeeds:
- `git log -1 --oneline` - commit message matches what was approved
- `git diff HEAD~1 --stat` - file list matches what Phase 1 reviewed

A discrepancy is reported to the developer immediately - what was expected
versus what was committed - with `git reset --soft HEAD~1` suggested to undo
and retry, on developer permission.
