# Gitter Rules

Rules governing all git operations across the project.
Applies to every commit regardless of which role is active.

## Dirty commits

A `(dirty)` subject marks POC-mode work (WF-21, WF-24 MODE-STATE).
- Who runs the commit changes; commit shape does not. G1, G2, G4, G8, G9, G12, G15 and G16 bind whoever runs it.
- Stand down for a `(dirty)` subject: G6, G7 (Step 3.1, Step 3.2, Phase 4), G13, G14.
- All four apply in full to the `(hardening of <range>)` commit closing the range.

---

## G1: COMMIT-CADENCE

**Statement:** One user-facing logical unit per commit - never bundle two, never split one.
- Unit means the named refactor, feature, bug fix or ticket, not the micro-step. An extraction plus its tests, call sites and old-code removal is one commit.
- In doubt: combine. Splitting needs a stated reason - bisectability for a named bug, separate reviewer focus, a clean revert point for a risky change. No obvious reason, ask the developer.
- Bad: an unrelated bug fix committed with a feature change.
- Bad: "extract NetworkClient helper" landing as 20 commits, one per method and call site.

---

## G2: COMMIT-MSG-FORMAT

**Statement:** Subject starts with a whitelisted imperative verb, stays within the hook's length limit, and carries no trailing dot.
- Source of truth is `.git-hooks/commit-msg.py`, extracted at task time - never the static values here.
- Absent hook: 60 characters, verbs Add, Fix, Update, Remove, Refactor, Improve, Document, Change, Move, Rename, Extract, Enable, Disable, Revert.
- Bypass: `[skip_ci]` prefix; `fixup!` and `squash!` skip the checks.
- Bad: hardcoding the verb list in rule text - it drifts from the hook.

### G2-LEN

```bash
# Extract length limit (fallback 60 if hook absent):
MAX_LEN=$(sed -n 's/.*len(message) > \([0-9]*\).*/\1/p' .git-hooks/commit-msg.py | head -1)
MAX_LEN=${MAX_LEN:-60}
```

### G2-VERB

```bash
# Extract whitelisted verb pattern (fallback empty = use the shortlist above):
VERB_REGEX=$(sed -n 's/.*re\.match[^"]*"\^\(.*\)\b.*/\1/p' .git-hooks/commit-msg.py | head -1)
```

### G2 auto-fix policy

Gitter may modify the subject. Fix mechanical violations itself, commit, and note the change in its report; never bounce a mechanical fix back to the orchestrator.
- Trailing period: strip it.
- Over length: drop the lowest-information words first (filler, redundant clauses, parenthetical asides), keeping the verb, the ticket ID and the core noun phrase. Then try acronymising an obvious phrase ("MockEtwConsumer + MockEtwSession" -> "ETW mocks").
- Verb not whitelisted: swap in the closest semantic match (`Implement/Build/Construct` -> `Add`/`Make`; `Tweak/Adjust/Tune` -> `Modify`/`Update`; `Wire/Hook up` -> `Add`/`Integrate`; `Repair/Patch` -> `Fix`; `Bring back` -> `Restore`; `Deactivate` -> `Disable`; `Activate` -> `Enable`). Unsure: prefer Add, Do, Edit, Fix, Make, Remove, Update, Use.
- Escalate instead when the fix changes meaning, when two equally good fixes differ in emphasis, when length still overruns, or when no whitelisted verb fits.
- The commit-msg hook stays authoritative; this pre-validation only handles the mechanical cases.

**Report shape, auto-fixed (commit succeeds):**
```
<task#> <new subject> - COMMITTED <SHA>
- Subject auto-fixed:
  Original: <original subject> (<original length> chars, violations: <list>)
  Fixed:    <new subject> (<new length> chars)
  Rationale: <one-line explanation of what you dropped/swapped and why>
- Files staged: <list>
- Hooks status: pre-commit PASSED; commit-msg PASSED
- git status after: <one-line summary>
```

**Report shape, escalated (commit NOT attempted):**
```
<task#> Subject needs the orchestrator judgment - `git commit` not attempted.
Subject as received: <original> (<length> chars, violations: <list>)
Auto-fix attempted: <what you tried>; couldn't safely produce a compliant
subject because <reason>.
Suggested fixes for the orchestrator to pick:
  1. <option 1>
  2. <option 2>
  3. <option 3>
Staging untouched (still <N> files staged); ready to retry on revised subject.
```

---

## G3: BRANCH-NAMING

**Statement:** Branch names match project conventions; an unrecognised one is prompted back to the developer before any work proceeds.
- Example: `<project>/fixes/<TICKET-ID>_<short_summary>`.
- Bad: creating `my-fix` without checking conventions.

---

## G4: STAGING-DISCIPLINE

**Statement:** `git add` and `git commit` always chain in one command; the plan file is never staged; a refactor's pieces never split across commits.
- Example: `git add -u -- file1.py file2.py && git commit -m "Add helper"`.
- Bad: staging, then editing more before committing.
- Bad: committing deletions separately from their replacements.

---

## G5: SKIP-PERMISSION

**Statement:** Superseded by G10 SKIP-TOKEN-DISCIPLINE's structured token - see G10 for the format, the per-phase requirement, and the G7 carve-out.
- No pre-commit phase is marked "N/A" or skipped without that token.

---

## G6: PRE-COMMIT-CONSISTENCY

**Dirty-mode exemption:** deferred for a `(dirty)` commit until the range closes.

**Statement:** Before committing, a fresh verification agent - given only the changed files and their content, no prior session context - checks that they are mutually consistent.
- It checks: cross-references resolve, no stale identifiers survive a rename, terminology matches across files, and no two files contradict each other.
- Bad: letting the context that wrote the changes verify them - it skips over stale references it "knows" were updated.

### G6-UPSTREAM-REF-CHECK

A cross-reference may point at a target that exists on the remote default branch but is not merged into this working tree, which reads as fabricated to a working-tree-scoped agent.
- Bad: calling a `supersedes:` reference fabricated because the working tree lacks it.

---

## G7: NON-SKIPPABLE-STEPS

**Dirty-mode carve-out:** a `(dirty)` subject defers Step 3.1, Step 3.2 and Phase 4; Phase 5 always runs. `git log -1` after the commit replaces the approval round-trip.

**Statement:** Four pre-commit steps always run, whatever the change size or file types: Step 3.1 plan update (fresh plan-writer), Step 3.2 consistency check (fresh analyzer), Phase 4 approval, Phase 5 commit.
- "It's just two files" and "the change is trivial" are not reasons. A single-file `.md` change runs both agents.
- Non-skippable means the phase always runs, not that its scope is fixed - see G7A.
- Bad: skipping the consistency check on a small `.md` change because the only cross-reference looks obvious.

---

## G7A: MECHANICAL-DIFF-TIER

**Statement:** A mechanical diff - under 3 files, under 30 changed lines, no new function, class or control flow - narrows dispatch scope only; every G7 phase still runs.
- `mr script classify_diff` tags a diff `mechanical` or `standard`.
- What changes: Step 2.2 and Step 3.2 run as one combined verifier dispatch, and `roles/refactorer/workflow.md` Phase 4 narrows its clean-room re-audit to the touched files.
- Bad: dropping Step 3.2 because the diff is small - the tier collapses it into Step 2.2, never removes it.

---

## G8: COMMIT-BODY-WHY

**Statement:** The body explains only what the diff cannot show - why the change exists, and why it took this shape over an obvious alternative.
- Never enumerate what the diff displays: file names, symbol names, rule IDs, per-file edit lists, counts.
- Budget: three sentences per concern, five concerns. More than five means this is more than one commit (G1).
- Length tracks the explanation, never the diff. A 500-line mechanical rename needs one sentence; a one-character config fix found after a long hunt may need five.
- Never restate the subject line in the first sentence.
- Bad: "Updated foo.py and bar.py".
- Bad: twenty lines enumerating sixteen rule IDs across five files.

---

## G9: PRE-FLIGHT-STAGED-CHECK

**Statement:** Run `git diff --cached --stat` before any `git add`; anything staged outside the orchestrator's named commit scope is reported, and work stops until the developer answers.
- Example: a prior run aborted at Phase 4 leaving 3 files staged, which the next single-file commit would sweep in.
- Bad: `git add -u -- <named-file> && git commit` without inspecting the index first.

---

## G10: SKIP-TOKEN-DISCIPLINE

**Statement:** Gitter rejects any dispatch that omits or name-skips a standard pipeline phase without a `user-accepted: skip Phase N.M (<name>); reason: <text>` token for that phase individually.
- Token shape: each skipped phase named by number and title, one clause each. Coarse tokens name nothing specific and are rejected.
- Good: `user-accepted: skip Phase 2 (refactor R1-R14 scan); skip Phase 3.3 (tests-vs-plan delta-check); reason: docs-only change`.
- Bad: `user-accepted: skip 5-phase pipeline`.
- Dirty-mode standing authorization: a `(dirty)` subject needs no token for Step 3.1, Step 3.2 or Phase 4, and the G7 carve-out below does not fire on them. Every other skipped phase still needs its own clause.
- G7 carve-out: a token naming Step 3.1, Step 3.2, Phase 4 or Phase 5 on a non-dirty commit is invalid even when correctly shaped. Reject with: `Dispatch rejected: Phase N.M is G7-mandatory (non-skippable). Re-send without the skip token. Gitter does not dispatch other roles itself, if refactorer or plan-writer input is needed for this phase, ask the orchestrator to route it. Never bypass the phase.`
- Step 3.3's auto-skip (no test files in the diff) is a "no work to do" pass, not a dispatcher override.

---

## G12: NO-SESSION-LOCAL-TERMS

**Statement:** Neither subject nor body carries a term that only means something inside this session's plan file, cache or in-flight workflow (STYLE-2 BE-ACTUAL).
- Forbidden: plan-local phase labels (`Phase X`, `Wave Y`, `Step N.M`, `K-3a`), iteration labels (`iter-N`, `round N`, `pass N`), session-relative time (`this session`, `previously`, `in the prior dispatch`), in-flight tags (`convergence loop`, `dispatch N`, `Task #N`), and cache-local artifact names.
- Allowed: ticket IDs, file, function and class names, technology names - all outlive the session.
- Canonical rule IDs (`AGT-3`, `R1-R14`) are permanent but still forbidden: a reviewer outside the AI-tooling loop has no context for them.
- Gitter audits both surfaces at Phase 1, alongside the G2 count, and re-checks the body at Phase 4 in case the orchestrator re-authored only the subject.
- No auto-fix: G12 is semantic. Return a proposed-vs-stripped contrast table and let the orchestrator re-author.
- When both subject and body carry session-local terms, call out the pattern, not just the instances.
- Bad: "Phase K-3b dispatch + main.py unification" length-corrected to "Add async dispatcher + cli/main unification (K-3b)" - G2 caught the mechanical issue and left "K-3b" engraved in `git log`.

---

## G13: BIDIRECTIONAL-INDEPENDENCE

**Dirty-mode exemption:** a `(dirty)` commit is part of a range a later commit completes, so the Phase 1 framing check does not reject it. Applies in full to the `(hardening of <range>)` commit.

**Statement:** Every commit is authored as if it is the latest for its scope - self-contained, with nothing later required to make it work.
- Forward: checking out commit N without N+1..M yields a buildable, functionally coherent state.
- Reverse: `git revert N` leaves the rest buildable and coherent, so a reviewer can drop any single commit without cascading breakage.
- Newer commits may alter older ones; older commits must never reference newer. That asymmetry is the whole rule.
- Gitter rejects a dispatch framed as "part 1 of N" or "step M of a sequence": collapse it, re-scope it as self-contained, or document a justification.
- Allowed: N adds `foo()`, N+1 adds a caller and extends its signature. Forbidden: N adds a caller of `helper()`, N+1 adds `helper()`.
- Dimensions to audit at Phase 1 and Phase 4: build, runtime, test coverage, cross-reference - in both directions.
- Standalone-build check: for an uncommitted stack, a full-cumulative-diff proxy build before Phase 4, with the per-commit check interleaved into Phase 5 (`roles/gitter/workflow.md` Step 3.4). For an existing stack, check out each commit alone and build.
- Phase 1 audit, any failure rejects: (1) does the dispatch use sequence framing; (2) does the named scope reference symbols, files or tests landing in a later commit; (3) would the feature work end-to-end if this commit shipped alone.
- Phase 4 audit: mentally simulate `git revert` on each commit in the stack and confirm the remainder stays coherent.
- Units that depend on each other in either direction collapse into one commit (G1's combine-by-default).
- Bad: "production async refactor" in commit 2 and its test cascade in commit 4 - broken forward and backward.
- Why it matters beyond bisect: independent revertability is what lets ops roll back one deployed commit without a revert cascade.

---

## G14: TESTS-SHIP-WITH-CODE

**Dirty-mode exemption:** a `(dirty)` commit may touch no test file (WF-21), so it ships production only. The range's test cascade lands with the `(hardening of <range>)` commit.

**Statement:** A commit that adds, removes or modifies production code carries the matching test changes in the same commit.
- A structural consequence of G13's functional-completion gate, broken out because the production/test split is its most common violation.
- Covers: a new function and its unit tests, a signature change and every affected test, a removal and its tests, a refactor's production and test files, an async conversion and its mock setups, a renamed logger and the tests asserting on it.
- Acceptable one-sided commits: purely additive coverage for previously untested code, and a purely test-side refactor.
- Not acceptable: "tests in a follow-up", "test cascade at the end of the stack", or "tests already cover it" when the test no longer asserts the same intent.
- Phase 1 audit: a one-sided diff must be additive coverage or a test-side refactor, otherwise reject. A dispatch saying "tests in next commit" is rejected outright.
- Phase 4 audit: confirm test counterparts are in the file list; a modified production function with no test referencing it gets the question asked.
- Why it matters: a SHA where `mr verify` fails poisons every future bisect, and an emergency revert that drops the test commit leaves verify permanently broken.
- Relationship to G1: a logical unit that includes production code includes its test coverage. The unit is "production + test together."

---

## G15: BRANCH-TICKET-EXCLUSIVITY

**Statement:** The branch's ticket ID is the only ticket ID allowed in a commit's subject or body. A mismatch is a hard reject, not a warning.
- Extract: `BRANCH_TICKET=$(git rev-parse --abbrev-ref HEAD | grep -oE '[A-Z]+-[0-9]+' | head -1)`. Empty means the rule does not apply.
- Commit ticket set: every `[A-Z]+-[0-9]+` match across the proposed subject and body.
- Reject when the set holds any ticket other than `BRANCH_TICKET`, or is empty while the branch encodes one and the branch's existing commits carry a suffix.
- Override: `user-accepted: ticket-mismatch <TICKET>; reason: <text>`, one clause per offending ticket. Coarse tokens are rejected.
- Run it at Phase 1 before the G2 length check (cheapest first) and again at Phase 4 on the final text, since an orchestrator edit can reintroduce a ticket.
- Cost: one `git rev-parse`, two `grep -oE`, one set comparison. No dispatch.
- Relationship to G12: G12 allows ticket IDs because they outlive sessions; G15 narrows that to the branch's own.
- Bad: a branch named for TICKET-A carrying five commits suffixed TICKET-B - `git log --grep=TICKET-A` returns nothing.

**Mismatch report format:**
```
G15 branch-ticket exclusivity FAILED:
- Branch: {BRANCH}
- Branch ticket:  {BRANCH_TICKET}
- Commit tickets: {SORTED_LIST}
- Offending: {SET_DIFF: commit_tickets - {BRANCH_TICKET}}
Action: orchestrator must replace offending tickets with {BRANCH_TICKET},
OR provide override token `user-accepted: ticket-mismatch {OFFENDING};
reason: <text>` in the next dispatch.
```

---

## G16: MR-BODY-PURPOSE

**Statement:** An MR description may carry a purpose paragraph; G8's "nothing the diff already shows" binds per-commit bodies only.
- A reviewer opens the MR before the commit list and needs framing for why the branch exists.
- Bad: compressing an MR description to bare per-commit G8 language.

---

## Git Command Restrictions

Beyond CLAUDE.md's Critical section and G4's staging rules:
- Never stage or commit `.gitignore` - developer-managed.
- Never stage or commit `.git-hooks/` - symlinked from `${AI_TOOLING_SRC}`, managed by `mr setup`.
- Never stage or commit `.ai/` - per-project runtime cache, untracked by design.
- All git commands work from the Claude Code terminal without environment-flag restrictions.

---

## Referenced common rules

- DEL-1 (Execution Structure; skill-tree editing forbidden for all persistent sub-agents) - `~/.claude/skills/orchestrator/rules/delegation.md`
