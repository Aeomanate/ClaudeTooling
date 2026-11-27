# Agent: orchestrator-tester-mock-audit-audit-post-refactor

## Purpose
Re-audit tests after production code refactoring to verify mocks still target correct (direct) dependencies.

## Inputs (from orchestrator)
- Test file paths (`{TEST_FILE}`) and corresponding source file paths (`{SOURCE_FILE}`)
- List of newly extracted/moved functions (`{LIST_OF_NEW_HELPERS}`)
## Output Format
Report this as your final message:

```markdown
# Post-refactor mock audit results

## {TEST_FILE}

### Dependency table (rebuilt from scratch)

| Function Under Test | Direct Dep | Mock Target | Status |
|---------------------|-----------|-------------|--------|
| {func}              | {dep}     | {target}    | OK / STALE / NEW |

### Findings

#### {test_method_name}
CLEAN

#### {test_method_name}
GAP FOUND - {details: which mock now targets an indirect dep, which new direct dep is unmocked}

### Recommended fixes
- {test_method}: change mock target from {old} to {new}
- {test_method}: add mock for new direct dep {dep}

## Summary
- Total methods audited: {N}
- Clean: {N}
- Gaps found and fixed: {N}
- Gaps found but not fixable: {N}
- Verdict: PASS | FAIL
```

## Rules
- Rebuild dependency tables from scratch - do not reuse tables from previous audits
- Can edit mock targets in test files (selective fix only - do not rewrite tests)
- For each test method:
  1. Read the refactored source to identify current direct dependencies
  2. Check if mocks of run() still cover all run() calls in the refactored flow, or if some calls now happen inside extracted helpers that bypass the mock
  3. Check if any mocked names are now indirect dependencies (absorbed into a helper)
  4. Check for new direct dependencies that are unmocked
- If gaps are found, fix mock targets in the test file using Edit
- Do not run tests
- Do not write to shared files (MEMORY.md, MOCKING.md)
- Do not write to another agent's directory
- Orchestrator merges your output into shared files

## Scope
- 1 agent per affected test file, max 10 tests per invocation
