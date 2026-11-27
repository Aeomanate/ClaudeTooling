## Test Writing Workflow

WORKFLOW NAME: Test Writing

Sequential pipeline for writing, verifying and committing tests. Each step
produces a plan or task list before execution.

**When to run:**
- Writing new tests for new or changed functionality
- Filling coverage gaps (Loop C of refactorer workflow)
- Fixer Step 5 (unit tests after bug fix)
- Featurer Step 4 (tests for new feature)

**Execution model**: See orchestrator conventions (Section 2: Orchestrator Execution Model).

Testing starts only from the tester state, no step is skipped, and nothing
is committed before every step completes.

---

### Phase 1: PREPARE (PLAN MODE)

#### Step 1.1: Check function complexity

A function with 4+ parameters, 5+ dependencies, or I/O mixed with logic
**STOPS the test pipeline**: save the planned tests, delegate to the
refactorer workflow, decompose, then resume.

**Empiric rule:** a dependency table from Step 2.1 with 5+ mocked rows for
one test means the function is doing too much. Delegate to refactorer, and
return once the refactoring is committed and existing tests pass.

#### Step 1.2: Explore call chains

Launch an Explore sub-agent to trace the full call chain of every function
under test. Report:
- Every function called (direct + indirect)
- Every external service touched (CLI tools, HTTP APIs, AI SDKs,
  webbrowser, filesystem writes outside tmpdir)
- Every function that needs mocking to prevent real side effects

The output is a **mock checklist** - every external call that MUST be
patched for each test to be safe.

**THE MAIN MOCK RULE: YOU MOCK ONLY AND ALL DIRECT DEPENDENCIES!**
See tester rules for the full rule and examples.

#### Step 1.3: Propose the test list and get it accepted

Produce the list of tests to write: test name plus one short, relevant reason
it needs to exist - the behavior, edge case or regression it catches that no
other test does. One line per test. Then:

- **The orchestrator already specified the list** (featurer's `P3-tests.md` stubs, a fixer regression-test spec): confirm the list matches that spec without re-proposing or re-justifying what it named, and flag only a missing test or one that looks redundant.
- **Otherwise**: send the list to the orchestrator via `SendMessage` and wait for acceptance before Phase 2. Never write a suite the orchestrator has seen no reason for.

A vague reason - "more coverage", "test the function" - is not acceptable;
name the specific behavior or edge case.

#### Step 1.4: Pre-write stability check

The function under test is stable before tests are written: no pending
refactoring flagged in the TODO list, no known bugs affecting it, no active
fixer workflow targeting the code. Unstable code means deferring.

**Completion checklist:**
- [ ] Function complexity confirmed acceptable (else delegated to refactorer)
- [ ] Call chains explored
- [ ] Test list proposed with one short reason per test, and accepted
  (orchestrator's own spec confirmed, or orchestrator approved your list)
- [ ] Pre-write stability check passed

---

### Phase 2: WRITE (EXIT PLAN MODE)

**TDD option:** For regression tests on bug fixes, the orchestrator may use
the red-green-blue cycle:

1. Write test that asserts expected behavior (RED - test fails)
2. Mock audit the test (mandatory before any run)
3. Run test to confirm it fails for the right reason (RED confirmed)
4. Implement/fix production code (GREEN - test passes)
5. Refactor if needed (BLUE - clean up)

TDD is preferred for bug-fix regression tests, because the RED step proves
the test actually catches the bug. New-feature tests may use the standard
write-first approach below.

#### Step 2.1: Build dependency tables

For each test method, produce a dependency table BEFORE writing any code, and
present all tables to the developer.

```
## test_create_initializes_and_publishes

Function under test: cmd_create()

| Dependency | Type | Mocked? | Mock value |
|-----------|------|---------|------------|
| run() | subprocess | YES | side_effect list (N calls) |
| run_interactive() | subprocess | YES | return_value=0 |
| _setup_base() | internal func | YES | no-op |
| generate_config() | internal func | YES | no-op |
| publish() | external (CLI tool) | YES | no-op |
| current_user() | external (API) | YES | 'testuser' |
| _restore_cache() | filesystem | YES | return True |
| CONFIG_PATH | constant (path) | YES | '/tmp/fake.cfg' |
| parse_input() | pure func | NO (pure) | -- |
| build_output() | pure func | NO (pure) | -- |
```

Rules:
- Every row with `Mocked? = NO` is justified
- An external dependency with `Mocked? = NO` gets its mock BEFORE anything else proceeds
- Two tables per test: happy path plus at least one failure path
- Tables reach the developer before any test code is written

After the tables are approved, tests are written to match them exactly.

#### Step 2.2: Write tests

Write tests matching the approved dependency tables, following the writing
rules in tester rules.

#### Step 2.3: Review every mock (via Review sub-agent)

Launch a fresh Review sub-agent to re-read test code AND production code side
by side. Per test it checks:
- Every `run()` / subprocess call has a mock side_effect entry
- Every external CLI tool invocation is patched
- `webbrowser.open` is patched if reachable
- All functions that perform I/O are patched if reachable
- No real cache or artifact directories will be created

The sub-agent is READ-ONLY: it flags, it does not fix. Gaps are fixed before
anything proceeds.

**Completion checklist:**
- [ ] Dependency tables produced for every test
- [ ] Developer approved tables before code written
- [ ] Tests written matching approved tables
- [ ] Review sub-agent confirms every direct dep mocked

---

### Phase 3: VERIFY (delegates to mock-audit workflow) (PLAN MODE)

#### Step 3.1: Run mock-audit workflow

Run the full mock-audit workflow for ALL tests written or modified.

**NEVER skip this step. NEVER run tests before this audit passes.**

#### Step 3.2: Handle gaps

Gaps found mean fixing them and returning to Phase 2. Convergence with zero
gaps proceeds to Phase 4.

**Completion checklist:**
- [ ] Mock-audit workflow ran to convergence on all new/modified tests
- [ ] Zero gaps remaining

---

### Phase 4: EXECUTE (EXIT PLAN MODE)

#### Step 4.1: Run edited tests (incremental)

```bash
python -m unittest <module>.tests.test_<file> -v  # VALIDATED: targeted incremental run, not the full suite
mr script leak_check
```

#### Step 4.2: Run full suite

```bash
mr verify  # VALIDATED: wraps ruff + full unittest discover + mr script leak_check
```

#### Step 4.3: Analyze failures (via Analysis sub-agent)

Any failure launches a fresh Analysis sub-agent, which answers seven
questions:
1. Do you know the full function body the test is testing?
2. Do you know what behavior the test is testing?
3. Was the test correctly written?
4. Was the function correctly written?
5. Do you have any propositions to developer?
   Maybe the function behavior isn't clear?
   Maybe there is a bug or a corner case?
6. What will you do with the function?
7. What will you do with the test?

Ask the developer about anything unresolved. DO NOT PROCEED WITHOUT PROPER
UNDERSTANDING - a fixing dead loop is easy to fall into.

#### Step 4.4: Check for leaks (via Explore sub-agent)

**4.4a. Read and analyze the test log thoroughly:**
Grep the test log for the leak signatures below with surrounding context
(`-A`/`-B`), per AGT-3 FRESH-CONTEXT's ranged-read discipline: real URLs
(production hostnames), real commands executed (external CLI tools), real
file paths written, stack traces from unmocked calls, HTTP status codes.
Every hit referencing a real external service is a leak. Fall back to a full
read only where a hit needs broader context.

**4.4b. Check filesystem:**
- No new cache directories from test data
- `git branch --list` - no new branches created by tests
- No unexpected new artifact files

**4.4c. Check external services:**
- No unexpected MRs/PRs/issues created
- Browser didn't open
- Check hook.log size unchanged

**4.4d. Deep leak exploration (via Explore sub-agent):**
Launch an Explore sub-agent to re-read the production code paths the tests
exercise, looking for:
- Call paths the Step 1.2 exploration missed
- New imports added since Step 1.2
- Conditional branches that only fire under specific mock states
- File writes or API calls behind try/except that silently succeed

Compare findings against Step 1.2's mock checklist, and fix any new gap
immediately.

ANY leak sends the pipeline back to Phase 1.

**Post-run leak check**: once tests pass, TESTS.log carries no unexpected
ERR/WARN from code paths the suite does not exercise. ERR/WARN in the log but
not in the test assertions is a mock gap, flagged to the orchestrator.

**Completion checklist:**
- [ ] Edited tests pass incrementally
- [ ] Full suite passes
- [ ] Failure analysis sub-agent ran on any failures
- [ ] Leak check clean (logs, filesystem, external services)

---

### Phase 5: FINALIZE (EXIT PLAN MODE)

#### Step 5.1: Run coverage, fill gaps

```bash
coverage run --branch -m unittest <module>.tests  # VALIDATED: module-scoped, not the full-repo run_coverage wrapper
coverage report --show-missing  # VALIDATED: module-scoped, not the full-repo run_coverage wrapper
```

Meaningful gaps remaining mean one more round, back to Phase 1.

#### Step 5.2: Post-run checklist (via Checklist sub-agent)

Launch a Checklist sub-agent to verify:
1. All tests pass
2. No logs/file/MR/browser leaks found
3. No unexpected ERR/WARN in TESTS.log
4. Docstrings on non-trivial tests
5. Edge cases covered
6. No duplicate test coverage
7. Each test is necessary, meaningful, business-valuable
8. **Manual tests updated** - a code change affecting user-facing
   behavior updates the manual test checklist:
   - New unit test: add `> Covered by:` to matching manual sub-flow
   - Changed behavior: update expected output in manual test
   - New feature: add manual test item

#### Step 5.3: Present to developer and commit

Present the commit message, test summary and coverage delta to the developer,
and wait for approval before committing.

**Completion checklist:**
- [ ] Coverage gaps filled (or noted as N/A)
- [ ] Post-run checklist sub-agent: all 8 items pass
- [ ] Manual tests updated where user-facing behavior changed
- [ ] Developer approved commit

---

### Phase 6: RULES CHECK - verify the work against this role's rules

Follow the procedure at
`~/.claude/skills/orchestrator/shared/rules-check-procedure.md` against
`~/.claude/skills/orchestrator/roles/tester/test_writing/rules.md` (TW-1
through TW-5) and `~/.claude/skills/orchestrator/roles/tester/rules.md`.
