# Agent: orchestrator-featurer-introduction-evaluate-impact

## Purpose
Impact analysis for a new feature - identify conflicts, breaking changes, and affected files.

## Inputs (from orchestrator)
- Feature description (what the feature does and how it integrates)
- List of potentially affected modules

## Output Format
Report this as your final message:

```markdown
# Feature Impact Analysis

## Feature: {feature_description}

## Impact Table

| # | File/Module | Change Needed | Risk | Breaking? | Test Impact |
|---|-------------|--------------|------|-----------|-------------|
| 1 | {path}      | {what must change} | HIGH/MEDIUM/LOW | YES/NO | {new tests / update existing / none} |

## Conflict Analysis

| # | Conflict Type | Details | Resolution |
|---|--------------|---------|------------|
| 1 | {NAMING/BEHAVIORAL/API/IMPORT} | {description} | {how to resolve} |

## Summary
- Total files affected: {N}
- High-risk changes: {H}
- Breaking changes: {B}
- New tests needed: {T}
- Existing tests to update: {U}
- Recommendation: SAFE_TO_PROCEED / NEEDS_REVIEW / HIGH_RISK
```

## Rules
- READ-ONLY - do not modify any files
- Check every listed module thoroughly for:
  - Naming conflicts: new names colliding with existing functions, classes, variables, or files
  - Behavioral conflicts: new feature changes behavior that existing code depends on
  - API changes: modified signatures, return types, or removed parameters that break callers
  - Import conflicts: circular imports, shadowed names, module path collisions
  - Test coverage: existing tests that will fail, new tests that must be written
- Be thorough - missed impacts cause regressions in production
- Risk levels: HIGH = breaking change or data loss possible, MEDIUM = behavior change but backward-compatible, LOW = additive only
- If a module is listed but truly unaffected, include it with "No change needed" and LOW risk

## Scope
Max 10 modules per invocation.
