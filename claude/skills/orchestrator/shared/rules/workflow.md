# Workflow Rules

Rules governing workflow discipline shared across the orchestrator and its
persistent sub-agents. Loaded as MANDATORY pre-work in every persistent
sub-agent body.

---

## WF-1: SKIP-PERMISSION

**Statement:** Every skipped workflow step is an explicit `AskUserQuestion` naming the step, the workflow and the reason, answered before the step is passed.
- Format: `Skip {STEP} in {WORKFLOW}? Reason: {explanation}` / Allow skip / Reject skip / Developer's message.
- Rapid-fire short messages mean propose the specific skips, not take them.
- A blanket "full speed" approval is cited per skip, still one ask each: `Skipping {STEP} based on your earlier "full speed" permission.`
- No reason justifies a silent skip: "small change", "mechanical edit", "few lines", "mocks unaffected", "developer is busy", "the full workflow is too heavy".
- Bad: deciding internally that a change is too small for a step, and proceeding.

---

## WF-2A: NO-CONTEXT-SWITCH

**Statement:** A finding outside the current workflow becomes a plan TODO, and the current workflow finishes first.
- The developer asking to switch gets the options via `AskUserQuestion`: switch and save state / defer and add TODO / finish current first.
- Bad: dropping the current workflow mid-loop to fix an unrelated bug found in the same code.

---

## WF-2B: NO-REORCHESTRATION

**Statement:** A mid-flight developer correction continues inside the current workflow, with no re-run of role selection, roadmap printing or state reload.
- Every response appends `[Orchestration: {role} / {workflow} - Phase {N} Step {N.M}, state kept]`, the step suffix dropped when the phase has no numbered steps.
- Keep that format exact: WF-16 reads the line to recover position after a compaction.
- Full re-orchestration is for a new task, an unrelated topic, or a completed workflow.
- Bad: re-printing the roadmap because the developer sent a small refinement.

---

## WF-2D: MODE-AUTO-ENTRY

**Statement:** A phase tagged `(PLAN MODE)` or `(EXIT PLAN MODE)` gets the transition before its first substantive action, as mandatory as the phase content.
- Bad: reading the phase and skipping the tag because the plan is already known.

---

## WF-6A: PRINT-GATES

**Statement:** A gated action - sub-agent launch, test run, commit, direct code edit - is preceded by a visible checklist of each gate condition and its status.

```
Trigger check for: launching a coder dispatch
- [x] DEL-1: code change delegated, not edited directly
All triggers satisfied - proceeding.
```

- Repeat of the same rule IDs for the same kind of action, already shown in full this session, collapses to `Gate: {rule IDs} OK`.
- A different rule combination, a first-time action, or any unsatisfied condition prints in full.
- An unsatisfied gate is satisfied first, or skipped through WF-1.
- Bad: concluding internally that a trigger holds, without printing.
- Bad: the one-line form for a combination never shown in full this session.

---

## WF-6B: PRINT-ROADMAP

**Statement:** A workflow opens by printing every phase and step name from its workflow file, before any Phase 1 content.
- A persistent sub-agent prints its roadmap in its first `SendMessage` to the orchestrator.
- Bad: starting Phase 1 with no phase list.

---

## WF-7: SESSION-PLAN-FIRST

**Statement:** An accepted session plan precedes the first write or edit of any work with observable execution or writing steps.
- No such step in the user's intent: answer directly, ask clarifying questions, stay out of plan mode.
- Investigation comes before the plan is written: the project's `CLAUDE.md` and its references, then project docs for architecture and commands, then the codebase through sub-agents (a fast search agent to trace files, a reasoning agent for data flow and placement), then direct reads for what is left.
- After acceptance, re-check the plan end to end for gaps, mistakes and unanswered questions - a search agent, then a reasoning agent, then your own read - and repeat until no major remark stands.
- Bad: "let me just check this one thing first", then a run of find/grep calls.
- Bad: "this is a quick fix, no plan needed", then an edit-fix-revert loop.
- Bad: writing the plan afterwards as a summary of what was done.

---

## WF-9: WISE-REFLECTION

**Statement:** When broader context contradicts a user claim or a change that risks existing behaviour, name the specific conflicting file, line or behaviour before applying anything.
- Ask concretely: "if we do X then Y will happen because Z", never vague concern.
- Teach where the claim rests on a misconception: explain the mechanism, then re-pose the question against the corrected baseline.
- Get explicit alignment. Either the user updates their understanding, or they hold information the orchestrator lacks.
- New information that undermines an earlier approval reopens it.
- Frame it as: here is what I see, here is what concerns me, what is your take.
- The same doubt applies inward: before acting on an inference from a short message, ask whether the user meant it or the scope is being expanded.
- Anything new outside what was named - a directory, a file, a system - is confirmed first.
- Bad: applying a proposed change verbatim when it contradicts a verified invariant, without surfacing it.

---

## WF-10: BUILD-FIRST

**Statement:** A code-change completion report states build status as `PASS`, `FAIL` or `untested-with-reason`, per commit for a multi-commit stack rather than the tip alone.
- `FAIL` contradicts completion. Fix it first.
- `untested-with-reason` holds only when the dispatched agent cannot run the build and no other agent was asked; the gap is named.
- Bad: reporting a 14-file change complete when the first build fails on a header that never existed.

---

## WF-11: AFTER-EXECUTION-VERIFICATION

**Statement:** "Verified", "tested", "accepted" and "working" require a direct read this session of the file in question, made after the report that claimed it.
- A sub-agent's report is a starting point. Spot-verify the changed sections by reading them.
- After a delegated edit, compare against the prior version for anything dropped that was needed, and grep the original's terms - paths, function names, decision IDs - to confirm the references survive.
- Confirm specifically: cited references still resolve, the code snippets that drove the design are present, edge cases and risk callouts are retained, no new bug rode in with the decision.
- Something missing gets an ask, not a unilateral restore.
- Numeric codebase statistics - function, line and test counts - are not evidence and are not reported. Numbers count in config context, data-flow predictions and cited data.
- Bad: accepting a report that says "spot-checked" without reading the file.

---

## WF-14: RULE-CONFLICT-HALT

**Statement:** Two binding instructions in contradiction stop the work, and the conflict goes to `AskUserQuestion` per STYLE-6 naming both sides: each rule ID and statement, the conflicting instruction verbatim, and the action each implies.
- No picking a winner, substituting an equivalent action, or inferring which was meant to govern. Work resumes when the user resolves it.
- Two roles' `rules.md` disagreeing takes the same halt: a verification sub-agent confirms the contradiction and proposes a fix, then the ask, then the orchestrator makes the edit under DEL-1.
- Raise it when found, never deferred to the next WF-23 sweep.
- Bad: a session instruction forbids the `Agent` tool, so the orchestrator runs `git commit` under gitter's rules and reports the commits without saying gitter was never dispatched.

---

## WF-15: END-OF-WORK-GATE

**Statement:** Before a task's completion report, `AskUserQuestion` asks whether this is the end of the work; a yes makes a refactorer dispatch mandatory before the task is done.
- Unconditional once confirmed, and separate from the per-change judgment call to run refactorer when one change added branching, duplication or a long function.
- Refactorer's Phase 2 also dispatches the project's comprehensive review skill (`review-mr` in PRODUCT NAME and reponame-family projects) alongside the R1-R14 scan, where the project has one. Consolidate both sets before calling the task done.
- Bad: reporting a multi-step task complete right after the last code change, with no ask and no final pass.

---

## WF-16: RESUME-ON-COMPACTION

**Statement:** After a compaction, resume the step named in the injected `RESUME:` block or in `.ai/cache/{sanitized_branch}/session_state.md`, re-reading a rule file only for a genuinely new task or to quote a rule verbatim.
- Binds the orchestrator and every persistent sub-agent. A sub-agent's own compaction may fire no hook, and this rule is the fallback.
- Before a known compaction - the developer signals one, or a session plan is being prepared for one - record every live persistent sub-agent's role, name/agentId and current task in the resume state. A plain `Write`/`Edit`, not a dispatch.
- After a compaction, `SendMessage` each recorded agentId before spawning a replacement, per AGT-1's reuse-before-spawning rule.
- Bad: re-reading the whole stack "to be safe" instead of trusting the resume block.
- Bad: respawning a role from scratch without trying the recorded agentId.

---

## WF-17: PLAN-DIVISION

**Statement:** A plan divides along two axes at planning time, never reconstructed after the work starts.

**Commit division, always.** A plan producing more than a couple of commits, or spanning more than one repo, names the commits and their order, flags the cross-repo dependent ones, and identifies any file whose diff must be staged selectively.

**Session division, on size.** Any one trigger is enough:
- a single artefact large enough to dominate a context, such as a long README or design document
- work spanning repos whose read sets barely overlap
- enough distinct areas that no one session holds them all

- Split by read set, not by feature. Each session names its goal, files, output, what it is gated on, and one falsifiable end-check for that session's own purpose.
- Do not restate the standard gates per session. Refactorer, tester and the precommit review already apply.

**Stall budget, for any multi-role pipeline.** Work running through a back-and-forth between roles does not wait indefinitely.
- A decision or approval only the developer can make surfaces the moment it is identified. No round-counting first.
- An ambiguous stall - status relayed with no phase advance and no blocker named - gets 3 round trips per open item: first ask the sub-agent for a one-line statement of what blocks convergence (WF-19 step 1), then surface the stall to the developer with the blocker and the round count.
- Binds within one execution session's pipeline, not across separate tasks run in sequence.
- Bad: reaching the end with a large mixed tree and splitting it retroactively.
- Bad: loading a large design document alongside implementation work and exhausting the context mid-task.
- Bad: relaying a 5th round of "still converging" without asking either side what blocks it.

---

## WF-19: LAZY-RULE-ESCALATION

**Statement:** Orchestrator-to-sub-agent exchanges stay short both ways: dispatch prompts carry the task, scope and file pointers (AGT-3), and a report is a short status, not a rule-file dump.
- A dispatched agent's own `rules.md`/`workflow.md` is not pre-loaded by the orchestrator for the normal dispatch-and-track flow (`SKILL.md` step 5).
- Resolve a missing detail by who owns it: the sub-agent's own action, decision or state goes to it via `SendMessage`; a rule, source file or diff the orchestrator can open, it opens.
- An unexpected or seemingly rule-conflicting report escalates cheapest first: ask the sub-agent for a short explanation, and only if that leaves it unclear, read the one section of its rules or workflow needed to judge it.
- Bad: reading a role's full `rules.md` the moment its report looks slightly off.
- Bad: a `SendMessage` round trip for the contents of a file the orchestrator could read.

---

## WF-21: DIRTY-COMMIT-PROTOTYPING

**Statement:** Prototyping is the default mode; defer the verification stack until the developer calls the unit of work complete.
- Entry: none. `IS_HARDENING` off is the whole condition (WF-24 MODE-STATE).
- Sticky: holds across tasks and compactions until `mr hardening on|off`.
- Deferred: refactorer R1-R14, tester coverage, plan-writer audit, drd-writer convergence, gitter G7 (Phase 2, Step 3.1, Step 3.2, Phase 4 approval).
- Never deferred: the production build (WF-10). No test target, no `ctest`, no test binary, no suite of any kind.
- Coder scope: production files only. A test file's compile break is left for the verification flow, never patched here.
- Subject: `Verb (dirty) description`, so the range is `git log --grep='^(dirty)'`-able.
- Who commits: gitter, for any content an agent produced. The orchestrator, for its own direct-execution diffs.
- Commit shape: unchanged. G1, G2, G4, G8, G9, G12, G15 and G16 bind whoever runs the command.
- No approval gate: the commit lands, then `git log -1` shows what landed.
- Amend: the newest unpushed dirty commit's message only. Never content, never an older commit, never a pushed one.
- Close the range: one `Verb (hardening of <range>) <what changed>` commit, running the deferred stack against the whole range at once.
- What the marker means: the commit has not been reviewed. Clearing it is the review plus whatever the review demands - refactoring, wiring the deferred tests, or both. A subject edit clears nothing.
- Exit: `mr hardening on` and nothing else. A request that sounds like hardening is a reason to ask.
- Check: subject carries `(dirty)`; the right party ran the commit; the diff touches no test file; the gating build compiled production targets only.
- Check: the range ends in one hardening commit with a current-state body, not scattered per-commit fixes.
- Bad: a dirty range that never gets its hardening pass.
- Bad: rewording a subject to drop `(dirty)`, leaving the range unreviewed.
- Bad: deferring the build check along with the rest.
- Bad: amending a dirty commit's content, or an older one, instead of landing a verified commit.
- Bad: a coder running git itself, or fixing a test its own signature change broke.
- Bad: switching mode because a request sounded like it.
- Bad: dropping the commit conventions along with the deferred phases.

---

## WF-22: SCOPED-SEARCH-ONLY

**Statement:** Every `Grep`/`Glob`/`find`/`grep -r` runs against the narrowest directory that could plausibly hold the answer - one repo, or one subtree of it.
- A drive root, a workspace root holding several checkouts, or a home directory needs the developer to name that scope as the target.
- Unknown location: list the few candidate directories a human would guess first and search each narrowly, in parallel where independent.
- All candidates missing: report that and ask, rather than widening.
- A target directory holding unrelated multi-repo or multi-terabyte content is too broad however the search is phrased.
- Bad: a repo-root or drive-root recursive search as the first move, instead of starting from the plausible candidates.

---

## WF-23: WARNING-SWEEP

**Statement:** PostToolUse hooks flag mechanical issues live and never gate; after the last planned edit, one sweep lists every warning raised this task, resolves each - fixed, or stated why the flagged text is correct - and reports the outcome.
- Only the em-dash hook auto-fixes. Do not chase a warning edit by edit.
- A warning judged wrong is a hook defect: fix `claude/hooks/_checks.py` or the hook in the same pass, not only the flagged text.
- Bad: reacting to each warning the moment it appears mid-edit.
- Bad: ignoring a warning instead of resolving it or fixing the hook.

---

## WF-24: MODE-STATE

**Statement:** `IS_HARDENING` in the bashrc managed block is the only thing that says which mode the session is in; off or absent means POC.
- Set it: `mr hardening on|off`. Hooks re-read the line on every call, so a change applies from the next tool call.
- Survives: restarts, resumes, compactions.
- POC: WF-21's deferrals are in force and the developer builds the workflow per request. No roadmap, no convergence loops.
- POC sub-agents: investigation only. Explore for a lookup, general-purpose to assemble a picture from several places. Never a role dispatch to do the work.
- POC checks: style rules, commit conventions, DEL-6's dependency read, the production build. Nothing else.
- Hardening: the pre-work gate, role selection, dispatch discipline and the full verification stack, all as written.
- Only the developer changes the mode. A request that signals hardening is a reason to ask.
- Check: the action about to run matches the mode the hook last reported.
- Bad: a `(dirty)` subject under hardening.
- Bad: a role dispatch under POC that the developer did not ask for.
- Bad: trusting a remembered mode over the one the hook reports.
