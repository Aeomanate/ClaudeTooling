## Fixer Workflow

WORKFLOW NAME: Fixer

Structured debugging workflow, used automatically when fixing a reported bug
or unexpected behavior. Each step has ONE focus: complete it, present
results, get developer approval, then move to the next.

**When to invoke:**
- Bug report - user reports incorrect behavior
- Test failure - existing test started failing after a change
- Unexpected state - system shows wrong status, data, or output
- Regression - feature broke after a change
- Tool integration issue - CLI tool, API, or config not working

---

### Phase 1: INVESTIGATE - Prove by hands (PLAN MODE)

**Goal:** reproduce the problem by running actual commands. No code changes,
no assumptions, only evidence.

#### Step 1.1: Read logs

```bash
mr script read_logs
```

#### Step 1.2: Read source code (via sub-agent)

**NEVER run the failing command directly.** Delegate to a sub-agent per DEL-2:
- Read the entry point and routing for the failing command
- Trace the code path from CLI invocation to the failure point
- Read config files, argument parsing, flag bridging
- Identify where the code path diverges from expected behavior

#### Step 1.3: Isolate root cause

Assess blast radius before proposing any fix - which callers, which tests,
which behaviors change. Prove the root cause from logs and code rather than
hypothesizing; never guess at an execution path that can be traced.

Trace through code and logs, not by re-running:
- Read config files (check for missing fields, dropped flags)
- Read entry points and dispatch chains (check argument bridging)
- Read log output from previous runs (`.ai/artifacts/hook.log`)
- A minimal safe diagnostic (`--help`, `--version`, `--dry-run`) goes to a sub-agent - the orchestrator never runs commands directly

#### Step 1.4: Test hypothesis

A suspected cause is proven, not assumed:
- Fix the config and re-run - does it work now?
- Call the API directly - does raw curl succeed?
- Search for the user/resource - does it exist?

#### Step 1.5: Document findings

Compile for the report to the orchestrator:
- What broke and why, with evidence rather than guesses
- Exact commands run and their output
- Root cause for each issue
- What config or manual action fixes, versus what needs code

**Completion criteria:**
- Every reported symptom has a confirmed root cause
- Each root cause proven with a command, not assumed
- Findings documented with commands + output

Then: present findings to the developer, get approval to proceed.

---

### Phase 2: PLAN - Pre-implementation (PLAN MODE)

**Goal:** write the exact code changes. Every fix fully specified with
current code, new code, and rationale. No implementation yet.

#### Step 2.1: Read affected source files

Understand the full function, not just the failing line, and check callers
and callees.

#### Step 2.2: Write exact changes

For each fix, write in the temp plan:
- File path and function name
- Current code (copy from source)
- New code (exact replacement)
- Why this change fixes the root cause from Step 1
- What logs the new code produces, for debug visibility

#### Step 2.3: Check ripple effects

- What tests assert the current behavior, and so need updating
- What other callers use this function, and might break
- Whether the change affects the return type or signature

#### Step 2.4: Write test outlines

For each fix, sketch the test:
- Test class and method name
- Docstring with input -> expected output
- Mock setup (what to patch, what to return)
- Key assertion

#### Step 2.5: Check related setup/config

A bug caused by a config issue means checking the setup script that writes
that config for the same bug. Runtime is not fixed without setup.

**Completion criteria:**
- Temp plan has exact current + new code for every fix
- Every fix has a test outline
- Ripple effects identified - tests to update, callers to check
- Developer has reviewed and approved the plan

---

### Phase 3: IMPLEMENT - Apply changes (EXIT PLAN MODE)

**Goal:** apply the code changes from the plan. Production code only, no
tests yet.

#### Step 3.1: Implement one fix at a time

Follow the temp plan exactly - no deviating, no improving beyond what was
planned.

#### Step 3.2: Mock audit via tester handoff

**Mandatory** per MA-4 AUDIT-BEFORE-TESTS: never run tests until the mock
audit is complete. The orchestrator delegates to the tester mock-audit
workflow rather than running the mock auditor agent itself.

Formal handoff protocol:

a) **Prepare scope** - list all new/modified test files and their production targets
b) **Delegate** - send tester mock-audit task via SendMessage; include scope list
c) **Wait** - tester runs full 4-phase mock-audit pipeline (AUDIT → FIX → VERIFY → DECIDE)
d) **Resume** - receive tester's CLEAN/FIX report via SendMessage
e) **Present** - relay the result to the orchestrator via `SendMessage(to: "main", ...)` for an AskUserQuestion approval gate before test execution. Fixer has no direct `AskUserQuestion` access; classic schema, AGT-26 RELAY-IDENTIFY.

Test execution is never auto-approved - the developer decides when to run.

#### Step 3.3: Verify fix in isolation (via Verify sub-agent)

A fresh Verify sub-agent runs incremental tests for the affected module,
catching regressions before the next fix starts.

#### Step 3.3a: Refactorer rules check

New and modified code is checked against R1-R14 via a rule-scanner agent
before test updates, and violations are fixed here rather than surfacing in
gitter's Phase 2.2.

#### Step 3.4: Handle new failures

A new failure is analyzed before anything else proceeds. Broken fixes do not
accumulate.

#### Step 3.5: Update conflicting tests

A test breaking because the fix changed behavior it asserted gets updated.
Only directly conflicting tests are touched.

#### Step 3.6: Convergence check

Before committing, both audit roles report zero findings:

- Mock audit (Step 3.2): tester reported CLEAN.
- Rule-scanner (Step 3.3a): refactorer reported zero R1-R14 violations.

Findings from either mean applying fixes and re-dispatching that role fresh,
per AGT-3 FRESH-CONTEXT with no carry-forward, until both report
`CONVERGED - no further changes pending`.

**Completion checklist:**
- [ ] Tester mock-audit: CONVERGED - no further changes pending
- [ ] Rule-scanner (R1-R14): CONVERGED - no further changes pending

#### Step 3.7: Commit via gitter workflow

**Mandatory:** every commit goes through gitter's pre-commit workflow - the
orchestrator hands off for the full 5-phase pipeline: gather, review, verify,
approve, commit. The fixer runs no git commands itself, even for "just one
commit."

**Completion criteria:**
- All fixes from the plan implemented
- Existing tests pass, or updated where expected
- Each fix committed separately
- No silent code paths - every branch logs

Then: present the diff summary to the developer, approve for production test.

---

### Phase 4: VERIFY - Production test (PLAN MODE)

**Goal:** trigger the real workflow and verify fixes work end-to-end.

#### Step 4.1: Developer pushes branch

```bash
git push
```
Works from any terminal, including Claude Code.

#### Step 4.2: Check logs immediately

```bash
mr script read_logs
```

#### Step 4.3: Verify each fix in logs

Every fix from the temp plan has a corresponding log line. A fix that added a
log message means that message appears; a fix that changed behavior means the
old pattern is gone and the new one present.

#### Step 4.4: Check end result

MR on GitLab, CLI output, tool state - whatever the fix was supposed to
improve is verified visually.

Something wrong means reading the log, identifying which fix didn't work, and
returning to Phase 2 for that specific fix. Never patch blindly.

**Completion criteria:**
- Push succeeded
- Log shows expected messages for each fix
- MR on GitLab looks correct
- No unexpected errors or warnings

Then: present log excerpts to the developer, approve for test writing.

---

### Phase 5: UNIT-TESTS - Write regression tests (EXIT PLAN MODE)

**Goal:** write or update unit tests covering each fix.

#### Step 5.1: Delegate to test-writing workflow

All tests follow the test-writing workflow, taking run commands, writing
rules, mock patterns, docstring conventions and the post-run checklist from
tester rules.

#### Step 5.2: Write tests from Phase 2 outlines

For each fix, write the test(s) from the Step 2.4 outlines.

#### Step 5.3: Update conflicting existing tests

- A fix that changed a return type means updating tests asserting the old one
- A fix that removed behavior means removing or rewriting tests asserting it
- No test is deleted silently - the commit message says why

#### Step 5.4: Update manual tests

Fixes changing user-facing behavior update BRANCH_PLAN.md's manual testing
section, per manual.md rules.

**Completion criteria:**
- Every fix has at least one test
- Post-run checklist passes - all green, zero unexpected ERR/WARN
- Coverage maintained or improved
- Manual tests updated if user-facing behavior changed
- Tests committed

---

### Phase 6: WRAP-UP (EXIT PLAN MODE)

#### Step 6.1: Update BRANCH_PLAN.md

Check off completed items and update the Decisions Log with fix details, per
plan-writer rules.

#### Step 6.2: Update temp plan

Mark all items done.

#### Step 6.3: Collect MEMORY.md proposals

Present patterns, gotchas and new conventions discovered during the fix.

#### Step 6.4: Update patterns

Errors or new patterns found go into the patterns catalog for future
reference.
