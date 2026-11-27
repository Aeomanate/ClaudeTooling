## Per-task Edit Workflow

WORKFLOW NAME: edit

This is the in-session workflow plan-writer itself runs when
dispatched with a specific edit task. Plan-writer operates inside this
loop until reporting PASS back to the orchestrator.

### Phase 1: Read current plan
Read full `.ai/BRANCH_PLAN.md` using Read tool (never grep shortcut - PLAN-1).

### Phase 2: Identify changes
Compare current plan against orchestrator's instruction.
List: additions, checkbox updates, log entries to add.

### Phase 3: Apply changes
Edit BRANCH_PLAN.md using Edit tool. One logical section per edit.
Never rewrite sections not in scope.

### Phase 4: STYLE-2 Audit
After every edit pass, run a STYLE-2 grep audit on the full plan file. Check for violations
that block the PASS report:

```bash
grep -En '[0-9a-f]{7,40}' .ai/BRANCH_PLAN.md          # VALIDATED: SHA patterns, mr script extraction deferred
grep -En 'commit [0-9]|Phase [0-9][a-z]?|Step [A-Z]' .ai/BRANCH_PLAN.md  # VALIDATED: opaque codes, deferred
grep -En '\(this turn\|this session\|prior turn\|verified this turn\)' .ai/BRANCH_PLAN.md  # VALIDATED: deferred
grep -En '[0-9]{4}-[0-9]{2}-[0-9]{2}' .ai/BRANCH_PLAN.md  # VALIDATED: date patterns, deferred
grep -c '<!-- begin-deleted-historical' .ai/BRANCH_PLAN.md  # VALIDATED: HTML history markers, deferred
grep -Ein 'gitter|plan-writer|refactorer\x27s|coder\x27s|fixer\x27s|featurer\x27s|orchestrator-persistent|\b(AGT|WF|DEL|DOC|PLAN|STYLE|PW|G|R|CODER|TW)-[0-9]+\b' .ai/BRANCH_PLAN.md  # VALIDATED: role/rule-ID names, deferred
```

These six overlap the stale-reference checks inside `mr script audit_plan`;
folding them in is deferred pending its own design review (BRANCH_PLAN.md).

Each non-zero hit must be confirmed as an acceptable carve-out (append-only Decisions Log
entry, anti-pattern example, current-state declaration) OR scrubbed before reporting PASS.

**Completion checklist:**
- [ ] STYLE-2 grep ran on full BRANCH_PLAN.md
- [ ] Zero unresolved hits (all hits confirmed as carve-outs or scrubbed)

### Phase 5: Verify
Read back changed sections. Confirm checkbox state, wording, Decisions Log format.
Report diff summary to orchestrator.

**Completion checklist:**
- [ ] All requested edits applied
- [ ] Each edit re-read post-write to confirm wording
- [ ] Decisions Log entries follow `<domain> - <summary> - <details>` format
- [ ] No source code, test files, or skill files were touched
- [ ] STYLE-2 audit PASS
- [ ] Diff summary reported to orchestrator

### Phase 6: Critique Pass (on-demand or after substantive edits)
On the first pass, re-read the entire plan (an unfamiliar file falls
outside the ranged-read case below). On every later loop, bound the
re-read to the sections named in the prior pass's disposition list and
suspicious-claims table, per AGT-3 FRESH-CONTEXT's `file:start-end`
citation discipline, widening to a full re-read only if a cross-section
contradiction is suspected. Produce:

**(a) Section-by-section disposition list:**
Each section: KEEP / REWRITE / DELETE / MERGE - one-line justification evaluated against
STYLE-2 criteria (audience, action, stability, specificity, currency).

**(b) Suspicious claims table:**
Every factual assertion that warrants re-verification: cited file:line, symbol names,
version behaviors, commit SHAs, URLs, "X uses Y" cross-references. For each claim:
verify against current ground truth (code, docs, reflog). Mark VERIFIED / STALE / UNVERIFIABLE.

Output both tables BEFORE applying any edits. Await orchestrator review.

**Loop:** Repeat Phase 6 after each round of accepted edits until a full re-read produces
zero new section dispositions AND zero new suspicious-claims entries. Convergence on a
clean pass is the termination condition.

**Escalation escape hatch:** If a suspicious claim cannot be resolved by reading code/docs
alone (requires human judgment about design intent, original author context, or whether a
commit is still reachable), send a SendMessage to `main` (the orchestrator) listing the
unresolvable claims. Loop pauses at escalation points until claims are resolved.
Convergence requires all escalations answered.

**Completion checklist:**
- [ ] Section disposition list produced
- [ ] Suspicious-claims table produced with VERIFIED / STALE / UNVERIFIABLE for each
- [ ] All STALE claims scrubbed or confirmed as intentional
- [ ] All escalations sent to the orchestrator and resolved
- [ ] Final re-read produces zero new findings (convergence)

### Phase 7: WF-11 orchestrator post-completion E2E verification (orchestrator-side, after plan-writer reports CONVERGED)

After plan-writer SendMessages its CONVERGED report to the orchestrator, the orchestrator MUST perform WF-11 verification:

1. Read plan-writer's diff summary and the sections it cites as changed (per AGT-3 FRESH-CONTEXT's ranged-read discipline). Widen to a full, chunked end-to-end read only if the diff summary looks incomplete, stale, or doesn't cover a section the report claims to have touched.
2. Hunt for: stale cross-references, internal contradictions (section A vs section B), silent omissions, editorial leaks, STYLE-1 / STYLE-2 violations plan-writer didn't surface, claims in plan-writer's report that aren't actually true in the file (e.g., "added 12 entries" → count them).
3. Spot-verify plan-writer's report claims directly (grep for "added X" / read the section that was "tightened" / etc.).
4. If gaps: SendMessage plan-writer with the specific gap list; back to Phase 3 (or re-dispatch the targeted edit). Do NOT fix-by-orchestrator unless DEL-1's trivial-edit exception applies.
5. Only after WF-11 passes: accept the deliverable and proceed.

**Completion checklist:**
- [ ] Plan-writer's diff summary read; full end-to-end read only if that summary looked incomplete
- [ ] Each plan-writer-claimed change spot-verified against the file
- [ ] Zero gaps OR all gaps redispatched + re-verified
- [ ] WF-11 verification PASS printed visibly per WF-6A PRINT-GATES

---

### Phase 8: RULES CHECK - verify the work against this role's rules

Follow the procedure at
`~/.claude/skills/orchestrator/shared/rules-check-procedure.md` against
`~/.claude/skills/orchestrator/roles/plan_writer/rules.md` (PW-2 through
PW-7), scoped to the changed plan/README paths.
