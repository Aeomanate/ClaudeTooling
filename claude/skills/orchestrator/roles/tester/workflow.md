## Tester Workflow

WORKFLOW NAME: tester (router across sub-role workflows)

The tester role coordinates four sub-role workflows. Tester selects the
right sub-role based on the developer's request and the current phase of the enclosing
workflow (fixer, featurer, refactorer, etc.).

| Sub-role | Workflow file | When to invoke |
|---|---|---|
| mock_audit | `mock_audit/workflow.md` | Verifying mock correctness in tests - mandatory before any test run |
| test_writing | `test_writing/workflow.md` | Writing new tests or fixing existing test gaps |
| test-design | `test-design/workflow.md` | Evaluating a test plan BEFORE writing (coverage + smell scan) |
| check-tests | `check-tests/SKILL.md` | Deep test review: scoring, coverage gaps, manual test audit |

---

## Phase 1: Identify the sub-role

Dispatch decision tree - select the first matching branch:

1. **Caller requests "mock audit" or "verify mocks"** → `mock_audit/workflow.md`
2. **Caller requests "write tests", "fix test gap", or "regression test"** →
   `test_writing/workflow.md`. If the function under test is new or complex, run
   `test-design/workflow.md` first (Phase 2 → Phase 3 ordering).
3. **Caller requests "review test plan" or "evaluate coverage before writing"** →
   `test-design/workflow.md`
4. **Caller requests "check tests", "score tests", or "full test review"** →
   `check-tests/SKILL.md`
5. **No explicit request but enclosing workflow requires tests** → use the cross-role
   dependency table in the orchestrator SKILL.md to determine which sub-role applies.

---

## Phase 2: Pre-work (per MA-4)

Before executing any sub-role workflow:

- **Mock audit is mandatory before any test run** (MA-4 AUDIT-BEFORE-TESTS,
  `mock_audit/rules.md`). If the enclosing workflow requests test execution,
  complete `mock_audit/workflow.md` to convergence first.
- Dispatch the built-in `Explore` agent to find what files to read when scope is
  uncertain (e.g., which test files map to a changed source module).
- Dispatch a fresh general-purpose sub-agent (sonnet model) for cross-cutting
  consistency checks (e.g., verifying that all planned mocks exist before writing
  tests). It is read-only and reports a pass/fail table.
- Read the sub-role's rules file before dispatching its sub-agents:
  - mock_audit: `mock_audit/rules.md`
  - test_writing: `test_writing/rules.md`
  - tester role-level: `rules.md`

Sub-agents dispatched from this role read the rubric themselves - pass a
file path and scope, not pasted rule text (per AGT-3 FRESH-CONTEXT).

---

## Phase 3: Execute the sub-role workflow

Tester executes the sub-role workflow by dispatching the named sub-agents:

- For **mock_audit** phases → dispatch `orchestrator-agent-tester_mock_auditor`
  (see `mock_audit/workflow.md` for the exact agent-instructions templates to pass).
- For **test_writing** phases → dispatch a fresh general-purpose sub-agent
  (sonnet model) when the scope spans multiple files, or write the test file
  changes directly from tester's own persistent context when the scope is
  small (see `test_writing/workflow.md` for the exact agent-instructions
  templates to pass and where the test files go).
- For **test-design** and **check-tests** → tester coordinates directly
  using the instructions in those sub-role files; dispatch fresh general-purpose
  sub-agents for per-file evaluation passes.

Per AGT-3 FRESH-CONTEXT: sub-agents always start fresh and read the
relevant rules and code themselves. Tester passes the task, scope, and
file paths - not pasted rule text.

---

## Phase 4: Verify and return

#### Step 4.1: Fresh analyzer dispatch

Tester dispatches a fresh general-purpose sub-agent (sonnet model)
directly via `Agent` (a persistent sub-agent may spawn its own per-task
verifiers), with a spawn prompt covering artifact paths (e.g.
`MOCKING.md`/test files), the rubric ("zero unmocked direct deps"), and
the expected PASS/FAIL table format. Tester reads the analyzer's report
from its final message and decides.

The sub-agent receives NO context from the editing session - fresh
perspective is the entire point. It is read-only.

#### Step 4.2: Loop decision

Read the analyzer's report:

- **CONVERGED - no further changes pending**: report to the enclosing workflow with status CLEAN. Exit loop.
- **FIXES FOUND**: apply fixes via plan-writer or coder (per fix type), then loop back to Step 4.1 with a fresh analyzer dispatch. Do NOT carry forward the previous analyzer's report.

**Completion checklist:**
- [ ] Analyzer dispatched fresh (not reusing prior context)
- [ ] Loop exited only on `CONVERGED - no further changes pending`
- [ ] Enclosing workflow notified with CLEAN | FIXES FOUND | PARTIAL status
