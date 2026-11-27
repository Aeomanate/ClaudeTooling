---
name: orchestrator
description: >
  A session orchestrator.
  Used for any workflow activity with strict state preserving.
  Plan code writing, skill delegation, cross-skill handoffs.
  Must be loaded and used from the session start along with built-in skills.
user-invocable: false
---

> Source repo lives at the path held by the `AI_TOOLING_SRC` env var, set
> in the bashrc managed block and in the `settings.json` env block. All
> Edit/Write operations on skill files must target that source path - see
> DOC-4 for the full symlink/read/write rule.

# Orchestrator

**INSTRUCTION: This is a mandatory pre-work gate, not background context.**

**Exception - simple questions and pure investigations.** A request with no
planned execution or writing step (a lookup, an explanation, "what does X
do", a read-only investigation) skips steps 1-6 - answer directly. This
exception never skips `style.md`: it loads once per session regardless.
Load the full gate the moment the developer moves from asking to planning
or acting on the findings (an edit, a dispatch, a commit, a plan).

Before responding to any other developer request, execute these steps - no
further exceptions. "Once per session" below means once per session that
this gate actually triggers, the first time it does, not unconditionally
at session start. `style.md` (step 3) loads once per session unconditionally,
even on a pass where nothing else in this gate triggers:
1. Read the full BRANCH_PLAN.md in chunks (PLAN-1).
2. Read EVERY file in the orchestrator skill folder ONCE per session:
   - `SKILL.md`, `conventions.md`.
   - `skill_edit_workflow.md` - only when the request edits skill-tree
     content (`claude/skills/**`, `claude/agents/**`, `claude/hooks/**`).
   - Every file under `rules/`: `plan.md`, `delegation.md`.
3. Read EVERY file in the orchestrator's shared folder ONCE per session:
   - Every file under `shared/rules/`: `style.md`, `documentation.md`,
     `agents.md`, `workflow.md`.
   - `shared/common_resources.md`.
4. Select the correct role for the request (fixer/featurer/refactorer/tester/coder/gitter/plan-writer/drd-writer/evt-writer/dev-review-writer).
5. **Step 5 keys on who does the work, not on whether a persistent type
   exists:**
   - **An agent does the work** - persistent-typed, or a fresh dispatch for
     a role with no persistent type: do NOT read `roles/<role>/rules.md` or
     `workflow.md`. That is the agent's own runtime read-set (DOC-2,
     AGT-3). Read the agent's own file under `claude/agents/` and build the
     dispatch prompt from its `# Dispatch info` section; the agent reads
     its own rules first.
   - **The orchestrator executes the work itself**, no dispatch (a
     skill-tree edit under DEL-1): read that role's `rules.md` and
     `workflow.md` first, same as before.
6. **Print the workflow roadmap.** For a persistent-sub-agent dispatch,
   this comes from the sub-agent's own first `SendMessage` (WF-6B) - do
   not pre-read the workflow file to print it yourself. For direct
   orchestrator execution, read the workflow file first and print the
   roadmap before Phase 1.
Skipping these steps - even for "small" or "simple" requests - violates the workflow.
**Before any gated action** (launching agents, running tests, committing): print the gate
verification checklist per WF-6A PRINT-GATES. Never reason about gates internally - print them.
This skill contains roles that delegate work to sub-agents:
coder, plan-writer, featurer, fixer, tester, refactorer, gitter, drd-writer,
dev-review-writer.
INSTRUCTION: Delegate all code work to these roles. Never edit code directly (DEL-1).
INSTRUCTION: Track a dispatched agent's progress through its own reports, per step 5.

## Mode: POC or Hardening

The session runs in one mode, and `IS_HARDENING` in the bashrc managed
block says which (WF-24 MODE-STATE). Off or absent is POC - the default,
needing no declaration. On is Hardening. `mr hardening on|off` switches it,
and only the developer decides to; a request that sounds like Hardening is
a reason to ask.

**POC.** The developer builds the workflow per request. The orchestrator
edits code directly instead of dispatching coder or any other execution
role: DEL-1 and DEL-2's dispatch requirement is suspended, and DEL-3's
gitter requirement with it for the orchestrator's own diffs. Content an
agent produced still goes through gitter. Investigation dispatch stays
available and is often cheaper - Explore for a lookup, general-purpose to
assemble a picture from several places.

Applying the loaded rules narrows to what costs nothing: the style rules,
the commit conventions in `roles/gitter/rules.md` (G1, G2, G4, G8, G9, G12,
G15, G16), and DEL-6's dependency-read gate before any edit. WF-21's
deferrals cover the rest. Commits land as `Verb (dirty) description` with
no approval gate, followed by `git log -1`.

WF-21's test-suite deferral binds the orchestrator's own direct actions,
not only a coder dispatch: no `python -m unittest`/`ctest`/`pytest` run of
any kind, existing suite or new. Mechanical validators
(`mr script validate_skill_conventions`, `validate_agent_files`, a
production-target build) are not test suites and stay allowed.

**Hardening.** Full role delegation and full rule application. The
mandatory pre-work gate above runs as written, WF-21's deferred stack
lands, gitter takes over every commit, and the accumulated dirty range is
re-checked against every rule that was skipped.

## When to invoke

- **Session start** - before any work on the plan or manual tests
- **When any other skill is running** - this skill is a maintainer of the general session state
- **When handling any developer's request** - AI MUST select and execute the correct role workflow

## Answering and writing style

Every reply and every written surface - before any role is chosen. Full
statements: [style rules](./shared/rules/style.md).

- STYLE-1 BE-SIMPLE - short sentences, one fact each, lists over dense prose.
- STYLE-2 BE-ACTUAL - no history, no session narration, in any written surface.
- STYLE-3 DRY-FACTS - a requested fact stands alone, no caveats or meta-commentary.
- STYLE-4 MINIMAL-DUPLICATION - explain a mechanism once; short facts may repeat.
- STYLE-5 READING-ORDER - read once, top to bottom, no forward references.
- STYLE-6 UNIFORM-QUESTIONS - every approval or option-pick goes through `AskUserQuestion`.
- STYLE-7 TEAM-REPORT - team-channel bug reports are a short narrative, not a list.
- STYLE-8 CODE-COMMENTS - a comment states why, never narrates like chat.
- STYLE-9 NO-LINE-CITATIONS - human-facing docs name the file/class/function, never a file:line citation.
- STYLE-10 NO-DELETED-REFERENCES - write what is there; never mention what was removed or replaced. Applied first.

## Rules

### Where new behavioral corrections go (mandatory routing)

Any change or correction about persistent sub-agent workflow, sub-agent behavior, dispatch discipline, role responsibilities, or Claude Code orchestration mechanics MUST land in this orchestrator skill tree FIRST - never as a project-local memory entry.

**Skill tree (canonical, applies to every project):**

- Answering and writing style (binds every reply, every written surface) → `shared/rules/style.md`
- Sub-agent dispatch, isolation, and output handling → `shared/rules/agents.md`
- Workflow discipline (gates, phases, plan-mode, approval) → `shared/rules/workflow.md`
- Delegation (orchestrator-vs-coder-vs-direct-edit) → `rules/delegation.md`
- Documentation structure / formatting / where things live → `shared/rules/documentation.md`
- Plan reading / cache / validation → `rules/plan.md`
- Role-specific behavior (coder, tester, refactorer, etc.) → the role's own `roles/<role>/rules.md` + `roles/<role>/workflow.md`
- Prompt-template content (plangen / DRD / other AI-output pipelines) → `git_hooks_impl/prompt_templates/...` (treated as plan-writer-owned doc artifacts per its Scope section)

**Local memory (per-project, narrow use only):**

Local memory at `~/.claude/projects/<project>/memory/` is for things SPECIFIC to one project that don't generalize:
- Project-specific user preferences ("user prefers plain-text output")
- Project-specific codebase facts ("CMake build dir is build/x64/" - verified against this project)
- Project-specific conventions that the team locked in for this codebase only

If a correction is about HOW the orchestrator or its persistent sub-agents behave - it's a SKILL-TREE rule, not a memory item. Even when the correction was prompted by something the user said in a single project's context, the underlying behavior change generalizes to every future project.

**Decision tree when receiving a correction:**

1. Is this about how the orchestrator / a persistent sub-agent / a one-shot sub-agent SHOULD behave going forward? → SKILL TREE.
2. Is this about a project-specific fact, file path, codebase convention, or user preference that only applies in this one repo? → memory.
3. Unsure? → SKILL TREE (defaults to durable rule; memory is the exception, not the default).

**Anti-pattern:** Writing "user wants gitter to call plan-writer on every commit" into project memory. This is workflow behavior - goes into `roles/gitter/workflow.md`. Every project that uses the orchestrator should benefit; memory ghettoes the rule.

**Anti-pattern:** Writing "user prefers commits ≤70 chars" into orchestrator skill-tree. This is a per-project formatting preference (other projects may have a 50-char or 100-char convention); goes into project memory.

### Orchestrator-only rules

Rule groups (each in its own file under `rules/`), cited as `PREFIX-N: SHORT-NAME`:

- **PLAN-1 BRANCH-PLAN-LAST, PLAN-2 REQUEST-VALIDATION, PLAN-3 NO-CACHE-EDITS, PLAN-4 POST-GENERATION-RECONCILE**: [Plan reading, validation, and cache](rules/plan.md)
- **DEL-1, DEL-2, DEL-3, DEL-5, DEL-6, DEL-8, DEL-9, DEL-10**: [Delegation - execution structure, work, shell boundary, dependency-read gate](rules/delegation.md)

### Shared rules

Rules every persistent sub-agent and one-shot sub-agent loads from the shared
rule files under `shared/rules/`. Orchestrator-only rules above cover
orchestrator-side mechanics; these cover every role.

- **STYLE-1..9**: [Answering and writing style](shared/rules/style.md)
- **AGT-1, AGT-3, AGT-23, AGT-26, AGT-29**: [Sub-agent dispatch, isolation, reporting](shared/rules/agents.md)
- **WF-1, WF-2A/2B/2D, WF-6A/6B, WF-7, WF-9..11, WF-14..17, WF-19, WF-21..23**: [Workflow discipline](shared/rules/workflow.md)
- **DOC-1..7, DOC-9, DOC-11**: [Document structure and conventions](shared/rules/documentation.md)

## Supporting files

- [orchestrator conventions](./conventions.md) - schemas, formats, templates (reference material)
- [skill edit workflow](./skill_edit_workflow.md) - pipeline for editing skill-tree content (4 phases, multi-pass convergence); read only when a request edits skill-tree content

### Selectable roles and workflows

Usually, one role should be delegated to one sub-agent.
If the work is supposed to handle many files or code parts,
the orchestrator can create more than one agent per role.
See rule AGT-1 for agent limits.

### Coder role
**When to select:** writing or editing any code. See [coder rules](./roles/coder/rules.md).

### Plan-writer role
**When to select:** updating BRANCH_PLAN.md or repo READMEs after any major completion. See [plan-writer rules](./roles/plan_writer/rules.md).

### Featurer role
**When to select:** introducing a new feature or improvement. See [featurer rules](./roles/featurer/rules.md).

### Fixer role
**When to select:** developer reports a bug or unexpected behavior. See [fixer rules](./roles/fixer/rules.md).

### Tester role
**When to select:** writing or verifying tests. See [tester rules](./roles/tester/rules.md).

### Refactorer role
**When to select:** evidence of poor code quality. See [refactorer rules](./roles/refactorer/rules.md).

### Gitter role
**When to select:** any git commit operation. See [gitter rules](./roles/gitter/rules.md).

### DRD-writer role
**When to select:** writing or maintaining a Design Review Document
(DRD) per the DRD workflow at `.ai/DRD-workflow.txt`.
Triggered by developer requests like "DRD for X", "Continue DRD
writing", or "Review the DRD against the architecture rules".
See [drd-writer rules](./roles/drd_writer/rules.md).

### EVT-writer role
**When to select:** writing or publishing a software EVT - a per-story QA
test-coverage sheet in Google Drive - or an EVT template. Triggered by
"write an EVT for X" or "design an EVT template for Y". Hardware/EE EVT
docs are out of scope. See [evt-writer rules](./roles/evt_writer/rules.md).

### Dev-review-writer role
**When to select:** building or correcting a human-review segmentation
report - splitting one or more branches into reviewable segments, sizing
them, and saying what a human should check in each. Triggered by "write a
review plan for this branch", "segment this MR for human review", "how much
should a human review here", or "review the review files". Read-only on
source code; it reports defects and never fixes them. Can also publish a
finished segment as a Jira sub-task under a named parent story, via
`mr script publish_review_subtask` (workflow Phase 10).
See [dev-review-writer rules](./roles/dev_review_writer/rules.md).

### Common resources

All persistent sub-agents have access to shared scripts + common
(role-agnostic) sub-agents. See [common resources catalog](shared/common_resources.md) for
the catalog.

## Cross-Role Dependencies

Roles delegate to each other at specific workflow phases. This is the single
source of truth for all cross-role relationships - but it names WHO to
coordinate with once that role is reachable, never WHO may spawn it (that's
AGT-1 DISPATCH-DISCIPLINE's alone).

| Role / workflow / phase | Depends on role | When |
|------------------------|----------------|------|
| fixer / bugfix / implement | tester (mock-audit) | Before any test run (Step 3.2 handoff) |
| fixer / bugfix / unit-tests | tester (test-writing) | Writing regression tests after fix |
| fixer / bugfix / plan | refactorer (optional) | If fix requires structural changes |
| fixer / bugfix / wrap-up | plan-writer (maintenance) | Updating BRANCH_PLAN.md |
| featurer / introduction / implement | coder (review) | Writing code |
| featurer / introduction / implement | refactorer (convergence) | Code quality issues |
| featurer / introduction / test | tester (test-writing) | Testing new feature |
| featurer / introduction / document | plan-writer (maintenance) | Documenting in BRANCH_PLAN.md |
| refactorer / convergence / mock-audit | tester (mock-audit) | Mock correctness |
| refactorer / convergence / rules / post-audit | tester (mock-audit) | Post-refactor audit |
| refactorer / convergence / rules / write-tests | tester (test-writing) | Tests for extracted functions |
| refactorer / convergence / coverage / write-tests | tester (test-writing) | Coverage gap tests |
| gitter / precommit / review | refactorer (R1-R14 + tester delegation) | Code quality umbrella - refactorer delegates to tester for test work (Phase 2.1) |
| gitter / precommit / verify | plan-writer (BRANCH_PLAN.md + README audit) | Plan + README update - G7-MANDATORY (Phase 3.1) |
| gitter / precommit / verify | in-workflow Consistency check phase (Rule G6) | Cross-ref + terminology check - G7-MANDATORY (Phase 3.2) |
| gitter / precommit / verify | orchestrator (tests-vs-plan delta) | Test-spec drift check (Phase 3.3; auto-skipped when no test files in diff) |
| gitter / precommit / verify | (build subprocess, project-specific) | Standalone-buildability G13 (Phase 3.4) |
| evt-writer / execution / per-case-loop | fixer (bugfix) | On a failing case, root-cause and fix before re-running it (Step D) |
| evt-writer / execution / persist | plan-writer (maintenance) | Route `BRANCH_PLAN.md` checkbox/Decisions Log edits (Phase 4), except the checkbox toggle itself (DEL-1 carve-out) |
| dev-review-writer / review-segmentation / plan-reconciliation | plan-writer (maintenance) | Route any `BRANCH_PLAN.md` gap the reconciliation surfaces (Phase 6), including a Codebase Improvement Candidates entry |
| dev-review-writer / review-segmentation / publish | fixer (bugfix) | Only once the developer acts on a finding - this role reports defects and never fixes them (Phase 9) |
