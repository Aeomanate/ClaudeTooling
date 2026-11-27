# Rules-Check Procedure

Shared 4-step procedure for the RULES CHECK phase at the end of coder,
gitter, refactorer, and drd-writer workflows. Each workflow's RULES CHECK
phase points here, naming only its own rules-file path(s); this file holds
the procedure once.

## Step 1: Dispatch the check

Spawn a general-purpose sub-agent (sonnet). Give it the path(s) to this
role's rules file (named at the call site), the role's language-specific
rules file if one applies, `~/.claude/skills/orchestrator/shared/rules/
style.md`, the changed-file paths (or how to get the diff:
`git diff --staged`), and an output path. It reads the rules itself.
Output schema: `~/.claude/skills/orchestrator/shared/rules-check-schema.md`.

Verdicts: PASS | VIOLATION-CRITICAL | VIOLATION-MINOR | SKIPPED.
A SKIPPED rule needs a written reason.

## Step 2: Fix every violation

Apply each fix. Do not argue a violation away.

## Step 3: Re-dispatch until CLEAN

Cap at 3 iterations. On a third non-clean verdict, report the remaining
violations and stop.

## Step 4: STYLE-8 comment-style check

Spawn a general-purpose sub-agent (sonnet), read-only, to read the diff and
report comment blocks disproportionate to the code they guard, and prose
that reads as session narration rather than a statement about the code.
Fix what it finds; it reports, it does not edit.

## Completion checklist

- [ ] Every rule appears in the table as checked or skipped
- [ ] Every skipped rule has a reason
- [ ] Verdict: CLEAN
- [ ] Second-pass comment-proportionality agent run, findings fixed
