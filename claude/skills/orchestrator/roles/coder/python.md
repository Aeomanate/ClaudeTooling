# Python - language-specific rules

Part of the orchestrator/coder. These apply to all Python code.

## Version
Python 3.10 exactly. Command: `python` (never `python3` - triggers
Windows Store alias).

## Testing
- Framework: `unittest` (stdlib) - no pytest
- Run: `python -m unittest discover` (or project's standard test command)
- Coverage: `python -m coverage run --branch ...`
- See tester rules for full test pipeline

## Type hints
- Use for public function signatures when it aids readability
- Don't add type hints to code you didn't change
- Don't annotate obvious types (`x: int = 0`)

## String formatting
- f-strings preferred over `.format()` or `%`
- Raw strings for regex: `re.compile(r'\d+')`
- See `refactorer/python.md` R8 for the full rule and check

## Error handling
- Catch specific exceptions, not bare `except:`
- `try/except` blocks should be narrow - wrap only the line that can fail
- Don't swallow exceptions silently - at minimum `dbg()` the error

## Dataclasses
- Use `@dataclasses.dataclass` for data containers with multiple fields
- Use `dataclasses.field(default_factory=list)` for mutable defaults

## Imports
- stdlib first, then third-party, then project imports
- Alphabetical within each group
- No wildcard imports (`from module import *`)
- No deferred imports inside functions (see `refactorer/python.md` R6)

## Hook safety

- All git commands inside CLI commands MUST assume hooks are suppressed
- Never design a flow that depends on a hook firing during an internal git operation
- If a hook's behavior is needed (plan swap, MR sync, cache save), call the appropriate function directly from the relevant package
- Use `--no-verify` for internal push/commit to prevent hook recursion

## Destructive tooling-script operations

Any tooling script operation that deletes, overwrites without merge, or
otherwise irreversibly modifies user files follows a three-step approval
gate, as separate passes with no deletion/overwrite call between the
first and third:
1. **Collect candidates** - identify every target without touching
   anything.
2. **Print details** - for each candidate: file path, why it was
   flagged, what will happen (deleted / overwritten / replaced).
3. **Prompt for approval** - `prompt_yn(message, default_yes=False)`
   from `git_hooks_impl.utils`. No destructive action without explicit
   user confirmation.

**Scope:** every tooling script in the repo, not only `setup/` - hook
scripts that overwrite deployed files, validator/cleanup scripts that
auto-fix by deleting, any deploy/link/sync script with a deletion pass.

**Destructive:** deleting files, overwriting a file the user may have
customized, force-replacing a diverged symlink without consent,
truncating persistent state. **Not destructive:** adding a new symlink
where no target exists yet, refreshing a symlink already confirmed as
tooling-managed, read-only operations.

**Anti-pattern:** Collecting candidates and deleting them in the same
loop pass - the user never sees the list before the first file is gone.