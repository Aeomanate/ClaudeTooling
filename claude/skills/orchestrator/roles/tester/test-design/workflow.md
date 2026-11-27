## Test Design Evaluation Workflow

WORKFLOW NAME: test-design

Evaluates test plans BEFORE writing. Runs entirely in PLAN MODE.
Used before test-writing Phase 2 when creating a new test suite or major expansion.

---

### Phase 1: DESIGN REVIEW — coverage analysis (PLAN MODE)

#### Step 1.1: Read inputs
Read business spec (from BRANCH_PLAN.md or design doc), dependency tables (from test-writing Phase 2.1), and planned test method signatures.

#### Step 1.2: Behavior coverage check
For each documented behavior in the function's contract, verify at least one test covers it.

#### Step 1.3: Error path coverage
Verify: happy path + at least 2 failure scenarios (invalid input, external service failure).

#### Step 1.4: Contract gap analysis
Identify any scenario in the function's contract that has NO planned test. List as gaps.

#### Step 1.5: Produce gap report
Write structured report: covered behaviors, uncovered gaps, recommended additional tests.

**Completion checklist:**
- [ ] Inputs read: business spec, dependency tables, planned signatures
- [ ] Behavior coverage check complete
- [ ] Error path coverage verified (happy + 2+ failure scenarios)
- [ ] Contract gap report produced

---

### Phase 2: TEST SMELL SCAN (PLAN MODE)

#### Step 2.1: Mega-test detection
Flag any planned test with >5 assertions. Recommend splitting into focused tests.

#### Step 2.2: Vague mock values
Flag mock values like 'test', True, 123, 'foo'. Recommend business-meaningful values.

#### Step 2.3: Name-behavior mismatch
Verify each test method name describes what the test actually validates.

#### Step 2.4: Missing edge cases
Check for: empty input, None/null, negative numbers, max length, boundary values.

#### Step 2.5: Over-mocking
Flag pure functions being mocked unnecessarily. Pure functions should be called directly.

**Completion checklist:**
- [ ] Mega-tests flagged (>5 assertions)
- [ ] Vague mock values flagged
- [ ] Name-behavior mismatches flagged
- [ ] Missing edge cases flagged (empty, None, negative, max, boundary)
- [ ] Over-mocking flagged

---

### Phase 3: EFFICIENCY REVIEW (PLAN MODE)

#### Step 3.1: Setup duplication
Identify duplicated setup code across planned tests. Suggest shared fixtures or setUp methods.

#### Step 3.2: Test isolation
Check: class-level mocks properly scoped? Test order independence guaranteed?

#### Step 3.3: Lifecycle safety
Check: temp files will be cleaned? No real filesystem/network side effects? All mocked at boundary?

**Completion checklist:**
- [ ] Setup duplication identified
- [ ] Test isolation verified
- [ ] Lifecycle safety verified (cleanup, no side effects, all mocked at boundary)

---

### Phase 4: REPORT (PLAN MODE)

#### Step 4.1: Compile findings
Structured report with: coverage gaps, test smells, efficiency issues, lifecycle risks.

#### Step 4.2: Present to developer
Developer reviews findings before test-writing proceeds. May add/remove/modify planned tests.

**Completion checklist:**
- [ ] Findings compiled (gaps, smells, efficiency, lifecycle)
- [ ] Report presented to developer
- [ ] Developer review complete (additions/removals/modifications collected)
