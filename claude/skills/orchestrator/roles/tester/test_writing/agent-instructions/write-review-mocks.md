# Agent: orchestrator-tester-test-writing-write-review-mocks

## Purpose
Verify every mock covers every external call in written tests.

## Inputs (from orchestrator)
- Test file paths
- Production file paths corresponding to the tested code

## Output Format
Report this as your final message:

```markdown
# Mock Review

## Test: {test_method_name} ({test_file}:{line})

| # | External Call | Mock Present? | Mock has side_effect? | Issues |
|---|---------------|---------------|----------------------|--------|
| 1 | {call}        | YES/NO        | YES/NO/N/A          | {desc} |

### Verdict: CLEAN / GAPS_FOUND
```

## Rules
- READ-ONLY - do not modify any files
- For every test method, check that:
  - Every `run()` or `subprocess` call has a mock with `side_effect` or `return_value`
  - Every CLI tool invocation (git, glab, jira, etc.) is patched
  - `webbrowser.open` is patched if reachable from the code path under test
  - All I/O functions (open, read, write, requests.get/post, etc.) are patched
  - All filesystem operations (os.path.exists, shutil, glob, etc.) are patched if called
- Flag every gap found - do not fix anything
- If a mock exists but is incomplete (e.g., missing side_effect for a call that can raise), flag it
- Report total: {N} tests checked, {M} gaps found

## Scope
Max 10 tests per invocation.
