# Documentation Rules

Rules governing skill-tree document structure and formatting conventions.
Loaded as MANDATORY pre-work in every persistent sub-agent body. Answering
and writing style rules live separately in the
[answering and writing style rules](./style.md) - that file binds every
reply, this one governs where things live and how skill files are
structured.

## DOC-1: HEADING-HIERARCHY

**Statement:** Every `workflow.md` opens with one `## ` workflow name, uses `###` only for numbered sequential phases and `####` only for numbered sub-steps:
```
## Workflow Name
### Phase N: PHASE_NAME - short description
#### Step N.M: description
```
- `_check_headings` confirms the first heading is `## `; the rest is confirmed by reading. An unnumbered phase or step is a violation.
- Bad: `##` for phases, or mixed heading levels within one workflow file.

---

## DOC-2: ROLE-DIR-STRUCTURE

**Statement:** Each role directory holds `rules.md` (numbered rules, each with statement, rationale, anti-pattern), workflow file(s) and `agent-instructions/` - `workflow.md` at the role root for a single workflow, or `{workflow_name}/workflow.md` per workflow when a role has several.
- Optional: language-specific rules (`python.md`, `cpp.md`), `scripts/`.
- Two workflows in one file is a violation; `_check_structure` confirms the required files exist.
- `rules.md` holds only rule bodies. The role's purpose statement, dispatch-prompt templates and pre-dispatch resources live in the agent definition (`claude/agents/orchestrator-persistent-<role>.md` or `claude/agents/orchestrator-agent-<purpose>.md`). The role directory is the agent's own runtime read-set; the agent definition is the orchestrator's pre-dispatch read-set.
- Bad: putting rules inside `workflow.md`, or an orchestrator-side dispatch template inside `roles/<role>/`.

---

## DOC-3: SCRIPT-CONVENTION

**Statement:** A command in a workflow file is `mr {command}` for `ai_tooling` CLI operations, `mr script {name}` for registered skill-tree diagnostics and validators, or a simple read-only diagnostic (`cat`, `ls`, `grep`, `git log/status/diff`).
- Raw `python -m`, `coverage`, `cmake` and other complex invocations belong behind a registered `mr script` command.
- Bad: a full `python -m unittest ...` invocation written directly into a `rules.md` instead of wrapped in a script.

---

## DOC-4: SOURCE-PATH-EDITING

**Statement:** Every Write and Edit targets `${AI_TOOLING_SRC}/claude/...` (`C:/Kragle/ai_tooling/claude/...`) directly, because `mr setup` symlinks that tree into `~/.claude/` and the harness refuses writes through a symlink.
- Reads may use either path - both resolve to the same inode.
- The Read immediately before an Edit targets the same path the Edit writes to; reading the deployed copy does not satisfy it.
- Adding or deleting source files is followed by `mr setup`, to sync or clean up the `~/.claude/` symlinks.
- Bad: `Edit(file_path="~/.claude/skills/orchestrator/SKILL.md", ...)`, which fails with "Refusing to write through symlink."

---

## DOC-5: CROSS-REFERENCES

**Statement:** Within orchestrator skill files, a markdown link points only within the same directory (`[name](./file.md)`, `[name](subdir/file.md)`); everything else is plain text or backticks.
- Never a `../` link - plain text instead. These are flagged live by `check_content.py`; link-target existence is `mr script validate_skill_conventions`'s `_check_link_targets`, whole-tree only.
- Never an absolute path or a user-home env-var inside a skill file. Project state is project-relative (`.ai/BRANCH_PLAN.md`), user-home is `~/`, and `${AI_TOOLING_SRC}` is only for source-only paths with no `~/.claude/` counterpart.
- A file in another role is plain text (`refactorer rules`); a concept is backticked (`refactorer`); a user-invocable skill carries a slash (`/tooling-check-tests`); a file outside the orchestrator tree uses the `~/.claude/skills/orchestrator/shared/...` form.
- Outside the orchestrator skill, paths are project-root-relative (`.ai/BRANCH_PLAN.md`), never relative to the current file.
- Bad: a markdown link from inside `tester/` up and over into `refactorer/rules.md` via a parent-directory-relative path.

---

## DOC-6: RULE-DEDUP

**Statement:** Each rule has exactly one canonical file - cross-cutting rules (AGT, WF, DOC, DEL, PLAN) in `shared/rules/` or `rules/`, and a role-local `rules.md` carrying only role-unique rules.
- A cross-cutting rule reaches a role file as an ID and path under `## Referenced common rules`, never as a restated body.
- Bad: copying a cross-cutting rule's body into a role file "so the role knows it too."

---

## DOC-7: AI-TOOL-REFS

**Statement:** A skill file, workflow file or agent prompt names Claude Code's built-in tools rather than shell equivalents: `Read` not `cat`/`head`, `Grep` not `grep`/`rg`, `Glob` not `find`/`ls`.
- Bad: telling an agent to run `grep` as a shell command instead of using the `Grep` tool.

---

## DOC-9: ABSTRACT-TREE-SCRUB

**Statement:** Scrubbing project-specific content from a general skill file preserves the structure - paths, code shape, examples, table layout - and replaces only the concrete project tokens with abstract placeholders.

| Concrete (project-specific) | Abstract (preserve shape) |
|---|---|
| `.git-hooks/hooks/tests/test_*.py` | `<project>/<test-dir>/test_*.<ext>` |
| `[PROJECTNAME-1234] Fix race condition` | `[<TICKET-ID>] <one-line summary>` |
| `glab_api()`, `sync_mr()` | `<external-api-call>()`, `<workflow-step>()` |

- A file that becomes heavily project-specific gets a "## Project Config" section near the top, naming which placeholders a project overrides via its own `CLAUDE.md`.
- A deleted section, or a placeholder dropping a meaningful distinction, is a violation.
- Bad: replacing `glab_api()` with the word "function", losing the "external API call" distinction the original conveyed.

---

## DOC-11: AD-HOC-FILE-PLACEMENT

**Statement:** Ad-hoc scripts, verification helpers and transient artifacts are placed by expected reuse count, not convenience.

| Expected use count | Placement |
|---|---|
| 1 (one-time) | Run inline via `bash -c '...'`. No file. |
| 2+ (reusable) | Project helpers: `.ai/scripts/<name>.sh`. Skill-tree diagnostics and validators: a `mr script <name>` command in `git_hooks_impl/entry_points/commands/`. |

- Bad: writing a one-shot verification script to a file instead of running it inline.

---

## DOC-12: RULE-IS-CURRENT-STATE-ONLY

**Statement:** A rule states the current, strict rule as a bare fact - no comparison narrative ("we checked N other docs and found..."), no evolution story ("an earlier iteration used X and it was dropped"), no "predates this convention" caveats about older files that don't comply yet.
- Git history and commit messages carry that. A rule file carrying it too says the same thing twice and goes stale the moment the history stops being relevant.
- A comparison against a wider convention that motivated the rule belongs in the PR or commit description, or a one-time reply to whoever asked the design question.
- Read the `**Statement:**` alone, no other rules loaded: needing more than one read to find the actual constraint, because it is wrapped in "we found", "checking N sibling examples", "used to be" or "this project's own extension, not X's fault" framing, means trim to the bare rule.
- Bad: "Checking five other EVT sheets found none of them use a Tier column... so `reponame_etw`'s Coverage columns are Case Id, Expected, Results, Note" instead of just: "`reponame_etw`'s Coverage columns are Case Id, Expected, Results, Note."
