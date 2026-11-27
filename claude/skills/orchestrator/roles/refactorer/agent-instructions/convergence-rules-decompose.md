# Agent: orchestrator-refactorer-convergence-rules-decompose

## Purpose
Extract pure logic from large functions into separate helpers, preserve all existing behavior, and fix test consistency after decomposition.

## Inputs (from orchestrator)
- `{SOURCE_FILE}` - source file containing functions to decompose
- `{FUNCTION_LIST_WITH_LINE_COUNTS_AND_SUGGESTIONS}` - functions flagged for decomposition with line counts and suggested extraction points

## Output Format
Report this as your final message:

For each decomposed function:
- Original function name, line count before/after
- Extracted helper(s): name, purpose, parameter count
- Test consistency changes made (mocks updated, tests rewritten)
- Controversial items flagged with reason (6+ params, class extraction needed, architectural change)

## Rules
- Read each flagged function using its given line range (`offset`/`limit`
  or `Grep -A/-B`), per AGT-3 FRESH-CONTEXT's ranged-read discipline. Widen
  to the full file only if a function's actual boundaries don't match its
  reported line count.
- Extract functions ABOVE the orchestrator function that uses them
- Each extracted function should need 0-2 mocks to test
- Preserve ALL existing behavior - zero functional changes
- Do NOT run tests - orchestrator will run after mock audit
- One extracted function per logical group
- After decomposition: CHECK test consistency
  - Read the test file for the decomposed source
  - If any test now mocks an INDIRECT dep (something absorbed into an extracted helper), FIX the test to mock at the correct (direct) level
  - If a test needs rewriting due to changed function boundaries, REWRITE it
- Focus on extracting:
  - Pure validation logic (returns error string or None)
  - Pure data building (returns constructed objects/lists)
  - I/O wrappers that bundle related subprocess calls
- Orchestrators become: validate -> call helpers -> handle errors
- If a decomposition is controversial (6+ params, class extraction needed, architectural change), flag it clearly in output
- NEVER write to shared files (MEMORY.md, MOCKING.md)
- NEVER write to another agent's directory
- Orchestrator merges your report into shared files

## Pattern-Driven Decomposition

When the scan output includes a PATTERN suggestion:
1. Read `../patterns/ai_index.md` for the pattern's trigger and one-line shape
2. Follow the pattern's structure when decomposing:
   - Strategy: extract each branch into a handler class/function, create dispatch map
   - Builder: extract parameters into a builder with fluent setters
   - Factory Method: extract creation into factory function returning base pointer
   - Template Method: extract varying steps into virtual hooks in base class
   - Facade: extract public API into thin wrapper class

Always confirm pattern choice with developer before applying (via orchestrator).

## Scope
- Max 1 source file per invocation
