# C++ - language-specific rules

Part of the orchestrator/coder. These apply to all C++ code.

## Build
- Build + run: `mr script run_cpp_tests <target> <pattern>`
- Never run the full test suite - only tests matching the changed module

## Windows API
- Project defines `UNICODE` in CMakeLists - always use W versions
  explicitly (e.g. `ExpandEnvironmentStringsW`, `SetEnvironmentVariableW`),
  don't rely on the macro
- Strings are UTF-8 `std::string`, not ANSI
- UTF-8 to `std::wstring`: use `utils::string::ToWString()`
  from `<utils/string/string.hpp>`
- Path conversions: use `reponame::filesystem::path` - construct from
  `std::wstring` or UTF-8 `std::string`
- Don't use `reponame::filesystem::path` solely as a string conversion tool

## Includes
- Don't reorder `#include` directives in existing code
- Group: project headers, then third-party, then stdlib
- Decomposition, naming, and structure rules (R1-R14) are in
  `refactorer/rules.md` - none of them are Python-specific

## Style preservation
- Don't remove or add comments unrelated to your changes
- Keep existing blank lines - don't reformat unchanged code
- Follow the style already present in the file you're editing

## Error handling
- Use RAII for resource management
- Check return values from Win32 API calls
- Log errors with enough context to diagnose (function name, error code)

## Member declaration order
- Never rely on member declaration order for correctness. Members
  construct in declaration order and destruct in reverse - a class whose
  correctness depends on that ordering is fragile to a later reader
  reordering fields for readability.
- If one member's constructor or destructor must run before another's,
  make that dependency explicit: an owning `unique_ptr` reset in the
  outer class's own destructor body, a named helper method, or a comment
  at both members stating the dependency and why. Do not rely on silent
  ordering alone.
- When you must depend on ordering anyway (a case a comment alone can't
  make safe - e.g. a lock that must outlive what it guards), state the
  dependency in a comment at the declaration of both members, not only
  one, so reordering either one is visibly wrong.
- Prefer restructuring to remove the dependency over documenting it,
  when restructuring costs little: extract the ordering-sensitive pair
  into their own small owning type, or use an explicit destructor body
  instead of leaning on reverse-declaration-order teardown.
