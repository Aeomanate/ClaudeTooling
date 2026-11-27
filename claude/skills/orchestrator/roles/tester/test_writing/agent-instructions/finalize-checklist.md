# Agent: orchestrator-tester-test-writing-finalize-checklist

## Purpose
Run the 8-item post-run verification checklist to confirm test batch quality.

## Inputs (from orchestrator)
- Test output (pass/fail summary from test runner)
- Coverage report (coverage percentage and uncovered lines)
- TESTS.log path
- Manual test checklist path (if applicable)

## Output Format
Report this as your final message:

```markdown
# Post-Run Verification Checklist

| # | Check | Result | Evidence |
|---|-------|--------|----------|
| 1 | All tests pass | PASS/FAIL | {X}/{Y} passed, {failures listed} |
| 2 | No leaks detected | PASS/FAIL | {leak count or CLEAN} |
| 3 | No ERR/WARN in TESTS.log | PASS/FAIL | {line numbers if found} |
| 4 | Docstrings on non-trivial tests | PASS/FAIL | {missing docstrings listed} |
| 5 | Edge cases covered | PASS/FAIL | {uncovered edges listed} |
| 6 | No duplicate coverage | PASS/FAIL | {duplicates listed} |
| 7 | Each test is meaningful | PASS/FAIL | {trivial/redundant tests listed} |
| 8 | Manual tests updated if needed | PASS/FAIL/N/A | {what was updated or why N/A} |

## Final Verdict: ALL_PASS / {N}_FAILURES
```

## Rules
- READ-ONLY - do not modify any files
- Every item must be explicitly checked with concrete evidence - no assumptions
- For item 1: parse the actual test output, count pass/fail
- For item 2: reference the leak check report from the execute phase
- For item 3: scan TESTS.log for lines containing ERR, WARN, ERROR, WARNING
- For item 4: check every test method with more than 3 lines for a docstring
- For item 5: review test inputs for boundary values, empty inputs, error conditions
- For item 6: identify tests that exercise the exact same code path with same assertions
- For item 7: flag tests that assert nothing meaningful or only test trivial getters/setters
- For item 8: if new public API was added, manual test checklist must be updated

## Scope
1 invocation per test batch.
