# Tester Rules

Rules for writing, naming, running, and verifying tests.
Referenced by all tester workflows and other skills that delegate to tester.

---

## Test-Pair Completeness

**Statement:** Every behaviour carries both tests - positive, that it fires under the right conditions, and negative, that it stays suppressed under the wrong ones.
- Applies to guard clauses, cache hit and miss, idempotency flags.
- Audit action: flag a single-sided behaviour as "Coverage gap - [positive|negative] test missing."
- Bad: the happy path alone, with the guarded-off case untested.

---

## The Main Mock Rule

**Statement:** Mock the function's own direct dependencies and nothing deeper, so the function under test becomes a pure input-output box.

Given a function calling `b()`, `d()`, `e()` and reading `G`: mock those four,
and nothing inside any of them.

```python
# Function under test:
def my_function(x):
    a = fetch_data(x)      # mock this
    c = parse_result(a)     # mock this
    return c or DEFAULT      # mock DEFAULT if it's external

# Test:
@patch('module.DEFAULT', 'fallback')
@patch('module.parse_result', return_value='parsed')
@patch('module.fetch_data', return_value='raw data')
def test_my_function(self, mock_jira, mock_parse, mock_default):
    result = my_function('PROJ-1')
    self.assertEqual(result, 'parsed')
```

`requests.get` inside `fetch_data` stays real and unreached, because
`fetch_data` itself is mocked. Each function is tested in isolation, in its own
test class.

- Patch at the import location where the function is used: `'pkg.module_a.helper'`, not `'pkg.module_b.helper'`.
- Read the file's imports before writing: a deferred import moves the mock target, since the patch binds the import location rather than the source module.
- No real filesystem paths. `tempfile.mkdtemp()` for all I/O.
- `side_effect` lists for sequential calls.
- A new call added to production code gets its mock in the tests.

### External Processes Are Always Mocked

**Statement:** `git`, `npm`, `curl`, any other external binary and the network are mocked at the function's own subprocess or HTTP call, even when the function under test is a thin wrapper around one.
- Scripted `(exit_code, stdout, stderr)` tuples per command, asserted against, test our command sequencing and output parsing - the only part that is ours.
- A test shelling out for real tests two things at once, and the dependency's own semantics are covered by its own suite.
- Bad: building a real git repo in a tempdir (`git init`, several `git checkout -b` and `git commit --allow-empty`) to test a function that only sequences git commands and compares their output. Each real spawn costs 100-300ms, so a handful of these dominate the suite's wall time for coverage a `run()` mock gives in milliseconds at the same fidelity.

---

## Writing Rules

### Structure

- Flat data preparation, flat assertions.
- Helper variables instead of `calls[0][0][0]`.
- Every non-trivial test gets a docstring: `"""input -> expected output"""`.

### Logger Mocking - Direct Dependency Only

**Statement:** Logger functions (`dbg`, `err`, `log`, `ok`, `warn`) are mocked when they are direct dependencies of the function under test, and never when they are reached through a helper.

| Call shape | Is `log()` a direct dep of `f()`? | Action |
|---|---|---|
| `f()` calls `log()` directly | YES | Mock `log()` (per Main Mock Rule) |
| `f()` calls `g()`, `g()` calls `log()` | NO - `g()` is | Mock `g()`. `log()` inside `g()` is unreachable because `g()` is mocked. |

- A logger call reached via a helper is unreachable once the correct direct-dep mock is in place. Wanting to mock one deeper in the chain means the test is not mocking its actual direct dependency.
- A deep logger mock silences production paths the test never meant to exercise, which hides leaks. `mr script leak_check`'s TESTS.log = 0 criterion catches unmocked-production-path leaks only while logger calls stay unsilenced below the direct-dep boundary.
- Verifying `g()`'s internals belongs in `test_g.py`, where `g()` is the function under test and its own direct deps, `log()` possibly included, are correctly mocked.
- Goal: zero ERR/WARN/LOG in TESTS.log after a clean run, reached by mocking the helpers that produce the output.
- Audit action: flag every `mock.patch('module.log/warn/err/dbg/ok')` and confirm the mocked function is a direct dependency of that file's target function.
- Bad: a test calling `cmd_X()`, which calls `helper()`, which calls `err()`, adding `mock.patch('module.err')` to silence it. Mock `helper()` instead.
- Bad: a broad `setUpModule` patch of `module.log/warn/err/dbg/ok` to quiet "expected log noise". Each one is suspect until the direct-dep relation is confirmed.

### Test structure at WARN/ERROR, not text at DEBUG/INFO

**Statement:** At WARN and ERROR, assert the structure - the right `log_kind`, the right fields, the right count. At DEBUG and INFO, assert only that the call happened.
- Exact-string pinning even at WARN and ERROR only where the literal text is load-bearing, such as a grep recipe quoting it verbatim.
- Bad: pinning a DEBUG formatter's exact output string.
- Bad: leaving a WARN or ERROR line structurally uncovered because "it's just logging".

### No tautological tests

**Statement:** A test asserts project logic, never language or framework behaviour.

```python
# BAD - tautological (tests Python dataclass defaults)
def test_evidence_defaults():
    e = Evidence(source_type='x', source_id='y', title='t',
                 relation='r', mentioned_in='m')
    self.assertEqual(e.content, '')  # tests @dataclass, not our code

# GOOD - tests project logic
def test_parse_jira_links_extracts_inward():
    result = _parse_jira_links(json_with_inward_link)
    self.assertEqual(result.jira_tickets[0].relation, 'is cloned by')
```

- During audit, flag these with "Tautological - remove: YES" and remove them in the test-writing step.

### No redundant tests

**Statement:** A test earns its place by catching a plausible breakage nothing else already catches. A tautological test exercises the language; a redundant one exercises real logic another test already pins.

Three shapes that usually fail that question:

- Asserting a parameter's declared default, when every other test in the file already calls the defaulted form.
- Asserting an accessor returns what the matching setter just set, with no logic between.
- An edge case a broader case already subsumes, such as empty input where the no-separator case covers the same branch.

- Two similar-looking tests are not automatically redundant: a positive/negative pair, or two cases split by a switch branch, each pin a different invariant. Keeping such a pair means naming the invariant each one holds.
- During audit, report a redundant test alongside the one that covers it. An empty removal list backed by per-pair reasoning is a real result; do not delete a test to make the audit look decisive.

---

## Naming

- Classes: `TestModuleName` or `TestFunctionName`
- Methods: `test_<what_it_tests>`, descriptive, no abbreviations
- Variables: `expected_result`, not `exp`
- Test data IDs: obviously fake and collision-proof, `<TICKET-ID>-123456789` rather than `<TICKET-ID>-5678`

## Docstrings

- Business logic, not code mechanics.
- Good: `"""GitLab failure -> None so callers fall back."""`
- Bad: `"""mock returns (1, '', 'error') -> assertIsNone."""`

---

## Run Commands

The canonical run sequence lives in
`~/.claude/skills/orchestrator/shared/common_resources.md`, "Canonical Python
test run sequence". Short form: `mr verify`, or
`python git_hooks_impl/entry_points/cli.py verify`.

Single file or class:

```bash
python -m unittest git_hooks_impl.tests.test_<file> -v  # VALIDATED: targeted debug run
python -m unittest git_hooks_impl.tests.test_<file>.<TestClass>.<test_method> -v  # VALIDATED: targeted debug run
```

Coverage, preferred entry point:

```bash
mr script run_coverage
```

The wrapper runs the three commands below in order and writes
`.ai/artifacts/coverage.json`, consumed by `check-tests` sub-agents per that
skill's Phase 1. Run from the repo root. Where the wrapper is unreachable:

```bash
coverage run --branch -m unittest discover git_hooks_impl/tests  # VALIDATED: documented fallback if the wrapper is unreachable
coverage report --show-missing  # VALIDATED: documented fallback if the wrapper is unreachable
coverage json -o .ai/artifacts/coverage.json  # VALIDATED: documented fallback if the wrapper is unreachable
```

**Framework:** `unittest` (stdlib) is canonical, and every CI, sanity and
pre-commit run uses it through `mr verify`.

`pytest` is for ad-hoc enriched runs where its features earn their place:
richer failure output (`-vv --tb=long`), single-test debugging (`-k <pattern>`),
plugin workflows (parametrize, fixtures, `pytest-xdist`), interactive iteration
(`pytest --pdb`). Those runs are exploratory, and the canonical unittest run
confirms afterwards.

- Bad: reporting "787 pytest pass" as the convergence signal. `mr verify` is the only gating source of truth.

**Python:** exactly 3.10, invoked as `python`, never `python3`.
**Logs:** redirected to a temp dir by `tests/__init__.py`.

---

## Leak Check Criteria

`mr script leak_check` implements these, and all pass after any test run:

1. **hook.log** does not exist. It is a sentinel: no production code writes that filename, so its presence means a stale code path is alive.
2. **tooling.log** has not grown, measured against the pre-test baseline at `.ai/.leak_baseline_lines`. Dormant when no baseline file exists.
3. **TESTS.log** is 0 lines, so no test triggered production file logging.
4. **BRANCH_PLAN.md** is intact. `mr verify` snapshots its size before the run and compares after, writing nothing. `leak_check` additionally compares the hash when `PLAN_HASH_BEFORE` is set, or diffs against `.ai/BRANCH_PLAN_COPY.md`.
5. **Wall time** is under `TEST_TIMEOUT_SECONDS`, default 10s.

- A corrupted BRANCH_PLAN.md means a test writes to the real PLAN_FILE: find it, patch PLAN_FILE to a tmpdir, fix the mock.
- A timeout means running the full refactorer pipeline to find mock gaps. Raise the timeout only after the scan is clean.

---

## C++ Tests

Google Test and Mock, CMake presets, never the full suite.

```bash
mr script run_cpp_tests <target> <pattern>
```

**Long-build timeout:** a `reponame` or `kiros` build can take hours, so every
**Long-build timeout:** a `reponame` or `kiros` build can take hours, so every
build command in those repos gets the maximum timeout, 120 minutes /
7200000ms.

### Known Log Paths, Not Repo-Wide Grep

**Statement:** Confirming a log line was written means resolving that process or account's exact log path first - from the code that opens it, or the documented location - and reading that file.
- A repo-wide grep hides a real defect: a service account unable to write its log produces nothing to find, which reads as absence rather than failure.
- Checking the known path is itself part of the test: it proves the account can write where it should, not just that the line exists somewhere.

### Real-Resource Calls Are Integration Tests

**Statement:** A test touching a real OS resource - an ETW session, a network socket, an elevated-token operation, anything needing privilege or hardware CI may lack - is an integration test and stays out of the default suite.
- Name it greppably: an `Integration` suffix on the suite name, or a separate suite, binary or CMake target outside the default `ctest` / `run_cpp_tests` invocation.
- Select it explicitly when it should run, via `--gtest_filter` or its own target.
- An environment precondition it cannot guarantee is checked at the top of the body, followed by `GTEST_SKIP()` naming what is missing. A skip reads as "couldn't run here"; a raw API failure reads as broken code.
- The Main Mock Rule and External Processes Are Always Mocked still hold. An integration test covers only what a fake genuinely cannot verify - an empirical spike into real platform behaviour, a one-time environment probe - and never ordinary regression coverage of our own logic.
- Bad: a test opening a real ETW trace session inside the default `ctest` suite, so an unelevated run either fails outright or silently skips that path.

---

## Modes

- **Incremental**: changed module only
- **Full**: entire suite + coverage
- **Gap-fill**: post-task coverage gaps, one round, presented to the developer
- **Deep review**: [check-tests](check-tests/SKILL.md) for scoring and the manual test audit

---

## Referenced common rules

- DEL-1 EXECUTION-STRUCTURE, skill-tree editing forbidden for every persistent sub-agent - `~/.claude/skills/orchestrator/rules/delegation.md`
