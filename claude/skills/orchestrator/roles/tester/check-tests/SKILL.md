---
name: tooling-check-tests
description: >
  Deep test review: score tests by business value, find coverage gaps,
  audit manual tests. Autonomous - runs all steps, presents report.
  Invoke with /tooling-check-tests or /tooling-check-tests manual.
argument-hint: "[full|manual]"
context: fork
allowed-tools: Read, Grep, Glob, Bash, Task, Edit, Write
---

# Check Tests - test review & gap analysis

Autonomous deep analysis of all tests, unit and manual. Runs every step
without developer interaction and presents one report at the end. The
developer reviews the report and decides what to act on.

**Execution model:** you orchestrate, agents read. One agent per 10 tests or
5 source files, at most 3 at once, parallel where files do not overlap.
Never read a full test or source file yourself.

| Mode | Scope | What it does |
|------|-------|-------------|
| **Full** (default) | All modules + manual tests | Score every unit test, find gaps, audit manual tests, produce report |
| **Manual** | `<project's manual-test file>` only | Cross-references, format compliance, gap analysis |

Invoke: `/tooling-check-tests` for full, `/tooling-check-tests manual` for
the manual audit alone.

For the test writing pipeline and rules, see tester rules and the
test-writing workflow.

## Project config

Placeholders resolve from the project's own CLAUDE.md or invocation context.

| Placeholder | What the project provides |
|---|---|
| `<test-suite command>` | Full-suite command (`pytest`, `python -m unittest discover`) |
| `<project>/<test-dir>` | Test directory (`tests/`, `src/tests/`) |
| `<project>/<source-dir>` | Source directory (`src/`, `lib/`) |
| `<project's manual-test file>` | Manual test plan (`tests/MANUAL_TESTS.md`) |
| `<project's project-config file>` | Project conventions (`.ai/PROJECT.md`, `CLAUDE.md`) |
| `<TICKET-ID>` | Issue tracker prefix used in commit and branch conventions |

Artifact paths under `.ai/` resolve at runtime and are project-agnostic:
coverage data at `.ai/artifacts/coverage.json`, the report at
`.ai/artifacts/test_review.md`, plan gaps at
`.ai/artifacts/gaps_BRANCH_PLAN.md`.

## Supporting files

- [manual test rules](manual.md) - manual/unit sync rules, writing strategy, formatting rules 1-20. Load for the manual audit.

## Current test state

```
Last test run: !`<project's test-suite command> 2>&1 | tail -5 || echo "<test-suite command> not available"`
```

```
TESTS.log (tail): !`tail -20 .ai/artifacts/TESTS.log 2>/dev/null || echo "No TESTS.log"`
```

---

## Full analysis (default mode)

### Pre-run checklist

1. `.ai/artifacts/coverage.json` is fresh - regenerate with the "Full coverage with JSON" commands from tester rules.
2. The full suite passes. Failing code is not evaluated.
3. `.ai/BRANCH_PLAN.md` is readable. Agents need it for business context.
4. Modules are batched so no more than 3 agents run at once.
5. Every agent prompt carries the token-limit bail-out instruction.

### Phase 1 - Collect coverage

Run the "Full coverage with JSON" commands from tester rules. The JSON gives
per file: `missing_lines`, `missing_branches` as `[from, to]` pairs,
`executed_lines`, and `summary.percent_covered`. Agents read the JSON, not
the text summary.

### Phase 2 - Map test files to source modules

Discover the mapping at runtime; there is no hardcoded table.

1. `Glob` `<project>/<test-dir>/test_*.<ext>` for test files.
2. `Glob` `<project>/<source-dir>/*.<ext>` for source modules, excluding `<init-file>`.
3. Read each test file's imports to see which modules it covers. `test_<module>.<ext>` covers `<module>.<ext>` by convention, confirmed against its `from <package>.X import ...` lines.
4. A source module with no test file is an untested module, handled by its own agent in Phase 3.

### Phase 3 - Evaluate, in parallel batches

Batch related modules, at most 3 agents at a time, next batch after the
current one returns. One Task agent per group, `model=sonnet`,
`subagent_type=general-purpose`, with this prompt:

```
You are reviewing unit tests for quality and business value.

CRITICAL: If you hit a token or context limit at any point, STOP immediately.
Return whatever partial results you have so far. Do NOT retry or continue.

## Scoring criteria - business value first

Score by how the tested code maps to features in `.ai/BRANCH_PLAN.md`. A test
covering a user workflow (<user-facing workflow A>, <workflow B>, <workflow C>)
scores above one testing internal plumbing, however complex the plumbing.

- 5 Essential - a user-facing workflow from the plan
- 4 High - logic directly supporting a plan feature (<helper A>, <helper B>)
- 3 Moderate - real but internal logic (<wrapper layer>, <I/O helpers>)
- 2 Low - real but weakly asserted, or duplicating another test
- 1 Very low - trivial behaviour that cannot realistically break
- 0 Useless - tautological, tests nothing real

Score 0-2 is flagged for rewrite or deletion. Tiebreakers within one score:
corner case or not, could the code break in a way this catches, duplicative,
mock asserting mock behaviour rather than real logic.

## Deep evaluation rules

Go beyond line coverage on uncovered paths:

1. Condition combinations - which `if/elif/else` branches interact, and which
   combinations across separate `if` blocks in one function are never tested
   together?
2. Global state sensitivity - which environment variables, filesystem state or
   git state does the function depend on, and are those combinations realistic
   in the tests?
3. Error propagation - when a callee fails, does the caller handle it, and is
   that handling tested? Trace errors up the call stack.
4. Module-level contracts - what does each module promise, and is the promise
   tested end to end?

## Docstring convention

Every test method carries a docstring describing the business logic under
test, referencing what the user or system does.

Good: `"""<workflow> title from issue tracker: ticket + summary -> '[<TICKET-ID>] <summary>'."""`
Good: `"""<external-api> failure -> None so callers can fall back gracefully."""`
Bad: `"""<external-api>('user') returns None when rc=1."""`
Bad: `"""mock_run.return_value = (1, '', 'error') -> assertIsNone."""`

Flag test methods with no docstring.

## Your task

1. Read `.ai/BRANCH_PLAN.md`, Context and Description sections.
2. Read `.ai/artifacts/coverage.json` for per-line and per-branch data on {source_file}.
3. Read the test file `<project>/<test-dir>/{test_file}`.
4. Read the source module `<project>/<source-dir>/{source_file}`.
5. For each `def test_*`: what it tests in one sentence, necessity score 0-5,
   the reason in one sentence, and whether it has a docstring.
6. For each meaningful uncovered path in the coverage JSON: worth a test or
   not, whether it supports a plan feature, and the scenario in one sentence.
   Skip import guards, logging-only branches, UI needing a display,
   interactive prompts, and dead code behind feature flags.
7. Group untested scenarios in three tiers: function-level (branches within
   one function), module-level (interactions between functions in one module),
   system-level (cross-module contracts users depend on).

## Output format

Return ONLY a JSON object (no markdown fences, no extra text):

{{
  "module": "{source_file}",
  "existing_tests": [
    {{
      "class": "TestClassName",
      "method": "test_method_name",
      "description": "What it tests",
      "score": 3,
      "reason": "Why this score",
      "has_docstring": true
    }}
  ],
  "proposed_tests": [
    {{
      "uncovered_lines": "45-52",
      "path_description": "What this code path does",
      "worth_it": true,
      "reason": "Why worth/not worth testing",
      "scenario": "Test scenario description",
      "tier": "function-level"
    }}
  ],
  "missing_docstrings": ["TestClass.test_method", ...],
  "untested_tiers": {{
    "function_level": ["description of gap"],
    "module_level": ["description of gap"],
    "system_level": ["description of gap"]
  }}
}}
```

Untested modules get one extra agent that reads each source file and returns
`proposed_tests` alone.

### Phase 4 - Merge and sort

Mechanical transformation, so Python does it, not the model. An inline
one-liner or a small script under `.ai/scripts/` reads every per-module JSON
under `.ai/artifacts/coverage/`, sorts by module then line, and writes
`.ai/artifacts/merged_review.json`:

```bash
python -c "import json, glob; data = sum((json.load(open(f)) for f in glob.glob('.ai/artifacts/coverage/*.json')), []); data.sort(key=lambda r: (r['module'], r.get('line', 0))); json.dump(data, open('.ai/artifacts/merged_review.json', 'w'), indent=2)"  # VALIDATED: example one-liner, per-project script under .ai/scripts/ is the documented alternative
```

Python sorts, the model formats.

### Phase 5 - Write the review file

Read `merged_review.json` and write `.ai/artifacts/test_review.md`:

```markdown
# Test Review - {date}

## Coverage Summary

| Module | Stmts | Miss | Branch | BrPart | Cover |
|--------|-------|------|--------|--------|-------|
| ... |

## Score Distribution

- Score 0 (useless): N tests
- Score 1 (very low): N tests
- Score 2 (low): N tests
- Score 3 (moderate): N tests
- Score 4 (high): N tests
- Score 5 (essential): N tests

## All Existing Tests (sorted by necessity, lowest first)

Score 0-1 are deletion candidates, score 2 rewrite candidates. Both are
handled in Phase 8C.

| Score | Module | Class | Method | Description | Reason |
|-------|--------|-------|--------|-------------|--------|
| ... |

## Missing Docstrings

| Module | Class.Method |
|--------|-------------|
| ... |

## Untested Scenarios

### Function-level gaps (branches/conditions within one function)

| Module | Function | Gap description |
|--------|----------|----------------|
| ... |

### Module-level gaps (cross-function interactions within one module)

| Module | Gap description |
|--------|----------------|
| ... |

### System-level gaps (cross-module contracts users depend on)

| Contract | Gap description |
|----------|----------------|
| ... |

## Proposed New Tests

### {module} ({coverage}% branch coverage)

| Lines | Path | Tier | Worth it? | Reason | Scenario |
|-------|------|------|-----------|--------|----------|
| ... |
```

### Phase 6 - Generate proposed tests

For each module with `worth_it: true` entries, spawn a Sonnet agent to write
the test code, under the test-writing workflow's rules.

### Phase 7 - Comment and docstring review

Spawn one Sonnet agent over the source modules:

```
You are reviewing code comments and docstrings for alignment with business logic.

## Your task

1. Read `.ai/BRANCH_PLAN.md` (Context + Description) - this defines what the system does
2. For each source module in <project>/<source-dir>/:
   - Read the module
   - Check every comment and docstring
   - Flag comments that describe code mechanics instead of business logic
   - Flag missing comments on non-trivial functions
   - Propose improved wording that ties to plan features

3. Look for logic that the plan DOESN'T describe but users should know about:
   - Edge cases with user-facing impact
   - Error recovery behaviors
   - Implicit assumptions or limitations
   Propose plan additions for these gaps.

## Output

Return two sections:
A) Comment improvements: [{file, line, current, proposed, reason}]
B) Plan gaps: [{description, impact, suggested_plan_text}]
```

Write plan gaps to `.ai/artifacts/gaps_BRANCH_PLAN.md` at once, so they
persist across sessions:

```markdown
# Plan Gaps - {date}

## {Gap title}

**Impact:** {who is affected and how}

**Suggested plan text:**

{markdown text ready to paste into BRANCH_PLAN.md}

---
```

At session end, tell the developer: **"Review
`.ai/artifacts/gaps_BRANCH_PLAN.md` - N gaps found that may affect users."**
Gap edits wait for the developer's approval before any commit, and the file
is deleted once acted on.

### Phase 8 - Post-review work, in order

#### 8A - Fix missing docstrings

Batch, no interactive loop: read the report's Missing Docstrings section, read
each flagged test and the source it covers, add a business-logic docstring per
the tester rules convention, run the full suite, commit "Add missing test
docstrings".

#### 8B - Write proposed tests

1. Take the `worth_it: true` proposals from the report.
2. Present all of them via `AskUserQuestion` with `multiSelect`, label the
   function name, describe the scenario and line range.
3. Spawn ONE Sonnet agent with only the approved proposals.
4. Run tests and coverage, fix failures, at most 2 attempts.
5. Commit "Add tests for uncovered code paths".

#### 8C - Review low-value tests

Local, no agents; every input is already in the report.

1. Take score 0-1 and score 2 rows, grouped by file.
2. Per test: print the full test body, plus `setUp`/`tearDown` when the class
   has them, then the score and reason.
3. Ask via `AskUserQuestion`: Delete, Rewrite (propose the version, developer
   approves) or Keep.
4. Record each decision in `.ai/artifacts/test_decisions.md` and apply nothing
   yet.
5. After the last test, apply the whole file's decisions in one batch.
6. Run the full suite, commit "Review low-value tests: delete/rewrite/keep".

### Phase 9 - Manual test audit

Run the manual audit below as the final step, appending to the same report.

---

## Manual audit mode

Reviews `<project's manual-test file>` for cross-reference validity and format
compliance. Runs as the last phase of a full analysis, or alone via
`/tooling-check-tests manual`.

### Phase 1 - Validate cross-references

Extract the annotations, `grep 'Covered by:' <project's manual-test file>`.
For each `test_module.TestClass.test_method`, confirm the file, the `class`
and the `def` all exist. A miss is a **stale cross-reference**.

### Phase 2 - Verify expected results

Compare each mapping's manual expected result, the text after `-` on the
checkbox, against the unit test's assertions. A manual test claiming "shows
exit code 1" against `assertEqual(rc, 0)` means the mapping is wrong or the
two have drifted.

### Phase 3 - Format compliance

Scan every checkbox line against `manual.md` rules 1-20:

- Missing `-` separator, or `→` in its place (rule 13)
- Label prefix before the command, "Verify:", "View:" (rule 13)
- Inverted "condition - action" (rule 14)
- Prose checkbox that belongs under `> Found:` (rule 14a)
- Cleanup without the exact command (rule 19)
- Missing `> Covered by:` annotation (rule 20)

### Phase 4 - Gap analysis

For each sub-flow marked `> [!caution] No unit test coverage`: can it be
unit-tested with mocks, what is its business value on the 0-5 scale, and
propose a test at score 3 or above.

### Output

Append to `.ai/artifacts/test_review.md`:

```markdown
## Manual Test Audit

### Stale cross-references
- 3f: `test_<module>.Test<Class>` - method `test_xxx` not found

### Expected result mismatches
- 2e: manual says "only current user assigned" - unit test does not check assignee count

### Format violations
- Line 142: `→` should be `-`
- Line 305: label prefix "Verify in log:"

### Coverage gaps worth testing (score >= 3)
- 1g-alt (local tooling ahead): score 4 - can mock merge-base --is-ancestor
- 6g (branch deletion cleanup): score 3 - can mock shutil.rmtree + os.path.isdir
```

---

## Implementation notes

- Agents hold Read/Glob/Grep and read their own files.
- Every agent reads `.ai/artifacts/coverage.json` for precise data and
  `.ai/BRANCH_PLAN.md` for business value; the manual audit also reads
  `<project's manual-test file>`.
- An agent that fails or returns unparseable JSON is logged, and the run
  continues.
- `.ai/artifacts/` is gitignored, so a re-run overwrites the report. The
  `.coverage` data file sits in the repo root, also gitignored.
- Framework, Python version and test conventions live in tester rules.
- Confirm the branch name against `<project's project-config file>` before
  running, and ask the developer when it does not match.
