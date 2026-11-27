# Keeping manual and unit tests in sync

Manual tests: `<project's manual-test file>`. Each sub-flow has `> Covered by:`.

1. **New unit test** → add `> Covered by:` to matching manual sub-flow
2. **Deleted unit test** → mark gap: `> [!caution] No unit test coverage`
3. **New behavior** → add manual test item
4. **Changed behavior** → update both manual + unit test
5. **Business value** → unit test without manual mapping = questionable

---

# Manual tests

Manual tests live in `<project's manual-test file>`.

## Writing strategy (iterative)

```
1. Coverage skeleton — one line per feature
2. Sub-flows + edge cases
3. Real output + verification commands
4. Checkbox discipline (rules 11-14a)
5. Formatting (rules 15-20)
6. Deprecation check
7. Map to unit tests (> Covered by:)
```

Each iteration: execute → present → gather feedback → plan fixes → approve → execute.

## Rules

### Content (iterations 2-3)
1. User commands only — describe tool outcome, not internal commands
2. Every verifiable step gets `- [ ]`
3. Preparation: `> [!important] Preparation:` blocks
4. Exact output from code, not paraphrases
5. Both y/n paths for prompts
6. Real variable names (`JIRA_API_TOKEN`, not "KEY")
7. No jargon ("exit code 1" not "rc=1")
8. `> Found:` for limitations/caveats
9. Dialog: title, buttons, shortcuts
10. Automated installs: observed outcome, not user action

### Checkboxes (iteration 4)
11. One action per checkbox
12. No OR — split into sub-flows
13. `command` — expected result (em dash, no `→`, no label prefix)
14. UI actions need `— result` on same line
14a. Prose observations → `> Found:` (not checkboxes)

### Formatting (iteration 5)
15. No HTML tags in plan text
16. Complex preparations get `> - [ ]` checkboxes
17. Long output in code blocks
18. No "same as" references — self-contained
19. Exact commands in cleanup (`glab mr close <iid>`, not "close MR")
20. Unit test mapping: `> Covered by: \`test_module.TestClass.test_method\``
