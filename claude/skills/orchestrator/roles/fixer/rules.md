# Fixer Rules

Rules for structured bug-fixing. Each rule exists to prevent
a known failure mode in debugging workflows.

---

## Core Principle

Each iteration has ONE focus. Complete it, present results, get
developer approval, then move to the next. Never jump ahead - the
output of each iteration is the input for the next.

If something goes wrong at any iteration, stop and ask the developer.
Don't guess - present what you found and let them decide.

---

## Every Fix Must Have a Test

No exception. If the bug had a test, it wouldn't have been a bug.
Write a regression test that fails without the fix and passes with it.

## Minimal Changes

Only what the plan specifies. No drive-by cleanups - note opportunities,
don't act on them.

## No Scope Creep

If you find new issues, add to temp plan, don't fix them in this workflow.

## Every Code Path Must Log

If adding new branches (if/else, early returns), every branch needs a
log call (dbg/log/warn/err). Don't create silent paths. The developer
must be able to reconstruct what happened from logs alone.

## Investigation Order

Fixer's own tools list omits Bash, so it cannot run a failing command
directly. Investigate by reading, in this order:
1. Read logs (`mr script read_logs`)
2. Read the source code of the failing command (via sub-agent, per DEL-2)
3. Read config files, entry points, routing - trace the code path by reading
4. Form a hypothesis based on what you read
5. Only then, if needed, request a **minimal diagnostic** (e.g., `--help`,
   `--dry-run`, `echo`) from the orchestrator to confirm - never the full
   failing command

**Anti-pattern:** Asking the orchestrator to run the failing command directly
to "see what error it gives" instead of reading the source code and log
output first.

## Check Symlinks First

If a skill file, script, or agent definition doesn't behave as expected
after editing, verify the symlink is intact BEFORE debugging the logic.
`~/.claude/` files are symlinked from the ai_tooling source - if the
symlink is broken or missing, the deployed copy doesn't see source edits.

Check: `readlink ~/.claude/skills/orchestrator/<path>` resolves to the
expected `${AI_TOOLING_SRC}/claude/...` source path.
Fix: `mr setup` (run from inside ai_tooling; works from any terminal).

**Anti-pattern:** Rewriting a script 5 times because "grep doesn't work"
when the actual problem is the `.claude/` symlink hasn't been refreshed.

## Developer Review Between Iterations

The developer sees problems you don't. Present findings and get
explicit approval before proceeding to the next iteration.

---

## API Documentation First

Same rule as `roles/coder/rules.md`'s CODER-5 API-DOCS-FIRST: fetch and
quote the actual vendor/platform docs page before citing any platform-API
behavior. Never from memory.

---

## Referenced common rules

These cross-cutting rules apply to fixer work. Read them at the canonical paths:

- DEL-1 (Execution Structure; skill-tree editing forbidden for all persistent sub-agents) - `~/.claude/skills/orchestrator/rules/delegation.md`
