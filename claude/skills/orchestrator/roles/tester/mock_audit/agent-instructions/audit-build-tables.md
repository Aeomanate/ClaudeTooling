# Agent: orchestrator-tester-mock-audit-audit-build-tables

## Purpose
Diagnose each test method's mocks against what it already has: find a
missing direct-dependency mock (a leak - real code runs during the test)
or a mock that targets an indirect dependency instead (masks what the
direct one does), and fix incorrect mock targets. This agent is spawned
once per batch and reused via SendMessage for every mock-audit loop-back
(AGT-1's reuse-before-spawning rule) - it is not respawned fresh each iteration.

## Inputs (from orchestrator)
- `{TEST_FILE}` - e.g. `test_module_x.py`
- `{N}` - test count
- `{TEST_FILE_PATH}` - full path to test file
- `{SOURCE_FILE_PATH}` - full path to source module(s)

## Output Format
Report this as your final message:

For EACH test method:

### test_file.TestClassName.test_method_name
Function under test: `function_name()` [source.py:LINE]

| dependency | mocked? | direct/indirect | action needed |
|------------|---------|-----------------|---------------|

**Function refactoring required:** YES/NO - (N lines, M deps, reason)
**Was dependency missed/absent:** YES/NO - details
**Improvements:** list any test quality issues:
  - Missing assertions (return code, mock call args, not-called)
  - Test passes for wrong reason
  - Missing edge cases
  - Naming/docstring inaccuracy
  - Dead code in test
**Tautological - remove:** YES/NO - test that validates language/framework behavior (e.g. dataclass defaults, stdlib return types) rather than project logic. These add noise and zero protection against regressions.

## Rules
- For EACH test method, on your FIRST pass through it:
  1. Read the test code and note its existing mocks (every `@patch`,
     context-managed patch, or module-level patcher already present) -
     this is your starting point, not a table you build from zero
  2. Read the source function it tests
  3. List every name used inside the function body that comes from outside scope (imports, module-level variables, other functions) - these are the DIRECT dependencies
  4. Check: is each direct dependency mocked in the test?
  5. Check: are any INDIRECT dependencies mocked?
- On a RE-ENTRY (SendMessage from a Phase 4 loop-back, same agent
  instance): do not redo steps 1-5 for a test you already diagnosed
  clean last pass. Re-check only tests you flagged "missed/absent" or
  "REMOVE - indirect mock" last time, to confirm the fix landed, plus
  any test whose source or test file changed since your last pass.
- Dependency classification:
  - Logging silenced via module-level patcher -> "YES (module)"
  - Pure functions (no I/O, no side effects) -> "OK -- pure"
  - Non-mocked direct dep with side effects -> "MUST MOCK"
  - Mocked indirect dep -> "REMOVE -- indirect mock"
  - Constants are not dependencies
  - `run()` subprocess calls are ALWAYS external deps
  - `os.path.isfile`, `open()`, `os.makedirs` are I/O deps
- Do NOT run tests - read-only audit + fix mock targets only
- If gaps found, FIX them in the test file using Edit
- NEVER write to shared files (MEMORY.md, MOCKING.md)
- NEVER write to another agent's directory
- Orchestrator merges your report into shared files

## Scope
- Max 10 tests per invocation
- One instance per batch, for the life of the mock-audit convergence
  loop - re-entered via SendMessage on each loop-back, never respawned
