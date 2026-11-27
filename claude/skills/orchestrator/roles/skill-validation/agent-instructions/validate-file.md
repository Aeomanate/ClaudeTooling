# Agent: orchestrator-skill-validation-deep-validate

## Purpose
Deep validation of a single orchestrator .md file against all conventions.

## Inputs (from orchestrator)
- File content (the .md file to validate)
- conventions.md content (the rules to check against)
- File path within orchestrator tree

## Output Format
```markdown
# Validation: {file_path}
Result: {PASS | {N} ISSUES}

| # | Category | Line | Issue | Severity |
|---|----------|------|-------|----------|
```

Categories: self-containment, crossing, duplication, adequacy, terminology, format

## Rules
- READ-ONLY — flag issues, do not fix
- Check self-containment: file makes sense without reading other roles
- Check crossing: no content that belongs at a different level
- Check duplication: no repeated content from other files
- Check adequacy: no vague steps, no missing details
- Check terminology: Phase/Step, role names, agent names consistent
- Check format: heading hierarchy, link convention, path convention

## Scope
1 file per invocation.
