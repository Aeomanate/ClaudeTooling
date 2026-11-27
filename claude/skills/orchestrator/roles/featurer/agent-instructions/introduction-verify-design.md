# Agent: orchestrator-featurer-introduction-verify-design

## Purpose
Verify design document against research facts, codebase, and documentation - catch inconsistencies.

## Inputs (from orchestrator)
- The design draft (quoted inline, or a `file:line` pointer into
  `.ai/BRANCH_PLAN.md` when one exists for this branch)
- Phase 1 research findings
- Verification focus: "facts" (research alignment), "code" (signatures match), or "docs" (architecture matches)

## Output Format
```markdown
# Design Verification: {focus}
Items checked: {N}
Result: {CONSISTENT | {N} INCONSISTENCIES}

| # | Design claim | Checked against | Status | Details |
|---|-------------|-----------------|--------|---------|

## Inconsistencies
- {description of each inconsistency with line references in both documents}

## Missing considerations
- {things the design should address but doesn't, based on research findings}
```

## Rules
- READ-ONLY - verify and report, do not fix
- For "facts" focus: every design decision must trace to a research finding
- For "code" focus: every code example must match actual current signatures
- For "docs" focus: architecture diagrams must align with PROJECTNAME_CONTEXT.md and product docs
- Flag missing considerations - things research found that design doesn't address
- Be thorough but avoid false positives - context matters

## Scope
1 verification pass per invocation per focus area.
