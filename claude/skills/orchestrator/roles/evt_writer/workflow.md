## EVT Execution Workflow

WORKFLOW NAME: EVT Execution

Runs an EVT's cases against the real system, tier by tier, fixing what
fails as it goes. This is an orchestrator-driven workflow, not something
evt_writer runs alone - evt_writer owns the QA doc and the Drive sheet
(EVT-15/EVT-16); this workflow owns the loop that executes cases, invokes
the fixer workflow on failure, and hands Result writes back to evt_writer.

**When to invoke:** the developer asks to run/execute an EVT, a QA
document's case set, or "test everything in `<doc>`."

**Do not confuse with EVT-3 VERIFY-AFTER-PUBLISH** - that's about
confirming a Drive write landed. This workflow is about confirming a
*case* passes against the running system.

---

### Phase 0: Resume-or-start

Before running anything, check for an in-progress run:

1. If `.ai/BRANCH_PLAN.md` exists for the current branch, read its
   Implementation Plan section for an entry naming this EVT run
   (`- [ ] EVT <doc>: <tier> tier, case <id> onward`). If found, resume
   from the first unchecked case in tier order - do not restart tiers
   already fully checked.
2. If no `BRANCH_PLAN.md` exists (no active branch plan for this work),
   check project memory for an in-progress-run entry for this doc (see
   Phase 4 for the entry shape). If found, resume from its recorded
   position.
3. If neither exists, this is a fresh run: start at Phase 1, first Core
   case.

**Completion criteria:** exactly one of resume-position or
fresh-start is established before any case runs.

---

### Phase 1: CORE

Run every Core-tier case (EVT-14 CASE-TIERING), in the document's order.
For each case, run the per-case loop below.

---

### Phase 2: CORNER

Only after every Core case is Pass or explicitly Blocked (Phase 3 of the
per-case loop). Run every Corner-tier case with the same loop.

---

### Phase 3: ERRORS-AND-LIMITS

Only after Core and Corner are both clear. Run the verifiable error and
system-limit cases (access-denied paths, session/provider caps, and
similar) with the same loop, but only where the case's own Preconditions
say it's checkable from this environment. A case needing something this
session cannot arrange alone (a second real account, a real interactive
sign-out) is marked Blocked - reason recorded, not silently skipped, and
never invented.

---

### Per-case loop (Phases 1-3 share this)

#### Step A: Execute

Run the case's Steps exactly as written. Delegate command execution
per DEL-2/DEL-3 - the orchestrator does not run mutating or heavy
commands itself; a fixer-style investigation sub-agent or direct
developer action does, matching the case's own Preconditions.

#### Step B: Observe and confirm

Compare actual output against the case's Expected field. This
confirmation is never assumed from "the command didn't error" - read
the actual evidence (log line, observed behavior) and state explicitly
whether it matches. A case with no clear pass/fail signal is a case that
needs rewriting (EVT-15), not a case to wave through.

#### Step C: Cleanup

Run the case's own Cleanup field, regardless of pass or fail - a failed
case can still leave machine state (a running instance, an installed
service, a signed-out session) that would poison the next case. Do this
after Step B, not before: Observe must read the evidence while it still
exists, and Cleanup routinely tears down exactly the state Evidence
depends on (stopping instances, uninstalling a service, closing an app).
The case's own table lists Cleanup right after Steps for readability -
that is a reading order, not the execution order this step follows.

#### Step D: On pass

1. Update the case's Dev Result to Pass (route the doc edit through
   evt_writer for the EVT sheet, and through whichever role owns the
   repo QA doc for that file).
2. Persist progress (Phase 4).
3. Continue to the next case.

#### Step E: On fail

1. Stop the linear run at this case - do not skip ahead. A `Fail` is
   always a defect to investigate, never a result the run excuses or
   pre-approves (EVT-8) - hand off to fixer regardless of whether the
   case documents an expected alternative outcome.
2. Hand off to the fixer workflow (`roles/fixer/workflow.md`) with the
   case's Steps as the reproduction and its Expected as the target
   behavior. Run fixer's Phases 1-6 to completion (root cause found,
   fix implemented, mock-audited, tested, committed via gitter,
   BRANCH_PLAN.md updated).
3. Once fixer reports the fix landed, re-run this same case from Step A
   - do not resume past it on the fixer's word alone. The case itself is
   the confirmation.
4. Only once the re-run passes, proceed as in Step D, plus note which
   fix closed it (commit reference, not a narrated bug story - EVT-21
   still applies to the case's own Note field; the fix history lives in
   git and the fixer's commit, not restated here).

**Completion criteria:** every case in the current tier is Pass or
Blocked before moving to the next tier.

---

### Phase 4: Persist state (after every case, both loops)

**Prefer `.ai/BRANCH_PLAN.md`** when one exists for this branch - add or
update one Implementation Plan checkbox per case
(`- [ ] EVT <doc>: <tier>, case <id>`), checked off as each case closes.
Route the actual edit through plan-writer except for the
checkbox toggle itself, which the orchestrator may do directly per
DEL-1's state-file carve-out. A fix that lands during Step D also gets
its own Decisions Log entry, per plan-writer's normal per-fix
requirement - nothing new here beyond what fixer's own wrap-up already
does.

**Fall back to project memory** only when no `BRANCH_PLAN.md` exists for
this work. Save one project-type memory entry (e.g.
`evt_run_<doc-slug>.md`) recording: the doc, the current tier, the last
confirmed case id, and any cases marked Blocked with their reason.
Overwrite this same entry as the run progresses - it is run-state, not a
durable fact about the project.

**Mandatory cleanup:** once Phase 5 (wrap-up) completes, delete the
run-state memory entry (or, for the `BRANCH_PLAN.md` case, remove the
now-fully-checked subsection per the plan's own "all boxes checked ->
remove the subsection" convention). A finished run leaves no in-progress
marker behind - the memory system's own exclusion rule against saving
ephemeral task state depends on this workflow actually cleaning up
after itself, not on the rule alone.

**Completion criteria:** exactly one persistence mechanism is used per
run (never both), and it names doc, tier, and last-confirmed case.

---

### Phase 5: Wrap-up

Once every case across all three tiers is Pass or Blocked:

1. Summarize: cases passed, cases blocked (with reason), fixes landed
   during the run (cross-referenced by commit).
2. Clean up persisted state (Phase 4's mandatory cleanup).
3. If any fix during the run surfaced a pattern worth remembering
   (per fixer's own Phase 6), that goes through fixer's normal
   MEMORY.md / patterns update - not duplicated here.

**Completion criteria:** persisted state removed, summary presented to
the developer.
