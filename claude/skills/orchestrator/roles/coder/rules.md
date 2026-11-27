# Coder Rules

Language-agnostic rules for coder work. Checked on every pre-commit (Phase 2,
Step 2.1 of the gitter pre-commit workflow).

---

## Unique rules

### CODER-1: DISCUSSION-FIRST

**Statement:** Every proposal presents pros, cons, what could go wrong and what details might be missing, in writing, before any code edit; a code change preceding its risk assessment is a violation.
- The session is a discussion: propose, warn, then let the developer decide.
- Bad: silently implementing a change whose risks were never flagged.

### CODER-2: ARCHITECTURE-DISCIPLINE

**Statement:** No dirty hacks (deferred imports, pointer or raw-bit magic), no magic constants, no re-creating what exists, one responsibility per function - a single magic number without a named constant, or one hunk duplicating logic already in the codebase, is a violation.
- Unclear decision-making goes to the developer for a decision, never resolved by patching around the problem.
- Search before writing anything new.
- Deferred imports are ruff-enforced; refactorer R6 ABSOLUTE-IMPORTS carries the fix. One responsibility per function is refactorer R1.

### CODER-4: TEST-FILES-ARE-TESTERS

**Statement:** Test files (`test_*.py`, `*_test.py`, `*_test.cpp`, `test_*.cpp`, `tests/**`, `conftest.py`, `pytest.ini`, `setup.cfg`) are tester-owned; any coder-authored edit to one without an attached tester spec is a violation.

A dispatch instructing coder to do test work is a routing mistake by the
orchestrator, and the reply is `REFUSE-OUT-OF-SCOPE: TEST-FILE`. Test
ownership is not transferable by dispatch wording.

Tester-owned, surfaced to the orchestrator:
- Adding or removing a test method, class or file - removal included, even when the behavior it tested was deleted
- Updating fixtures, sample data or mock setups when production behavior changes
- Changing assertions to reflect new expected behavior
- Modifying test infrastructure, or renaming and moving test files

Coder-owned, no routing:
- Reading test files to understand expected behavior of code under change
- Running pre-existing tests as read-only verification, via the project's canonical command (`mr verify`, or `python -m unittest discover git_hooks_impl/tests` per tester rules - never pytest)
- Surfacing observed failures with a fix-plan that delegates the test update

When a production change breaks existing tests: apply the production change,
run the tests, then `SendMessage` the orchestrator with the failing test list,
the suspected cause (production behavior change versus stale test assumption)
and the proposed fix shape. The orchestrator dispatches tester, which applies
the edits and reports APPLIED.

- Bad: "the dispatch told me to delete this test because the behavior was removed, so I deleted it."

### CODER-5: API-DOCS-FIRST

**Statement:** Any claim about platform-API behavior - Win32, ETW, COM, syscalls, vendor SDK semantics, language runtime internals - cites and quotes a docs URL fetched via `WebFetch` in the current session; a claim with no session-fetched citation is a violation.

- Fetch first even when the claim feels obvious from memory, and quote the exact sentence before paraphrasing.
- Docs and observed behavior diverging is documented as a fact - "docs say X; observed behavior is Y; mechanism not investigated" - never an invented mechanism.
- A docs page that is deprecated, undocumented or contradicts another page is flagged to the developer, not resolved by picking the most confident-sounding option.
- The `learn.microsoft.com/en-us/windows/win32/api/<header>/<member>` convention is right often enough to feel safe and not safe enough to skip the fetch.
- Applies to every language: Python `ctypes`/`subprocess`, Node native bindings, Linux syscalls, any vendor SDK - Win32 from C++ is only the most common case here.

Forbidden without a fetched-this-session citation, in user-facing text and code comments alike: "Per the docs, X behaves like...", "Microsoft documents that...", "The MSDN page for X says...", "By design, this API...", "The ETW kernel does...", "The Python interpreter does...", "POSIX requires that...".

- Bad: a hallucinated explanation becoming a load-bearing code comment, which misleads a future reader worse than no comment at all.

### CODER-7: WHY-COMMENT-MUST-BE-TRUE

**Statement:** Every why-comment's claim is confirmed literally true of the code beneath it, read rather than remembered from a similar pattern elsewhere.
- A wrong why-comment is worse than none, because a reader trusts it more than a what-comment. This is distinct from a stale comment: these are wrong at the moment of writing.
- Three real cases in one session: a "named local avoids dangling" comment where the named local was the form that dangles; a formatter comment claiming grep-compatibility with unrelated struct initializers; a comparator doc-comment asserting the exact fallback its own inner comment correctly rejects.
- Bad: writing "this uses X because Y" from general knowledge of why code often uses X, without reading whether this instance matches Y.

---

## Referenced common rules

These cross-cutting rules apply to coder work. Read them at the canonical paths:

- AGT-3 (Fresh-Context) - `~/.claude/skills/orchestrator/shared/rules/agents.md`
- STYLE-2 (No History - Narratives, Comments, or Checks) - `~/.claude/skills/orchestrator/shared/rules/style.md`
- DEL-1 (Execution Structure; skill-tree editing forbidden for all persistent sub-agents) - `~/.claude/skills/orchestrator/rules/delegation.md`
- WF-1 (Skip Discipline) - `~/.claude/skills/orchestrator/shared/rules/workflow.md`

The coder does not load or apply the R1-R14 rule-by-rule text. That mechanical
scan is refactorer's alone, later in the gitter pipeline (refactorer workflow
Phase 2 Step 2.1), against every commit regardless of who wrote it, and several
consumer projects (reponame and the other PRODUCT NAME / reponame-family projects) run their
consumer projects (reponame and the other PRODUCT NAME / reponame-family projects) run their
own equivalent review skill on top of it. The coder applies its own
language-specific file (`cpp.md`, `python.md`) plus CODER-2's principles as
general judgment, not a line-by-line checklist. A genuinely architecture-level
change - a new pattern, a cross-module restructure - surfaces to the
orchestrator per CODER-1 instead of being applied unilaterally.
