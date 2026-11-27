# Rules-Check Output Schema

Shared output schema for the RULES CHECK phase at the end of every role
workflow. Every role's final RULES CHECK phase points here instead of
repeating the table shape inline.

## Output format

Report this in your final message:

```markdown
# Rules Check

## Checked Rules

| # | Rule | Verdict | Evidence (file:line) |
|---|------|---------|-----------------------|
| 1 | {rule_id}: {rule_name} | PASS/VIOLATION-CRITICAL/VIOLATION-MINOR/FIXED | {file:line and explanation} |

## Skipped Rules

| # | Rule | Reason Skipped |
|---|------|----------------|
| 1 | {rule_id}: {rule_name} | {why not applicable to this scope} |

## Summary
- Rules checked: {N}
- Passed: {P}
- Violations (critical): {VC}
- Violations (minor): {VM}
- Fixed (were violations, now resolved): {F}
- Skipped: {S}

## Verdict: CLEAN / {V}_VIOLATIONS
```

## Rules

- READ-ONLY - do not modify any files.
- Check every rule in the given rules file against the changed-file scope -
  never skip a rule without documenting why.
- Verdict values:
  - PASS: the scope complies with this rule.
  - VIOLATION-CRITICAL: security, correctness, or data-loss risk - must fix
    before the workflow can report CLEAN.
  - VIOLATION-MINOR: style, naming, formatting - fix if practical, note if
    deferred.
  - FIXED: a previous violation of this rule was corrected in this diff.
- A rule is skipped only if the scope does not touch anything relevant to it.
- For each VIOLATION, give actionable fix instructions: what to change,
  where.
- Check both added and removed lines - removing a safety check is also a
  violation.
- If the scope includes test files, apply test-specific rules as well.

## Optional logging audit

Run this addendum when the changed-file scope contains executable code (any
language). Report findings under a `Logging audit:` heading inside the
`## Checked Rules` table, using the same verdict vocabulary.

### LOG-ERROR

Error-handling branches (catch blocks, early-return on failure, error
propagation) MUST have an ERROR-level log including cause + status/code.
- **Check:** For each catch/error-return in scope, verify an ERROR log call
  exists with cause and status.
- **Verdict:** PASS | VIOLATION-CRITICAL | FIXED | SKIPPED (no error-handling
  paths in scope)

### LOG-INFO

Lifecycle transition functions (Start/Stop, Connect/Disconnect,
Register/Unregister, Initialize/Shutdown) MUST have an INFO log marking what
transitioned and to what state.
- **Check:** For each lifecycle entry/exit function in scope, verify an INFO
  log is present.
- **Verdict:** PASS | VIOLATION-MINOR | FIXED | SKIPPED (no lifecycle
  functions in scope)

### LOG-HOT-PATH

Callbacks, handlers, dispatchers, and event-loop bodies MUST contain NO log
calls at any level.
- **Check:** For each hot-path function in scope, verify zero log calls
  inside its body.
- **Verdict:** PASS | VIOLATION-MINOR | FIXED | SKIPPED (no hot-path code in
  scope)

### LOG-SYMMETRY

If an add/register/enable function has a success log, its sibling teardown
MUST also have one. Teardown may be outside the diff - read it (one Read
call) before verdict; do NOT SKIP because it is absent from the diff.
- **Check:** For each add/register/enable with a success log in scope,
  locate the sibling teardown and verify its success log.
- **Verdict:** PASS | VIOLATION-MINOR | FIXED | SKIPPED (no add/register/
  enable functions in scope)

## Scope

1 invocation per RULES CHECK dispatch (one role's changed-file set for this
workflow run).
