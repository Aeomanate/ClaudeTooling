# Test Writing Rules

Rules for writing, naming, and documenting tests. Canonical bodies for
structure/naming/docstring/tautology rules live in `tester/rules.md`; this
file states only the write-time check/anti-pattern for each, plus rules
unique to test-writing (TW-2).

---

## TW-1: STRUCTURE

**Statement:** Per the "Writing Rules - Structure" section in `tester/rules.md`: the diff carries no chained indexing (`[0][0][0]`) on mock call objects, and every non-trivial test function has a one-line docstring in `input -> expected output` form.
- Bad: multi-level chained assertions, or a test with no docstring that has to be read whole before its subject is clear.

---

## TW-2: ERROR-PATH-MOCKING

**Statement:** A test exercising an error path mocks `err()`/`warn()`/`dbg()` only where the function under test calls it directly - per the Main Mock Rule and "Logger Mocking - Direct Dependency Only" in `tester/rules.md` - and running it leaves zero ERR/WARN lines in TESTS.log.
- A logger call reached through a helper means mocking the helper instead. The logger call then becomes unreachable, and the clean log follows as a consequence rather than a separate patch.
- Bad: patching `module.err`/`module.warn`/`module.dbg` to silence a call reached only through a helper.
- Bad: letting expected error or warn output reach TESTS.log - it masks real failures and makes the log useless for leak detection.

---

## TW-3: NO-TAUTOLOGICAL-TESTS

**Statement:** Per "No tautological tests" in `tester/rules.md`: a test whose assertion would still pass with the project's own logic deleted, leaving only language and framework primitives, is tautological.
- Audit flags it as "Tautological - remove: YES"; the test-writing step removes it.

---

## TW-4: NAMING

**Statement:** Per the "Naming" section in `tester/rules.md`: every test class, method and variable name in the diff describes what is tested without abbreviation, and every test-data ID is obviously fake when checked against the real ID formats used in the codebase.
- Bad: a method named `test_func1` or a variable named `res` - the body has to be read before the subject is clear.

---

## TW-5: BUSINESS-DOCSTRINGS

**Statement:** Per the "Docstrings" section in `tester/rules.md`: a docstring naming a mock, a return tuple or an assertion method describes mechanics rather than business behavior, and violates this rule.
- Bad: a docstring restating the mock setup and assertion instead of the business rule the test encodes.
