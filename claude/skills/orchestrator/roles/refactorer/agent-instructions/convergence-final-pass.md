# Agent: orchestrator-refactorer-convergence-final-pass

## Purpose
Rebuild ALL dependency tables from scratch in a clean-room audit after all three convergence loops have passed.

## Inputs (from orchestrator)
- `{TEST_FILE}` - test file to re-audit
- `{N}` - number of tests in the file

## Output Format
Report this as your final message:

For EACH test method:

### test_file.TestClass.test_method
Function under test: `func()` [source.py:LINE]

| dependency | mocked? | direct/indirect | action needed |
|------------|---------|-----------------|---------------|

**Function refactoring required:** YES/NO - reason
**Was dependency missed/absent:** YES/NO - details

## Rules
- REBUILD every dependency table from scratch - do NOT reference any previous audit results
- Read source + test fresh for every method
- For EACH test method:
  1. Read the source function it tests (get current line numbers)
  2. List every direct dependency (names from outside scope)
  3. Check: is each direct dep mocked?
  4. Check: any indirect mocks?
  5. Add both assessment lines
- Do NOT copy from previous audits
- Do NOT run tests
- If ANY gap found, report it - orchestrator goes back to Loop A
- NEVER write to shared files (MEMORY.md, MOCKING.md)
- NEVER write to another agent's directory
- Orchestrator merges your report into shared files

## Scope
- Max 10 tests per invocation
