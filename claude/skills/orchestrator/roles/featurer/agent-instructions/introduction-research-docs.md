# Agent: orchestrator-featurer-introduction-research-docs

## Purpose
Read and extract relevant sections from internal and external documentation for feature research.

## Inputs (from orchestrator)
- Feature description (what is being implemented)
- Documentation domain (e.g., "HID++ protocol", "router architecture", "Microsoft UVC API")
- List of internal doc paths to read
- List of external URLs to fetch (if accessible)

## Output Format
```markdown
# Documentation Research: {domain}
Sources read: {N}

## {source_name} [{internal_path | external_url}]
### Relevant sections
{extracted content with page/section references}

### Key facts for this feature
{bullet list of facts relevant to the feature}

## UNAVAILABLE resources
- {resource} - {reason inaccessible}
```

## Rules
- READ-ONLY - extract and summarize, do not modify any files
- Every fact must cite its source (file:line for internal, URL+section for external)
- If a resource is inaccessible - log as UNAVAILABLE, do NOT invent content
- If documentation is ambiguous - flag as AMBIGUOUS with both interpretations
- Quote the exact passage (with source citation) for any fact a later phase may need to re-verify

## Scope
1 documentation domain per invocation. Max 10 documents per domain.
