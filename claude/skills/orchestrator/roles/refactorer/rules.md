# Refactorer - code quality and decomposition

Part of the orchestrator/refactorer. Load before AND after editing any code.

Refactor before writing tests - clean code is easier to test than messy code
with mocks. Coder rules cover general architectural decisions.

## When to invoke

- Before tester, when the function under test is too complex
- 4+ parameters threaded to sub-calls
- One body doing both I/O and logic
- 5+ mocks needed to test one function
- The developer says "this should be simpler"
- A function clearly does too much
- A class or module that deserves refactoring now
- A pattern repeating across 2+ functions
- Comment-block dividers inside a function, each block a decoupling candidate

## Core principle: decouple first, test after

A function that is hard to test gets broken into individually testable pieces,
and the tests are written against those. Evidence that decoupling is worth it,
without a clear call either way, goes to the developer as concrete options.

## Anti-patterns

- Refactoring with no tests, so no safety net
- Extracting a function used once, which is premature abstraction
- Renaming everything at once, making the diff too large to review
- Adding type hints to code the change did not touch
- "Improving" code outside the current task's scope

Class-extraction anti-patterns are R11's own BAD examples.

## Style preservation

- Leave comments unrelated to the change alone, in either direction
- Keep blank lines
- Leave import order alone
- Follow the existing style around the edit where it agrees with these rules

Refactoring never mixes with plan-driven editing. Inside a big plan piece, the
refactor becomes a TODO instead.

## Repo-local style reference (.ai-stuff)

A project carrying a `.ai-stuff/` submodule (reponame, kiros) gets a per-task
A project carrying a `.ai-stuff/` submodule (reponame, kiros) gets a per-task
sub-agent checking the diff against its repo-local standards -
`Coding-Standards/cpp-style.md`, `Coding-Standards/review-policies.md`, and the
matching file under `Languages/` - separately from the R1-R14 smell scan. Reuse
a sub-agent already holding that context rather than spawning another, per
AGT-1.

---

## Core refactoring rules

### R1: ONE-RESPONSIBILITY

**Statement:** A function threads at most 3 parameters onward and mixes none of {I/O, business logic, presentation}; split it until each piece needs at most one mock category.
- Similar functions sharing a shape are a class-extraction candidate, judged against R11.
- Extraction repeats until every piece qualifies - the first pass leaving a 3-mock piece is not done.

```
BEFORE:
  big_function()         → needs 8 mocks, 200 lines, untestable

AFTER:
  parse_input()          → pure, no mocks needed
  fetch_external_data()  → 1 mock (the API call)
  transform_data()       → pure, no mocks needed
  write_output()         → 3 mocks (filesystem, CLI out, GUI) → REFACTOR AGAIN
  orchestrate()          → mocks the functions above

AFTER:
  parse_input()          → pure, no mocks needed
  fetch_external_data()  → 1 mock (the API call)
  transform_data()       → pure, no mocks needed
  write_output_gui()     → 1 mock
  write_output_log()     → 1 mock
  write_output_cli()     → 1 mock
  orchestrate()          → mocks the functions above
```

### R2: STRATEGY-OVER-CONDITIONAL

**Statement:** An `if`/`elif` chain keyed on a type or kind, with 3+ branches each doing 10+ lines of distinct work, becomes a dispatch table.

```
# BEFORE:
def handle(template_type, data):
	if template_type == 'fix':
		...50 lines...
	elif template_type == 'feature':
		...50 lines...
	elif template_type == 'docs':
		...50 lines...

# AFTER:
HANDLERS = {
	'fix': handle_fix,
	'feature': handle_feature,
	'docs': handle_docs,
}
def handle(template_type, data):
	return HANDLERS.get(template_type, handle_default)(data)
```

### R3: GUARD-CLAUSES

**Statement:** Edge cases return early, nesting stays within 2 levels, and every precondition check precedes any side effect - logging, API calls, file writes.

```
# BEFORE:
def process(branch, ticket):
	if branch:
		if ticket:
			if find_tool('cli_tool'):
				... actual work ...

# AFTER:
def process(branch, ticket):
	if not branch:
		return
	if not ticket:
		return
	if not find_tool('cli_tool'):
		warn("cli_tool not found")
		return
	... actual work ...
```

A log line before the guard that can short-circuit it makes the log a lie:

```
# BAD: logs before checking precondition
log(f"Downloading data...")
if not find_tool('cli_tool'):
	return None  # logged "Downloading" but didn't download

# GOOD: early return, then log
if not find_tool('cli_tool'):
	return None

log(f"Downloading data...")
```

### R4: CLEAR-CONDITIONALS

**Statement:** Each part of a compound condition is a named boolean; no backslash continuation and no chained `.x().y().z` calls inside an `if`.
- A combination of named booleans that is still too long gets the same treatment again.

```
BAD:
if a.x().y().z == b.x().y().z or c.x().y().z == d.x().y().z:
	action()

GOOD:
is_ab = a.x().y().z == b.x().y().z
is_cd = c.x().y().z == d.x().y().z
if is_ab or is_cd:
	action()
```

### R5: ASCII-DIAGRAMS

**Statement:** A diagram in a source comment or a skill/agent markdown file is plain ASCII (`+--+`, `|`, `-->`, `v`), and flow notation (`A --> B --> C`) beats box layout.
- Unicode box-drawing (`┌─│└▶`) misaligns across fonts and renderers.
- BRANCH_PLAN.md diagrams are Mermaid instead, per plan-writer's Diagram Rendering rule.

### R6: ABSOLUTE-IMPORTS

Python-specific - see `refactorer/python.md`.

### R7: NO-ABBREVIATIONS

**Statement:** Every identifier is spelled in full words: `return_code` not `rc`, `error_code` not `ec`, `branch_name` not `br`.
- Length is not a cost worth trading clarity for.

### R8: RAW-OR-F-STRINGS

Python-specific - see `refactorer/python.md`.

### R9: WHY-NOT-WHAT

**Statement:** A comment gives the business reason or design decision; code that reads clearly gets no comment at all.
- A comment whose removal loses nothing the code below already shows is restating syntax.
- Good: `# GitLab rejects empty descriptions - fill a placeholder`
- Bad: `# set description to empty string`

### R10: NO-LEGACY

**Statement:** A refactorer pass leaves no superseded code path and no symbol without callers; any suspicion of dead code gets a trace agent immediately.
- Extracting a method, class or module, or reorganizing anything, includes the dead-code check on what it left behind.
- Grep for remaining references to every removed or renamed symbol before concluding.
- Scope that grep to source extensions, `--include=*.cpp --include=*.hpp` or excluding `.ai/`. `.ai/cache/` holds prior agent prose that names symbols with no code behind them, and such a hit never justifies keeping a symbol.

### R11: CLASS-EXTRACTION-EVIDENCE

**Statement:** A class is justified only when all four conditions hold across the analyzed call sites; any one failing means module-level functions.

1. **Shared mutable state** - several methods read and write the same fields, accumulating across calls, not a parameter passed once
2. **Method chaining** - callers invoke 2+ methods in sequence, each depending on the previous one's state
3. **Clear lifecycle** - init, work, cleanup, with the object owning resources between calls
4. **Multiple owners** - instantiated from 2+ distinct call sites that gain from the encapsulation

```
# BAD: wrapping stateless utilities in a class
class FileCache:
    def __init__(self, key):
        self.key = key
    def save(self):
        _write_file(self._dir, content)  # identical to save_cache(key)

# WHY BAD: all call sites analyzed -- every function called in isolation,
# no chaining, no accumulating state. key is computed once upstream.
# Class adds ceremony: FileCache(key).save() vs save_cache(key)

# GOOD: module-level functions for stateless operations
def save_cache(key):
    ...
def restore_cache(key):
    ...
```

```
# BAD: single-entry-point orchestrator class
class SyncFlow:
    def run(self):  # only public method
        self._step1()
        self._step2()

# WHY BAD: created and consumed in one place, the command function takes
# no arguments from callers, state is discovered internally. The class
# becomes: flow = SyncFlow(); return flow.run() -- one indirection
# layer, zero benefit.

# GOOD: keep as a function with helpers
def cmd_sync():
    branch = _discover_branch()
    data = read_data()
    _resolve_conflicts(data, branch)
    _update_remote(data, branch)
```

### R12: MODULE-VS-CLASS

**Statement:** Functions sharing a concern - caching, merging, parsing - go in a module; a class is for genuine shared mutable state with a lifecycle.

| Functions share... | Right tool | Example |
|--------------------|-----------|---------|
| Same concern, no shared state | Module | cache.py -- cache ops that take a key param |
| Same concern + mutable state across calls | Class | DataBuilder -- builds context incrementally |
| Same parameter threaded everywhere | Does state accumulate? No --> module. Yes --> class | Analyze call sites first |
| Same entry point, sequential steps | Function (not class) | cmd_sync() with helpers |

### R13: STASH-CHECK

**Statement:** Before calling a symbol dead, search the developer's working contexts - `git stash list`, sibling branches, scratch directories, and the plan's Implementation Plan and TODO sections - for its name.
- A helper positioned ahead of upcoming sibling work is not a deletion candidate.
- Bad: "Function X has zero callers in this MR - must be dead, removing it", with no stash or plan check.

### R14: SMELLS-INDEX-ON-DEMAND

**Statement:** A scan opens by loading the smells and patterns indexes, and cites only what the index turned up.

```bash
mr script dump_code_quality_reference
```

- Deep-read one smell file only when a candidate looks plausible but non-obvious.
- Patterns have no individual files; `patterns/ai_index.md` is the whole catalog.
- Bad: scanning with no index loaded, so catalogued smells go unnoticed.
- Bad: pre-loading the whole smells library, spending context on irrelevant smells instead of triaging through the index.

---

## Refactoring workflow

See [convergence workflow](./workflow.md) for the 5-phase loop and script
reference.

---

## Referenced common rules

- DEL-1 EXECUTION-STRUCTURE, skill-tree editing forbidden for every persistent sub-agent - `~/.claude/skills/orchestrator/rules/delegation.md`
