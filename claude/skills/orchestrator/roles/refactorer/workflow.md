## Refactorer Workflow - convergence loops and audit pipeline

Background knowledge for the refactorer role. Loaded automatically when
the refactorer is active.

For agent conventions (naming, state, output schemas), see conventions.md.

## Scripts

| Command | What it does | When to use |
|--------|-------------|-------------|
| `mr script leak_check` | Check hook.log + TESTS.log + BRANCH_PLAN.md integrity | After any test run |

> **Test execution is language-specific.** Where a step says "run tests" or
> "run coverage", use the project's own runner (Python: `python -m unittest` /
> `coverage`; C++: `mr script run_cpp_tests`), then verify with
> `mr script leak_check`.

## Execution model

See orchestrator conventions (Section 2: Orchestrator Execution Model) for
agent limits, context discipline, isolation rules, and the "never run tests
before audit" rule.

---

## Full refactoring algorithm

Three convergence loops in sequence, each repeating until it finds nothing
new, then one clean-room pass to confirm stability, then pre-commit.

```
Phase 1: Mock audit convergence (MOCKING.md)
  |
  v
Phase 2: Refactoring rule convergence (REFACTORING_VIOLATIONS.md)
  |
  v
Phase 3: Test coverage convergence (COVERAGE_GAPS.md)
  |
  v
Phase 4: Clean-room re-audit (all tables rebuilt from scratch)
  |
  v
If gaps found --> back to Phase 1
If clean --> Phase 5 pre-commit --> commit
```

**Any structural change with more than one possible shape goes to the
developer first** - a class name, a responsibility split, a pattern choice, a
renamed return value, an added parameter, a changed function contract.
Refactorer has no direct `AskUserQuestion`, so it relays via
`SendMessage(to: "main", ...)` in AGT-26 RELAY-IDENTIFY's classic schema:

- What needs to change and why, the root problem
- Option A: the exact approach ("return tuple from function X")
- Option B: the alternative ("add parameter to caller Y")
- Tradeoffs: which callers break, how many files, test impact

Implement after the developer picks.

---

### Phase 1: MOCK AUDIT - convergence loop (PLAN MODE)

Delegates to the tester mock-audit workflow, scoped to all tests touching
changed production files. Converges when that workflow exits with zero gaps.

**Completion checklist:**
- [ ] Tester mock-audit workflow ran to convergence
- [ ] Zero gaps remaining

---

### Phase 2: RULE CONVERGENCE - convergence loop (EXIT PLAN MODE)

Converges when a full codebase scan finds zero new rule violations.

#### Step 2.1: Scan against R1-R14

Load the smells and patterns indexes before dispatching the scanner (R14):

```bash
mr script dump_code_quality_reference
```

Deep-read a specific smell or pattern file only for a candidate that looks
plausible but non-obvious.

Refactorer spawns its own general-purpose sub-agent (sonnet), per AGT-1 - a
persistent sub-agent may dispatch per-task sub-agents. Per AGT-3 the dispatch
carries the rules path
(`~/.claude/skills/orchestrator/roles/refactorer/rules.md`, R1-R14) and the
file scope; the agent reads the rules itself and stays read-only.

An uncertain file scope gets a search sub-agent (or the built-in `Explore`
agent) first to enumerate targets, then the rule-scan agent with an explicit
list.

The scanner emits one row per function in scanned files, test files excluded:

| function | file:line | lines | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | R9 | R10 | R11 | R12 | R13 | action |
|----------|-----------|-------|----|----|----|----|----|----|----|----|----|-----|-----|-----|-----|--------|

Each R column is PASS or VIOLATION with a brief reason. The scanner reports the
table in its final message; refactorer consolidates into
`{ARTIFACTS_DIR}/REFACTORING_VIOLATIONS.md`.

Also produce `{ARTIFACTS_DIR}/functions_to_refactor.md`, one actionable table
per file:

| function name | need refactor | reason | evidence | refactoring suggestions |
|---------------|---------------|--------|----------|-------------------------|

Tiers: Tier 1 (100+ lines, 8+ deps) decompose first; Tier 2 (50+ lines, 5+
deps) extract pure functions; Tier 3 (50+ lines, pure) readability only.

#### Step 2.1a: Smell & pattern analysis (PLAN MODE)

Runs only when a scan row shows a branching, wrapping or creation decision to
make. Otherwise skip it and say so.

For each function with SMELL or PATTERN columns filled:

1. Look the pattern up in `patterns/ai_index.md` decision trees.
2. Confirm it fits this specific code context.
3. Propose the refactoring with current code evidence (file:line), the
   detected smell, the recommended pattern and technique, and a before/after
   sketch.
4. The developer approves or rejects each suggestion.

Only approved pattern choices reach Step 2.1b.

#### Step 2.1b: Discuss the selected pattern

A pattern name is not a design: the same pattern takes different shapes
depending on ownership, lifetime and how the call site is reached. Selecting
one authorizes nothing.

Present the concrete shape:

- the exact call site or construct it replaces
- who owns each new object, and how long it lives
- pros: what this buys, in this codebase
- cons: added indirection, new files, test surface, what gets harder to read
- the alternative, including doing nothing

Relay via `SendMessage(to: "main", ...)` for the ask (AGT-26, classic schema).
Options: apply the pattern, apply a named alternative, or leave the code as it
is. Put the pros and cons in the option descriptions - the developer reads the
orchestrator's context, not this file.

Edit after the developer answers.

**Completion checklist:**
- [ ] Concrete shape stated, not just the pattern name
- [ ] Pros and cons both present, including the cost of the pattern
- [ ] "Leave as is" offered as a real option
- [ ] Developer answered

#### Step 2.1c: Cross-check via the project's review skill

Some projects carry a comprehensive code-review skill (`review-mr` in PRODUCT NAME and
reponame-family projects) covering what R1-R14 does not: language safety,
performance, backward compatibility, project-specific architecture. Check
whether the current project has one; skip and say so otherwise.

Dispatch a separate one-shot general-purpose sub-agent to invoke it, scoped to
the same files as Step 2.1 and running in parallel with it - the two scan
independently and neither needs the other's output.

Consolidate both sets into `{ARTIFACTS_DIR}/REFACTORING_VIOLATIONS.md` before
Step 2.2, tagging each row with its source (`R1-R14` or the skill's name) so
every finding stays traceable.

**Completion checklist:**
- [ ] Checked whether the project has a comprehensive review skill
- [ ] If yes: dispatched a separate one-shot agent, in parallel with Step 2.1
- [ ] If no: skipped, with the reason stated
- [ ] Findings from both sources consolidated into one violations table, tagged by source

#### Step 2.2: Decompose functions

Decompose as far as possible without human approval. Controversial points -
class extraction, architectural changes - go to
`{ARTIFACTS_DIR}/TODO_human_review.md` as TODOs.

For each Tier 1/2 function (R1):

1. Identify I/O operations: subprocess calls, CLI tools, file reads, API calls.
2. Identify pure logic: transforms, comparisons, data building.
3. Extract the pure logic into separate functions, 0-2 deps each.
4. The orchestrating function becomes validate, call helpers, handle errors.
5. Existing tests pass unchanged - no edits to test files.

One commit per extracted function, never mixed with feature work.

**Do not run tests after refactoring until the mock audit passes clean.**
Refactoring moves function boundaries, which changes what counts as a direct
dependency, so a test can pass by accident against the real function instead of
its mock.

After the last refactoring commit, re-run Phase 1 and let it converge at zero
gaps before Step 2.3.

#### Step 2.3: Post-refactor audit

Run the mock-audit workflow with the `post_refactor_audit.md` template, scoped
to every test touching a refactored function. Rebuild dependency tables from
scratch and fix new gaps. Zero gaps before Step 2.4.

#### Step 2.4: Write tests + fix improvements

Two tasks in parallel once Step 2.3 is clean.

**2.4-new: tests for extracted functions.** Delegate to the test-writing
workflow per function: direct unit tests at 0-2 mocks each, pure functions
tested input to output with no mocks, I/O wrappers mocking only direct deps
(`run`, `find_tool`).

**2.4-fix: improvements from the Phase 1 audit.** For every "Improvements"
entry: add missing assertions, rewrite a test that passes for the wrong reason,
write new methods for missing edge cases, correct inaccurate names and
docstrings, remove dead test code.

**2.4a - mock audit for the new tests, mandatory.** Both tasks produce test
code, so run the mock-audit workflow scoped to what was just written. Only at
zero gaps, run the tests:

```bash
# Execute the project's test runner (Python: `python -m unittest discover`;
# C++: `mr script run_cpp_tests`; etc.) then verify with mr script leak_check
mr script leak_check
```

Update `{ARTIFACTS_DIR}/MOCKING.md` with the new entries. The extracted helpers
raise the test count substantially.

#### Step 2.5: Loop decision

New violations in Step 2.1: commit refactoring plus tests, return to Step 2.1.
Zero: Phase 2 converged, proceed to Phase 3.

**Completion checklist:**
- [ ] Full R1-R14 scan complete; functions_to_refactor.md tier-classified
- [ ] All Tier 1/2 functions decomposed
- [ ] Post-refactor mock audit re-run: zero gaps
- [ ] Tests written for extracted functions; mock-audited before run
- [ ] Loop decision recorded (loop or proceed)

---

### Phase 3: COVERAGE CONVERGENCE - convergence loop (EXIT PLAN MODE)

Converges when every unit-testable flow is covered and no new gap appears.

#### Step 3.1: Run coverage

```bash
# Execute the project's coverage tool (Python: `coverage run --branch -m unittest discover`;
# C++: `gcovr`; etc.); produce branch coverage report
```

Omitted, project-specific via `{COVERAGE_OMIT}`: UI modules, which are not
unit-testable; entry point wrappers, thin shims covered by integration tests;
test code itself.

#### Step 3.2: Analyze gaps

For each module under 100% branch coverage, read the `--show-missing` output
and classify each uncovered flow:

- **Unit-testable** - pure logic or a mockable I/O path: MUST COVER
- **Integration-only** - needs a real subprocess or network: skip, marked integration
- **Error path already tested** - defensive `try`/`except`: skip
- **Platform-specific** - a Windows-only or Unix-only branch: fine when the other platform covers it

Produce `{ARTIFACTS_DIR}/COVERAGE_GAPS.md`:

| module | line range | flow description | testable? | action |
|--------|-----------|------------------|-----------|--------|

#### Step 3.3: Write tests for gaps

Delegate to the test-writing workflow, scoped to the MUST COVER gaps. That
workflow runs its own mock audit and execution steps.

#### Step 3.4: Verify

Full suite passes, hook.log absent, TESTS.log empty, BRANCH_PLAN.md intact.

#### Step 3.5: Loop decision

New unit-testable gaps: commit tests, return to Step 3.1. Zero: Phase 3
converged, proceed to Phase 4.

**Completion checklist:**
- [ ] Branch coverage report generated
- [ ] Each gap classified (unit-testable / integration-only / error-path / platform)
- [ ] All MUST-COVER gaps have new tests
- [ ] Full suite passes; leak check clean
- [ ] Loop decision recorded

---

### Phase 4: FINAL PASS - clean-room re-audit (PLAN MODE)

Once all three loops converge, run `mr script classify_diff` once, then one
complete pass from scratch:

1. Delete every previous `{ARTIFACTS_DIR}/audit_*.md`.
2. Rebuild the dependency table from scratch, copying nothing forward: every
   test method on a `standard` diff (G7A MECHANICAL-DIFF-TIER), or only tests
   importing a file the diff touches on a `mechanical` one. Re-read source and
   test either way.
3. Re-check both columns: refactoring required, missed deps.
4. Write a fresh `{ARTIFACTS_DIR}/MOCKING.md`.

Any gap sends the work back to Phase 1. Zero gaps produces the final summary
table and moves to Phase 5.

| Smell ID | File:line | Severity | Fix applied | Recommended follow-up |
|----------|-----------|----------|-------------|----------------------|

Severity is HIGH (structural, over 50 lines), MEDIUM (behavioral) or LOW
(cosmetic). Fix applied names the exact refactoring made this session, or
"none - deferred". Recommended follow-up carries the R-rule number or pattern
name for a deferred fix.

This table is the converged report behind the orchestrator's Phase 3.2
consistency checks and the gitter Phase 2 handoff. Send it via `SendMessage`.

**Completion checklist:**
- [ ] Previous audit files deleted
- [ ] Dependency tables rebuilt from scratch (full scope on `standard`, diff-touched scope on `mechanical`)
- [ ] Fresh MOCKING.md written
- [ ] Zero gaps found (else loop back to Phase 1)
- [ ] Final findings summary table produced and sent to the orchestrator

---

### Phase 5: PRE-COMMIT - follow gitter pre-commit workflow (EXIT PLAN MODE)

With the final pass at zero gaps, hand off to the gitter pre-commit workflow,
the single source of truth for pre-commit.

The refactorer rules-file path goes into gitter's Step 2.2 dispatch, which runs
`shared/rules-check-procedure.md` once per pipeline, STYLE-8 comment-style pass
included. That one run covers the refactorer rules check.

**Completion checklist:**
- [ ] Gitter pre-commit workflow handed off
- [ ] Refactorer rules path passed into gitter's Step 2.2 dispatch
- [ ] All 5 gitter phases complete with developer approval
