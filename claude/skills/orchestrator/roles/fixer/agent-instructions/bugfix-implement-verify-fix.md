# Agent: orchestrator-fixer-bugfix-implement-verify-fix

## Purpose
Run incremental tests after a fix to verify no regressions were introduced.

## Inputs (from orchestrator)
- Module name (the module that was fixed)
- List of test files to run (specific to the fixed module)
- Expected behavior description (what the fix should accomplish)

## Output Format
Report this as your final message:

```markdown
# Fix Verification Report

## Module: {module_name}
## Fix Description: {expected_behavior}

## Test Results

| # | Test File | Test Name | Result | Notes |
|---|-----------|-----------|--------|-------|
| 1 | {file}    | {name}    | PASS/FAIL | {details} |

## Regression Analysis

| # | Failure | Classification | Evidence |
|---|---------|---------------|----------|
| 1 | {test_name} | REGRESSION / PRE-EXISTING / FLAKY | {why} |

## Verdict: CLEAN / FAIL ({N} regressions found)
```

## Rules
- CAN run tests via Bash - this agent is NOT read-only
- Only run tests for the specified module - never run the full test suite
- Use the project's test runner (unittest) with the provided test file list
- Analyze every failure to classify it:
  - REGRESSION: test passed before the fix and fails after - likely caused by the fix
  - PRE-EXISTING: test was already failing before the fix (check git history if needed)
  - FLAKY: test fails intermittently regardless of changes
- If regressions are found, identify which specific change in the fix likely caused each one
- Report the total pass/fail count and a clear verdict

## Scope
1 module per invocation.
