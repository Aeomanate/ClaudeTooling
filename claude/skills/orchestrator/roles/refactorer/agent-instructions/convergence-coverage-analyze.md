# Agent: orchestrator-refactorer-convergence-coverage-analyze

## Purpose
Classify uncovered lines from coverage JSON into UNIT_TESTABLE, INTEGRATION, ERROR_PATH, or PLATFORM categories.

## Inputs (from orchestrator)
- `{FILE_LIST}` - source modules to analyze (max 5 per invocation)
- `{COVERAGE_JSON_PATH}` - path to coverage JSON produced by the project's coverage tool (Python: `coverage json`; C++: `gcovr --json`)

## Output Format
Report this as your final message:

| module | line range | flow description | testable? | action |
|--------|-----------|------------------|-----------|--------|

For EACH uncovered line range in coverage data:
1. Read the source code at those lines
2. Classify the flow:
   - **UNIT_TESTABLE** - pure logic or mockable I/O -> MUST COVER
   - **INTEGRATION** - real subprocess/network required -> SKIP
   - **ERROR_PATH** - defensive try/except, already tested -> OK
   - **PLATFORM** - Windows/Unix-only branch -> OK if other branch covered

## Rules
- Do NOT run tests or coverage - read-only analysis
- Do NOT write test code - just classify gaps
- Report what needs covering; orchestrator decides priority
- NEVER write to shared files (MEMORY.md, MOCKING.md)
- NEVER write to another agent's directory
- Orchestrator merges your report into shared files

## Scope
- Max 5 source modules per invocation
