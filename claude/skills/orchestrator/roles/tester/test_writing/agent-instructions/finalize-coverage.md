# Agent: orchestrator-tester-test-writing-finalize-coverage

## Purpose
Write new tests for UNIT_TESTABLE coverage gaps identified by coverage analysis.

## Inputs (from orchestrator)
- Source module path (`{SOURCE_MODULE}`)
- Existing test file path (`{TEST_FILE}`)
- Table of gaps from coverage analysis (line ranges, flow descriptions, testable classification)
## Output Format
Report this as your final message:

```markdown
# Coverage test-writing results

## Source module
{SOURCE_MODULE}

## Tests written

| Test Name | Covers (function:lines) | Gap Description |
|-----------|------------------------|-----------------|
| test_{function}_{scenario} | {func}:{L1}-{L2} | {flow description} |

## Modified files
- {TEST_FILE}

## Summary
- Tests written: {N}
- Gaps addressed: {N}
- Gaps skipped (reason): {N}
- Verdict: DONE | PARTIAL
```

## Rules
- Write one test per uncovered branch/flow
- Add tests to the existing test file (`{TEST_FILE}`) - do not create new test files
- Mock only direct dependencies of the function under test (0-2 mocks per test)
- Test naming: `test_{function}_{scenario}` (e.g., `test_save_cache_uuid_mismatch`)
- Docstrings: describe the business behavior, not the mock setup
- Logging: use module-level patchers (already in setUp if present)
- run(): mock at the import location (`{PACKAGE}.module.run`)
- Pure functions: do not mock
- Do not run tests - orchestrator runs tests after mock audit completes
- Do not write to shared files (MEMORY.md, MOCKING.md)
- Do not write to another agent's directory
- Orchestrator merges your output into shared files

## Scope
- 1 agent per test file, max 10 tests per invocation
