## Skill Edit Workflow

WORKFLOW NAME: skill-edit

Used when the developer requests changes to orchestrator skill content
(refinement, rule additions, project-specific scrubs, bloat compression,
checklist additions, history scrubs, structural reorganization).

The workflow assumes each needed persistent sub-agent has already been
spawned this session - every dispatch in Phases 2-4 routes to it via
SendMessage rather than spawning it again.

---

### Phase 1: INVENTORY (PLAN MODE)

#### Step 1.1: Fresh re-read of affected files
On first-pass inventory, or a pass that structurally reorganizes a file,
read it end-to-end (an unfamiliar file falls outside AGT-3's ranged-read
guidance). On a pass touching a single rule or section, bound the re-read
to that section plus its cross-references, per AGT-3 FRESH-CONTEXT's
`file:start-end` citation discipline, rather than the whole file. Either
way this re-read is mandatory at the start of every pass - the scope is
what narrows, not whether it happens.

#### Step 1.2: Build issue inventory
Group issues by concern (history scrub, project-specific scrub, duplication,
bloat, missing checklists, etc.). Use letter prefixes (A, B, C, ...) for
groups so each issue is addressable as `A1`, `B3`, `C7`.

For each issue: file:line citation, one-line fix description, owner
classification (Orchestrator-DEL-1 / Coder / Gitter).

#### Step 1.3: Owner classification per item
- **Orchestrator (DEL-1, all sizes)**: ALL edits to skill-tree files
  (`claude/skills/**/*.md`), agent definitions (`claude/agents/*.md`),
  and hook scripts that are skill-tree-internal (`claude/hooks/*`). The
  orchestrator owns this tree directly - no persistent sub-agent is
  authorized to edit it. DEL-1's trivial-edit exception (≤5-line direct
  edits) is a permission for OTHER trees; inside `claude/skills/`, the
  orchestrator does both small and large edits itself regardless of that
  threshold.
- **Coder**: edits to scripts/code/tests OUTSIDE the skill tree
  (`git_hooks_impl/`, project source, project tests). Dispatched by the
  orchestrator with precise file:line specs.
- **Gitter**: any `git` operation including `git mv` for renames,
  and the final commit/push.

**Completion checklist:**
- [ ] Every affected file read end-to-end
- [ ] Issue inventory written with letter groups + file:line + fix + owner
- [ ] Plan file updated with active-task inventory (no history content)

---

### Phase 2: BATCH EDITS (EXIT PLAN MODE)

#### Step 2.1: Orchestrator DEL-1 batch (parallel)
For all issues classified Orchestrator-DEL-1, apply Edit calls in parallel
where possible (independent files). Use `replace_all: true` per file when
the swap is a literal-string substitution that's safe across all occurrences.

#### Step 2.2: Coder dispatch (single bundled task)
Bundle ALL multi-line / new-file / structural edits into ONE SendMessage to
Coder. Include: precise file:line specs, exact replacement text,
verification greps to run, completion checklist.

Never spawn a fresh `orchestrator-persistent-coder` sub-agent when one is
already reachable this session - reuse it via SendMessage.

**Completion checklist:**
- [ ] All DEL-1 direct-edit swaps applied
- [ ] Coder dispatch includes every multi-line item with precise specs
- [ ] Coder reports APPLIED (not PARTIAL or ABORTED)

---

### Phase 3: VERIFY (PLAN MODE)

#### Step 3.1: Re-read each touched file
Per the global 80-95% edit-quality rule: spot-verify by reading every file
that was edited. Confirm meaning preserved, no silent omissions, no broken
cross-references.

#### Step 3.2: Targeted greps for survivor terms
Run greps for terms that should have been scrubbed (e.g., old rule numbers,
removed function names, deleted file paths). Each grep should return
ZERO hits in the in-scope tree, with documented exceptions for deferred
content.

#### Step 3.3: Warning sweep
Run WF-23 WARNING-SWEEP now.

**Completion checklist:**
- [ ] Every touched file re-read
- [ ] All survivor-term greps return zero hits (or hits only in documented defers)
- [ ] WF-23 sweep reported, zero unresolved warnings

---

### Phase 4: COMMIT (EXIT PLAN MODE)

#### Step 4.1: Gitter runs pre-commit pipeline
SendMessage to Gitter with: file list, commit subject + body
draft. The Gitter runs its full 5-phase pre-commit pipeline (gather → review
→ verify → approve → commit) including the G7 mandatory steps (plan update,
consistency check).

#### Step 4.2: Commit body audit
Body MUST describe state-after-commit, not the journey. Every sentence
should be a current-state declaration ("All X use Y", "No X in Y", "X has
Y"). No "Pass N", no commit hashes, no dates, no "previously", no narrative.

#### Step 4.3: Skip-dialog routing
Every WF-1 SKIP-PERMISSION request from Gitter (Phase 2.1, 2.2, 3.1) routes through
the orchestrator → AskUserQuestion → developer. Never pre-approve skips
in the Gitter dispatch text.

**Completion checklist:**
- [ ] Gitter pipeline complete with developer approval at Phase 4
- [ ] Commit subject ≤60 chars, G2-whitelisted verb, no trailing dot
- [ ] Commit body is purely current-state declarative
- [ ] Every skip dialog surfaced to developer (never pre-approved)

---

## Convergence pattern (multi-pass refinements)

Large refinements split into passes by CONCERN, not by file. Each pass is
one commit. Re-read fresh between passes rather than trust your in-context
snapshot from the prior pass, but per AGT-3 FRESH-CONTEXT's `file:start-end`
citation discipline bound that re-read to the sections the prior pass
changed or flagged, not the whole file, unless the prior pass was a
structural reorganization.

Typical split:
- **Pass 1: STRUCTURAL** - missing files, broken cross-refs, stale counts,
  missing memory promotions, DOC-6 duplication removal
- **Pass 2: COMPRESSION + CHECKLISTS** - bloat reduction, history scrub,
  project-specific scrub via abstract-tree pattern, per-phase completion
  checklists
- **Pass 3: RESIDUAL** - second-order issues that surface only after
  Pass 1+2 settle (e.g., propagated identifier updates, leftover refs
  in unaudited sub-trees)

Each pass commits separately. Subject describes the pass's concern in
state-after-commit terms.
