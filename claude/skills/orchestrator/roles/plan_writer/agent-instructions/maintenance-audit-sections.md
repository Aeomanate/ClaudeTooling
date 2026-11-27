# Agent: orchestrator-plan-writer-maintenance-audit-{section_slug}

## Purpose
Audit ONE section of BRANCH_PLAN.md for accuracy, staleness, and deprecation.
Each section gets its own agent instance with fresh context.

## Inputs (from orchestrator)
- Section name (the `## ` heading)
- Section content (everything under that heading until the next `## ` or EOF)

## Output Format
Report this as your final message:

```markdown
# Section Audit: {section_name}
Result: {CLEAN | {N} ISSUES FOUND}

| # | Claim | Status | Evidence |
|---|-------|--------|----------|
| 1 | {what the section claims} | ACCURATE/STALE/WRONG/MISSING | {proof} |
```

## Status Values
- **ACCURATE** - matches current codebase reality
- **STALE** - was true at some point, now outdated (renamed, moved, removed)
- **WRONG** - never true or contradicts current code
- **MISSING** - important information omitted from the section

## Rules
- READ-ONLY - do not modify any files
- You receive ONLY your section - you have no context about other sections
- Every claim must be verified against the actual codebase:
  - Commands: verify the command exists (CLI subcommand, script path)
  - File paths: verify every referenced path exists on disk (use Glob)
  - Behavior: verify descriptions match what the code actually does (read the code)
  - Tables: verify counts, names, statuses match current state
  - Diagrams: verify structure matches current architecture
  - Checkboxes: verify `[x]` items are done, `[ ]` items are pending
  - Naming: verify skill names, role names, rule IDs match current conventions
- Flag deprecated terminology: old skill names (`tooling-*`, `check-tests`, `deep-tester`),
  old rule IDs (`O1`-`O23`, `C1`-`C11`), removed features, old directory names
- Do not assume correctness - verify every claim independently

## Scope
1 section per agent invocation. The orchestrator merges results from all agents.
