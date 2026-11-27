## Mock Audit Workflow

WORKFLOW NAME: Mock Audit

Convergence loop that audits mock correctness for all tests in scope.
Converges when an audit pass finds zero new gaps.

**When to run:**
- Before running ANY tests (mandatory, no exceptions)
- After refactoring production code (function boundaries change, mocks may become stale)
- As part of the test-writing workflow (Step 3: VERIFY)
- As Loop A of the refactorer workflow

**Execution model**: See orchestrator conventions (Section 2: Orchestrator Execution Model).

**NEVER skip this workflow. NEVER run tests before it passes.**
Running tests before the audit can mask broken mocks - a test may pass
by accident because the real function is now called instead of the mock.

---

### Phase 1: AUDIT - diagnose mocks against what's already there (PLAN MODE)

For each test method in scope, start from its EXISTING mocks (what's
already `@patch`'d or context-managed in the test today), then diagnose:
does it need a mock it doesn't have (a leak - a direct dependency running
for real), or does it have a mock it shouldn't (an indirect dependency
masking what the direct one actually does)? This is not building a table
from a blank slate - every diagnosis starts from the test's current
mock state.

| dependency | type | mocked? | direct/indirect | action |
|------------|------|---------|-----------------|--------|

#### Step 1.1: Spawn audit agents once, then reuse them

First pass through this phase: launch agents (1 per 10 tests) using
[mock audit agent](agent-instructions/audit-build-tables.md) template.
Keep each agent's agentId. Every loop-back from Phase 4 re-enters the same
instances via `SendMessage` instead of spawning fresh ones (AGT-1's
reuse-before-spawning rule) - same reuse pattern as Phase 3's Verify
sub-agent. A reused agent already has its own prior findings in context,
so a loop-back re-diagnoses against what it already knows, not a repeat
of the whole rules read plus a from-scratch scan of tests it already
confirmed clean.

Each agent reads test code + production code, diagnoses gaps against the
test's existing mocks.

Each agent reports its dependency table in its final message.

#### Step 1.2: Merge agent outputs

Orchestrator assembles all agent results into `{ARTIFACTS_DIR}/MOCKING.md`.

#### Step 1.3: Per-test assessments

After each dependency table, record three assessments:

- **Function refactoring required:** YES/NO - (N lines, M deps, reason)
  - YES if: function >= 50 lines, OR 5+ mocks needed, OR I/O mixed with logic
- **Was dependency missed/absent:** YES/NO - list any unmocked direct deps
- **Improvements:** list any test quality issues found:
  - Missing assertions (return code, mock call args, mock not-called)
  - Test passes for wrong reason (validates wrong behavior path)
  - Missing edge cases (boundary values, error paths)
  - Naming/docstring inaccuracy (test name doesn't match what it tests)
  - Dead code in test (unused variables, unreachable assertions)

Improvements are NOT blocking - they feed back to the test-writing
workflow. But they MUST be recorded, never skipped.

**Completion checklist:**
- [ ] One agent per ≤10 tests launched (or re-entered via SendMessage on a loop-back)
- [ ] All agent outputs merged into MOCKING.md
- [ ] Per-test assessments recorded (refactoring required, dependency missed, improvements)

---

### Phase 2: FIX - resolve all gaps (EXIT PLAN MODE)

For each "missed/absent" = YES:

#### Step 2.1: Add missing mocks

Add the missing mock (patch at IMPORT location, not source).
See tester rules for the main mock rule.

#### Step 2.2: Remove indirect mocks

Remove any mocks that target something inside a dependency rather
than the dependency itself.

#### Step 2.3: Split oversized tests

If a test tests too much in one method, split into separate tests.
Rule: after this step, zero unmocked direct deps, zero indirect mocks.

**Completion checklist:**
- [ ] All missed-direct-deps mocked
- [ ] All indirect mocks removed
- [ ] Oversized tests split where needed

---

### Phase 3: VERIFY - confirm fixes (via sub-agent) (PLAN MODE)

#### Step 3.1: Spawn the Verify sub-agent once, then reuse it

First pass through this phase: spawn the Verify sub-agent using
[gap verification agent](agent-instructions/verify-gaps.md) template. Keep
its agentId. Every loop-back from Phase 4 re-enters this same instance via
`SendMessage` instead of a fresh `Agent` call (AGT-1's
reuse-before-spawning rule). The sub-agent re-reads MOCKING.md tables and
confirms zero remaining gaps. This is a READ-ONLY check - the sub-agent
does NOT edit code.

#### Step 3.2: Run tests + leak check

ONLY after the Verify sub-agent confirms zero gaps:

```bash
mr verify  # VALIDATED: wraps ruff + full unittest discover + mr script leak_check
```

`mr script leak_check` checks FOUR things (see tester rules - Leak Check Criteria).

#### Step 3.2a: Coverage check

After tests pass, run coverage on the affected modules:

```bash
coverage run --branch -m unittest <module>.tests  # VALIDATED: module-scoped, not the full-repo run_coverage wrapper
coverage report --show-missing  # VALIDATED: module-scoped, not the full-repo run_coverage wrapper
```

Verify all unit-testable paths in new/modified code are covered.
If gaps found, note them for the test-writing workflow - do not
block the mock-audit convergence loop for coverage gaps.

#### Step 3.3: Handle failures

If timeout exceeded (exit code 2): run full refactoring pipeline to find
mock gaps causing real I/O. If pipeline is clean, increase
`TEST_TIMEOUT_SECONDS` by 1 and repeat. Only the orchestrator may
increase the timeout, and only after confirming zero mock violations.

If any other check fails: find the leak, fix it, re-run.

**Completion checklist:**
- [ ] Verify sub-agent (same instance across loop-backs) confirms zero remaining gaps
- [ ] Tests run + leak check pass
- [ ] Coverage check on affected modules

---

### Phase 4: DECIDE - loop or proceed (PLAN MODE)

- If Phase 1 found new gaps: commit fixes, go back to Phase 1.
- If Phase 1 found zero gaps: converged, exit loop.

**Completion checklist:**
- [ ] Loop decision recorded (back to Phase 1 if new gaps found, else exit loop)

---

## Post-Refactor Variant

When running after production code refactoring, use the
[post-refactor audit agent](agent-instructions/audit-post-refactor.md)
template instead of `mock_audit.md`. This variant specifically checks
whether refactoring changed function boundaries in ways that make
existing mocks target indirect dependencies instead of direct ones.

Spawn fresh agents for this variant - do not reuse Phase 1's persistent
audit agents or their prior findings. Refactoring changed function
boundaries, so an agent's earlier "already diagnosed, mocks are fine"
conclusion may no longer hold; tables must be rebuilt from scratch here,
unlike the normal mock-audit loop above.
