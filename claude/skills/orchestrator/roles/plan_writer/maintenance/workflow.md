## Plan Maintenance Workflow

WORKFLOW NAME: maintenance

Full audit-fix-review pass, invoked after milestone completions or when the
developer asks to update the plan. Most of the work is dispatched to
sub-agents from this workflow. Convergence loop for auditing and fixing the
BRANCH_PLAN.md file.

**Two-tier approach:**
- **Targeted check** (gitter Phase 3.2): per-commit, covers only sections affected
  by the diff. Lightweight - one agent checks changed sections against the code.
- **Full maintenance** (this workflow): after milestone completions (fixer done,
  featurer done, refactorer converged, etc.). Runs scripts + section-level agents.

**When to invoke (full maintenance):**
- After completing a full workflow (fixer, featurer, refactorer, etc.)
- After multiple commits accumulate (3+ commits without full maintenance)
- When the developer asks to update the plan

| Command | What it does | When to use |
|--------|-------------|-------------|
| `mr script plan_summary` | Quick health: size, sections, checkboxes, hash, freshness | Before and after maintenance |
| `mr script audit_plan` | Sections, empty sections, missing paths, and stale references in one report | Phase 1 audit |

```bash
# Examples
mr script plan_summary
mr script audit_plan
```

---

### Phase 1: AUDIT PLAN (PLAN MODE)

#### Step 1.1: Gather plan health

Run the scripts to get a baseline:

```bash
mr script plan_summary
mr script audit_plan
```

#### Step 1.2: Audit sections for deprecation (1 agent per section)

Parse BRANCH_PLAN.md top-level sections (every `## ` heading). For each section,
dispatch a fresh-context audit:

- **Subagent type:** fresh general-purpose sub-agent (sonnet model)
- **Instance name:** `orchestrator-plan-writer-maintenance-audit-{section_slug}` -
  used in TaskCreate / SendMessage tracking

**Splitting large sections:** If a `## ` section contains more than 5 `### `
sub-sections, dispatch 1 additional analyzer per `### ` sub-section on top of the
`## ` section dispatch. Instance name for sub-sections:
`orchestrator-plan-writer-maintenance-audit-{section_slug}-{subsection_slug}`

Per AGT-3 FRESH-CONTEXT, each sub-agent receives its assigned
section/sub-section (by name or pointer) plus the audit rubric's file path
(deprecated-content checks, command verification, file-path checks, etc. -
see the bullet list below) - it reads the rubric itself, never a pasted
copy. Fresh context is what makes the audit a real check rather than a
confirmation of the plan-writer's own read. It is read-only and reports
findings only.

Each agent checks its section for:
- **Deprecated content**: old naming, removed features, stale descriptions
- **Commands**: verify each command exists and runs
- **File paths**: verify every referenced path exists on disk
- **Behavior descriptions**: verify they match the actual code behavior
- **Tables**: verify data matches current state (counts, names, statuses)
- **Diagrams**: verify structure matches current architecture
- **Checkboxes**: verify checked items are done, unchecked are pending
- **Feature descriptions**: verify they describe what the code actually does

Launch agents in parallel (up to 10, per AGT-1). Each writes to its own
artifact directory.

#### Step 1.3: Collect audit results

Read each agent's output. Merge into a single summary table:
```
| Section | Agent | Status | Issues |
|---------|-------|--------|--------|
```

Any section with STALE or WRONG findings must be fixed in Phase 2.

**Completion checklist:**
- [ ] All scripts run (plan_summary, audit_plan)
- [ ] One audit agent per `## ` section launched (and per `### ` if 5+ sub-sections)
- [ ] All agent results merged into summary table

---

### Phase 2: FIX PLAN (EXIT PLAN MODE)

#### Step 2.1: Edit plan to resolve all issues

Plan-writer applies the edits itself (`orchestrator-persistent-plan-writer`).
Inputs:
- The complete list of issues from Phase 1 audit
- Exact old → new strings for each fix
- Plan maintenance rules (from rules.md)

The plan-writer handles: stale numbers, checked TODOs, Decisions Log entries,
command table updates, and section text corrections.

#### Step 2.2: Re-audit - fresh analyzer dispatch

Plan-writer dispatches a fresh general-purpose sub-agent (sonnet model)
directly via `Agent` (a persistent sub-agent may spawn its own per-task
verifiers), with a spawn prompt covering pointers to ALL fixed sections
plus the audit rubric. Plan-writer reads the analyzer's report from its
final message and decides.

The sub-agent receives NO context from the editing session. It is
read-only and reports a pass/fail table.

Also re-run the script to verify programmatic checks pass:
```bash
mr script audit_plan
```

#### Step 2.3: Convergence check

Read analyzer output + script results:

- **CONVERGED - no further changes pending** (analyzer zero issues AND scripts zero hits): proceed to Phase 3.
- **Issues remain**: loop back to Step 2.1 - delegate remaining issues to plan-writer, then re-dispatch fresh analyzer (Step 2.2). Do NOT carry forward the previous analyzer output.

**Completion checklist:**
- [ ] All Phase 1 issues delegated to plan-writer
- [ ] Analyzer dispatched fresh (AGT-3 FRESH-CONTEXT): zero issues
- [ ] audit_plan: zero hits
- [ ] Loop exited only on `CONVERGED - no further changes pending`

#### Step 2.4: WF-11 orchestrator post-completion E2E verification

After plan-writer reports CONVERGED AND the fresh analyzer reports zero issues AND the scripts report zero hits, the orchestrator MUST perform WF-11 verification before proceeding to Phase 3. This is a SEPARATE check from the fresh analyzer (analyzer applies a rubric; orchestrator hunts for stale cross-references, internal contradictions, editorial leaks, and silent omissions specific to the dispatched changes).

For BRANCH_PLAN.md (often >500 lines), the orchestrator reads it in chunks
until every section is covered (per PLAN-1), then makes the gap-hunting /
accept-or-redispatch decision in its own context.

If gaps found: re-dispatch plan-writer with the specific gap list (back to Step 2.1). Re-verify after the follow-up.

**Completion checklist:**
- [ ] Orchestrator read BRANCH_PLAN.md end-to-end (chunked if large)
- [ ] Stale-cross-reference / contradiction / editorial-leak / silent-omission scan complete
- [ ] Zero gaps OR all gaps redispatched + re-verified
- [ ] WF-11 verification check printed visibly per WF-6A PRINT-GATES

---

### Phase 3: REVIEW DECISIONS (PLAN MODE)

#### Step 3.1: Spot skill-worthy rules

On every fix or change, ask: is this a one-off or a general rule
that should be in a role? Propose before adding.

#### Step 3.2: Feature change review

For new features/fixes/deletions, review:
- What pain does it solve?
- Pros/cons of approach
- How to describe to users
- What existing plan details could it break
- What existing tests/docs need updating

#### Step 3.3: Refactoring decisions

When a task requires refactoring existing code (changing signatures,
moving values, restructuring modules), relay concrete options to the
orchestrator via `SendMessage(to: "main", ...)` for an AskUserQuestion ask
(plan-writer has no direct `AskUserQuestion` access - classic schema, AGT-26
RELAY-IDENTIFY in shared/rules/agents.md):
- What needs to change and why
- Option A (exact approach with implications)
- Option B (alternative with implications)
- Tradeoffs (callers affected, files touched, test impact)

Developer picks approach, then implement.

#### Step 3.4: Final summary

Run the summary script to capture post-maintenance state:
```bash
mr script plan_summary
```

Present before/after comparison to developer.

**Completion checklist:**
- [ ] Skill-worthy rules proposed (or none surfaced)
- [ ] Feature changes reviewed for pain/pros/cons
- [ ] Refactoring decisions relayed for an AskUserQuestion ask if scope warrants
- [ ] Final summary script run; before/after comparison presented

---

### Phase 4: RULES CHECK - verify the work against this role's rules

Follow the procedure at
`~/.claude/skills/orchestrator/shared/rules-check-procedure.md` against
`~/.claude/skills/orchestrator/roles/plan_writer/rules.md` (PW-2 through
PW-7), scoped to the changed plan/README paths.
