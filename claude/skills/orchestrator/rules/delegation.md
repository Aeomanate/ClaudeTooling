# Delegation

## DEL-1: EXECUTION-STRUCTURE

**Statement:** Every code change goes through a coder dispatch - no exception for "small fixes", "just one line" or "trivial changes". POC mode (WF-24 MODE-STATE) suspends this for as long as the mode holds; it resumes the moment Hardening starts.

Execution begins only once the plan is approved, via the session-plan-checking
procedure, and takes one of two forms:

1. **Dispatch a sub-agent** - the default. Write the spec, dispatch, then
   verify the resulting diff by reading the changed files directly. The one
   exception is a trivial edit the orchestrator already has full context for,
   applied directly and announced, where all hold: single file, 5 contiguous
   lines or fewer, no new logic, control flow, functions or classes, and a
   pure value/label/constant swap - a typo fix, a magic-number rename, a flag
   toggle. A batch of individually-trivial edits (3+ files, or 10+
   line-equivalent swaps in one logical batch) is not that exception and gets
   dispatched.
2. **Instruct the user** - only when the user asks to implement it
   themselves, or the step needs a decision only they can make on their own
   machine.

The only files the orchestrator edits directly:
- Skill instruction `.md` files under `${AI_TOOLING_SRC}/claude/skills/orchestrator/`
  and agent definition files under `${AI_TOOLING_SRC}/claude/agents/*.md`,
  always at the source path, since the `~/.claude/...` deployed copies are
  symlinks the harness refuses to write through.
- State files (`BRANCH_PLAN.md` checkboxes).

**Skill-tree maintenance is orchestrator-owned**, in its own context - skill
`.md` files, agent definitions, skill-tree hooks - never delegated to a
persistent sub-agent. `skill-validation` is read-only on skill files: it
audits and reports, and the orchestrator applies the edit.

**Forbidden for every persistent sub-agent.** No persistent sub-agent may
Edit, Write or NotebookEdit any file under `claude/skills/`, `claude/agents/`
or `claude/hooks/`, regardless of dispatch wording. A dispatch instructing
such an edit gets REFUSE-OUT-OF-SCOPE citing DEL-1, and the orchestrator
applies it. Sub-agents may read those files and propose changes via
`SendMessage`.

- Everything else - shell scripts, Python files, C++/CMake files, any new file that will be executed - is code, and goes through a coder dispatch.
- Bad: creating a shell script directly because "it's just a few lines" or "it's infrastructure, not product code."

---

## DEL-2: WORK-DELEGATION

**Statement:** Audit, scan, test and analysis work happens in sub-agents, never in the orchestrator's own context - it gathers results and plans the next step. POC mode (WF-24 MODE-STATE) suspends this for execution work only; audit, scan and analysis work outside the direct edit still delegates.
- Sub-agents get what they need and no more: important snippets, file and line references, the general idea, pointers to discipline files - never full function or class bodies, per AGT-3 FRESH-CONTEXT.
- Massive reading - many files, a wide search - is itself an investigation task for a search or reasoning sub-agent.
- More than one file read directly for analysis, rather than a pointer lookup, is a violation.
- Bad: reading 5 test files in the orchestrator's own context to "quickly check" something instead of dispatching a search agent.

---

## DEL-3: DELEGATED-SHELL

**Statement:** Shell operations that mutate state or produce heavy output are delegated:
- Mutating git - commit, push, rebase, reset, branch, add, mv, restore,
  stash - routes to gitter, which owns the G-rules and the hook gates. No
  gitter dispatch happens until the current audit cycle's report ends with
  the exact phrase `CONVERGED - no further changes pending`; prose like "all
  resolved" does not qualify. In POC mode (WF-24 MODE-STATE) the orchestrator
  commits its own direct-execution diffs with no gitter dispatch, while
  content a sub-agent produced still goes through gitter in either mode.
- Full test suites and builds route to tester or coder - long output, and
  they own the discipline.
- Anything writing outside `.ai/` scratch.

The orchestrator runs directly:
- Read-only git: `status`, `diff`, `log`, `show`, `rev-parse`.
- Read-only search and inspection: `grep`, `ls`, `find`, `wc`.
- `mr script <name>` diagnostics and validators.

- The test is the delegated list, not every Bash call: a direct call violates only when it mutates git, runs a full suite or build, or writes outside `.ai/`.
- Bad: committing directly instead of dispatching gitter, or dispatching gitter before seeing the CONVERGED phrase.

---

## DEL-5: STATE-NOT-CONTENT

**Statement:** A dispatch to an interpretive role - plan-writer, fixer investigation, refactorer catalog phase, any role whose value is interpretation rather than mechanical execution - carries state, never finished content:
- Current state: file paths, line ranges, brief context.
- What changed this session: file paths plus a one-line summary each.
- The user-facing intent of each change.
- Pointers to the discipline files the role must read.

- Never pre-generated text the role is expected to insert verbatim, a sample format phrased "use this", or finished content to copy-paste.
- Bad: sending plan-writer a literal Decisions Log line to paste, instead of the change context plus a pointer to the template and rules.

---

## DEL-6: DEPENDENCY-READ-GATE

**Statement:** Any edit beyond DEL-1's trivial-edit exception - by the orchestrator or specced for a dispatched role, in any file rather than only the skill tree - is preceded in the same turn or earlier by a Read of the rule, workflow and reference files the touched area depends on.

- **Skill-tree edit** (orchestrator, direct, under DEL-1): the other rules in
  the file being extended, and any workflow file
  (`shared/rules/workflow.md`, a role's `workflow.md`,
  `skill_edit_workflow.md`) cross-referencing the section being changed.
- **Coder or other role dispatch**: the orchestrator has verified the actual
  dependent source files itself - not memory, not a compacted summary -
  before writing the spec.
- **Project docs, config, or anything else changing substantially**: the
  files referencing or depending on the section being changed, so the edit
  does not silently orphan a cross-reference.

- Bad: adding a new rule number to a rules file without first reading the sibling rules already in it, or the workflow files referencing the section being extended.
- Bad, equally, outside the skill tree in any language: changing a function's signature, a config key, or a script's path without first reading every caller that depends on the old form.

---

## DEL-8: EVIDENCE-IS-HINT

**Statement:** A fix dispatched off a reflog finding, prior-session note or memory-file entry also cites a controlled experiment from the current session, observing the failure under the original behavior and the fix working under the proposed change.
- Old findings bound where to look. They are never sufficient evidence alone.
- Bad: dispatching a fix off a reflog commit's claim, then discovering after several builds that the finding doesn't apply to the current build.

---

## DEL-9: DISPATCH-DONT-SKETCH

**Statement:** Outside plan mode, a made design decision is followed by the dispatch itself in the same turn, not by prose describing an intended dispatch "for your sign-off later".
- Sign-off before action means invoking plan mode explicitly.
- Bad: writing out a code shape as "preliminary, for your sign-off later" instead of dispatching it.

---

## DEL-10: ASK-BEFORE-ENFORCE

**Statement:** A user describing behaviour - expected, unexpected, surprising, or an invariant - is read as observational, and any enforcement or detection dispatch is preceded by an `AskUserQuestion`:
```
Options:
- Add code that enforces this invariant
- Add code that detects and logs violations
- Just understand - no code change
```
- Bad: the user says "X is a bug" and the orchestrator dispatches error-log code before confirming they wanted a code change at all.
