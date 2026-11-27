# C++ — language-specific tester rules

Part of the orchestrator/tester. These apply when writing or auditing C++ tests.

## Codebase Mocking Convention — Virtual Interfaces Only

**Mock through a pure-virtual interface.** Default to "make it virtual"
first; flag any deviation explicitly.

**Confirm the double's shape in the repo you are editing before writing
one.** The interface rule below is stable across these codebases. The
form the double takes is not, and it does not travel between repos:

| Repo | Double form | Verify with |
| --- | --- | --- |
| reponame | gmock `MOCK_METHOD` in a sibling `<name>.mock.hpp` | `Glob` for `*.mock.hpp` |
| reponame | gmock `MOCK_METHOD` in a sibling `<name>.mock.hpp` | `Glob` for `*.mock.hpp` |
| reponame_etw | hand-written `FakeX` in `tests/fakes/` | `Glob` for `tests/fakes/*.hpp` |

A repo with zero `MOCK_METHOD` occurrences is not a repo that forgot to
adopt gmock. Grep both forms and follow whichever the tree actually
uses. Carrying reponame's form into a repo that uses hand-written fakes
uses. Carrying reponame's form into a repo that uses hand-written fakes
produces a one-off pattern in that tree, which is the same failure this
rule exists to prevent.

Naming does not travel either. Check whether the tree writes `MockX`,
`XMock`, or `FakeX` before naming a new double.

Zero template-DI / template-based / duck-typed mocking precedent exists
in any of these trees. Introducing `std::function`-injection, adapter
wrappers, or template DI is a one-off unfamiliar pattern that creates
more maintenance friction than virtualizing the production class.

**Canonical example:** `reponame/router/include/reponame/router/request.hpp` declares `class request` with every method as `virtual ... = 0;`. The sibling `reponame/router/include/reponame/router/request.mock.hpp` declares `class RequestMock : public request` with `MOCK_METHOD()` for every method. The production class is a concrete impl that ALSO inherits the interface. Same shape at `mmdevice.mock.hpp`, `unified_profiles.mock.hpp`, `status_handler.mock.hpp`, etc.

**How to apply:**

- Before assuming a class can't be mocked, grep for `<header_basename>.mock.hpp` — see if a mock already exists.
- New mockable class: declare every public method as pure virtual in the header; ship a sibling `<name>.mock.hpp` with gmock `MOCK_METHOD` overrides.
- Existing concrete class needing a mock: ADD virtuals to that class (small bare-class change) rather than introducing an alternative pattern. Surface to coder for the virtualization edit.
- Reserve `std::function` DI, template DI, adapter wrappers, setter-based test injection only for cases where adding virtuals is genuinely impossible (third-party types from an external dep with no source access).

**Anti-pattern:** Recommending `std::function`-injection or template DI because the target class isn't virtual today. Default to "make it virtual"; flag any deviation with WF-1 skip-permission language.

## Run commands (C++ tests)

- Build + run: `mr script run_cpp_tests <target> <pattern>`
- Never run the full test suite — only tests matching the changed module
