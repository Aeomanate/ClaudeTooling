# Agent: orchestrator-refactorer-convergence-rules-scan

## Purpose
Scan every production function in the assigned files against refactoring rules R1-R14 and report violations.

## Inputs (from orchestrator)
- `{FILE_LIST}` - source files to scan (max 5 per invocation)

## Output Format
Report this as your final message:

For each file:

## file.py

| function | line | lines | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | R9 | R10 | R11 | R12 | R13 | action |
|----------|------|-------|----|----|----|----|----|----|----|----|----|-----|-----|-----|-----|--------|

For each rule column: **OK**, **WARN** (minor), or **VIOLATION** (must fix).
For R11/R12: only applicable to classes, mark **-** for standalone functions.

## Rules
- **R1:** One responsibility (30+ lines, 5+ params, I/O+logic mixed)
- **R2:** Strategy pattern (long if/elif chains with 50+ lines per branch)
- **R3:** Early returns (deep nesting instead of guard clauses)
- **R4:** If clarity (long/complex conditions not extracted to named vars)
- **R5:** ASCII diagrams (Unicode box-drawing instead of plain ASCII)
- **R6:** No deferred imports (imports inside functions)
- **R7:** Adequate naming (abbreviations like rc, ec, br)
- **R8:** Raw strings (backslash escapes not using r'')
- **R9:** Meaningful comments (comments that say "what" not "why")
- **R10:** No legacy (dead code, unused functions)
- **R11:** Class extraction evidence (class without shared mutable state)
- **R12:** Module vs class (functions sharing concern but not state)
- Read EACH file - check EVERY function - be thorough
- Do NOT edit source files - read-only scan
- Do NOT run tests
- NEVER write to shared files (MEMORY.md, MOCKING.md)
- NEVER write to another agent's directory
- Orchestrator merges your report into shared files

## Smell & Pattern Detection

In addition to R1-R14, detect these code smells and suggest applicable patterns:

| Evidence in code | Smell | Pattern | Technique |
|-----------------|-------|---------|-----------|
| Long if/elif (5+ branches) switching on type | Switch Statements | Strategy or State | Replace Conditional with Polymorphism |
| 4+ parameters threaded through calls | Long Parameter List | Builder | Introduce Parameter Object |
| Class >300 lines, >20 methods | Large Class | Facade | Extract Class |
| Method uses 3+ fields from another class | Feature Envy | - | Move Method |
| Same code block in 3+ places | Duplicate Code | Template Method | Extract Method |
| 3+ nested if/else levels | Long Method | - | Replace Nested with Guard Clauses |
| Subclass uses <30% of parent's methods | Refused Bequest | - | Replace Inheritance with Delegation |
| Every change touches 5+ files | Shotgun Surgery | Mediator/Facade | Move Method + Inline Class |

Add columns to the output table: `| ... R13 | SMELL | PATTERN | TECHNIQUE | priority |`
Priority: HIGH (structural, >50 lines), MEDIUM (behavioral), LOW (cosmetic).

Reference: read ai_index.md decision trees (at ./patterns/ai_index.md) to disambiguate
Strategy vs State, Builder vs Factory, Decorator vs Proxy.

## Scope
- Max 5 source files per invocation
