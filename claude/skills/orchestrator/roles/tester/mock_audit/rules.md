# Mock Audit Rules

Rules for auditing mock correctness across all tests in scope. Canonical
mock-rule bodies live in `tester/rules.md`; this file states only the
audit-specific check/anti-pattern for each.

---

## MA-1: MOCK-AT-BOUNDARY

**Statement:** Per "The Main Mock Rule" in `tester/rules.md`: the list of calls made directly inside the function under test and the list of `@patch`/`@mock` targets in its test match exactly - a patch target living inside a call the function does not make directly is an indirect dependency, and a violation.
- Bad: mocking something two levels deep in the call chain instead of the direct dependency that calls it.

---

## MA-2: PATCH-AT-IMPORT

**Statement:** Per the "Patch rules" in `tester/rules.md`: every `@patch(...)` dotted path resolves to the module that imports the target, not the module that defines it.
- Correct: `@patch('pkg.module_a.helper')`, where `module_a` imports `helper`.
- Wrong: `@patch('pkg.module_b.helper')`, where `helper` is defined.
- Bad: patching `pkg.module_b.helper` when `module_a` imports and calls it - the patch hits the wrong namespace and the real code runs.

---

## MA-3: LEAK-CHECK-CRITERIA

**Statement:** Per the "Leak Check Criteria" in `tester/rules.md`: all five criteria - `hook.log`, `tooling.log` delta, `TESTS.log`, `BRANCH_PLAN.md`, wall time - pass after any test run.
- Bad: declaring a run clean while TESTS.log is non-empty or hook.log exists; both signal real leaks that accumulate.

---

## MA-4: AUDIT-BEFORE-TESTS

**Statement:** No test run starts until the mock-audit workflow reported `CONVERGED - no further changes pending` for that same scope; a test run with no prior convergence report is a violation.
- A test passing by accident, because a stale mock let the real function run, is worse than one that fails honestly.
- Bad: running tests "to see where things stand" before the audit finishes, then treating a pass as meaningful.
