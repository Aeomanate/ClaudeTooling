# Common resources

Resources callable from any role / persistent sub-agent. Each entry is
callable without role-context - the role-specific resources live under
each role's own dir.

## `mr` CLI

Before hand-fixing an infrastructure or tooling problem (a broken symlink, a
missing hook, a stale hard-link, an unmerged settings.json key), check
whether `mr` already has a command for it. Run `mr --help` for the
authoritative, current top-level command list - the table below is a
snapshot and can go stale the moment a subcommand is added or renamed.

Top-level commands, as of this writing:

| Command | Purpose |
|---|---|
| `mr sync [--force]` | Push MR description update (sync PLAN.md into the MR; `--force` overwrites a remotely-changed MR body) |
| `mr planget` | Pull plan from MR description into local `.ai/PLAN.md` |
| `mr plangen [--force]` | Generate PLAN.md via AI pipeline (uses cache; `--force` to regenerate) |
| `mr status` | Show MR + plan status |
| `mr setup` | Full setup - refreshes project hooks (if in a consumer project) AND user-global `~/.claude/` hard-links (agents, skills, hooks). Idempotent. Run this after any canonical edit under `ai_tooling/claude/` before assuming a new agent/skill/hook isn't wired up. |
| `mr new --branch-name <b>` | Create branch, generate plan (publish with `mr sync`) |
| `mr on` / `mr off` | Enable/disable ai_tooling (`AI_TOOLING_ENABLED` in `~/.bashrc`) |
| `mr verify` | Run lint (ruff) + test suite (unittest); exit nonzero if either fails |
| `mr script <name> [params...]` | Run a command from the script registry - see "Common scripts" below |
| `mr help` | Show the top-level help |

Run `mr <command> --help` for a specific command's full usage before
assuming a flag doesn't exist.

## Common scripts

Run `mr script` for the full list of available commands, or
`mr script <name> --help` for one command's usage. Do not look for script
names or arguments in this file - a static table here goes stale the
moment a script is added, renamed, or gains a flag; the live `mr script`
output cannot.

### Canonical Python test run sequence (ai_tooling project)

Use `mr verify` - it snapshots baselines, runs ruff + unittest, compares BRANCH_PLAN.md size and tooling.log delta in-flight, then calls `mr script leak_check`. Single command, all gates:

```bash
cd C:/Kragle/ai_tooling  # VALIDATED: canonical documented reference, not repeated elsewhere
python git_hooks_impl/entry_points/cli.py verify  # VALIDATED: canonical documented reference, not repeated elsewhere
# or if mr shim is active:
mr verify
```

**Individual gates (when mr verify is unavailable):**

```bash
# Ruff lint
ruff check git_hooks_impl/  # VALIDATED: canonical documented reference, not repeated elsewhere

# Test suite (direct)
python -m unittest discover git_hooks_impl/tests -v  # VALIDATED: canonical documented reference, not repeated elsewhere

# Leak check (after tests)
mr script leak_check
```

Do NOT repeat these as inline commands in dispatch messages - reference this section instead.

## Common agents

One-shot agents the orchestrator may dispatch via the `Agent` tool. No role
context required. Cheaper / faster model than callers where possible.

| Agent | File | Purpose | Model |
|---|---|---|---|
| `orchestrator-agent-drd_fake_reviewer` | `claude/agents/orchestrator-agent-drd_fake_reviewer.md` | Imitates the real CI ARC reviewer against a draft DRD in-session. Applies the distilled architecture rules to a draft DRD; produces the same single-page schema output the real CI reviewer would. Used during the drd-writer workflow's review phase. | sonnet |
| `orchestrator-agent-tester_mock_auditor` | `claude/agents/orchestrator-agent-tester_mock_auditor.md` | Audits test mock correctness - every direct dependency mocked, no indirect dependencies mocked. Read-only on source code; may run `mr verify` / `unittest` / `mr script leak_check` to confirm findings. Used during the tester workflow's mock-audit phase. | sonnet |

Any other bounded check (consistency audit, rule-compliance check, bulk
find-and-verify) is not a cataloged agent. Spawn a general-purpose sonnet
sub-agent directly with the check's scope and rubric - see AGT-3
FRESH-CONTEXT for how to write that dispatch.

Invocation example:

```
Agent({
  subagent_type: "orchestrator-agent-drd_fake_reviewer",
  description: "review draft DRD section 3",
  prompt: "DRD_PATH: <path>. OUTPUT_PATH: <path>. ITERATION_NUMBER: 1."
})
```

## How to invoke

**Script from any role:**

```bash
mr script leak_check
```

**Common agent:** the orchestrator holds the `Agent` tool and dispatches
directly. A persistent sub-agent that needs a common agent sends the
orchestrator the spawn details via `SendMessage` and asks it to dispatch.

**Convention:** scripts produce stdout + exit code (check `$?`); common
agents produce structured text reports (returned as agent output string).

## Custom tools

Tools available outside the orchestrator skill tree, installed by `mr setup`:

- **`drone` CLI** (reponame-space) - prepare/build project, docs, verifications.
- **`glab` CLI** - GitLab operations when the MCP GitLab integration is not enough.
- **`jira` CLI** - Jira operations (no Jira MCP configured).
- **`C:/Kragle` repo set** - local checkouts of related repos (`drd-review-automation`, `sw-arch-drd`, `kiros`, `reponame`, others). A checkout may be stale. Pull before reading it, not after finding a discrepancy. When a claim needs source not checked out anywhere here (a vendored/Conan dependency's header with no local checkout), search GitLab for it by name via `glab` and clone it locally before reporting the claim unverifiable - only report genuinely unverifiable after both the local scan and the GitLab search have failed.
- **`C:/Kragle` repo set** - local checkouts of related repos (`drd-review-automation`, `sw-arch-drd`, `kiros`, `reponame`, others). A checkout may be stale. Pull before reading it, not after finding a discrepancy. When a claim needs source not checked out anywhere here (a vendored/Conan dependency's header with no local checkout), search GitLab for it by name via `glab` and clone it locally before reporting the claim unverifiable - only report genuinely unverifiable after both the local scan and the GitLab search have failed.

## `.ai/` gitignore coverage

`mr setup`'s per-project install step (`setup/link.py`) appends a `.ai/`
ignore entry to a project's `.gitignore`, creating the file if absent,
idempotent on re-run. This makes `.ai/BRANCH_PLAN.md` and `.ai/cache/`
gitignored for any project set up after this was added.

**Do not assume every project already has it.** It only applies from the
run of `mr setup` that included the fix onward - a project set up earlier
needs `mr setup` re-run (or a manual `.gitignore` entry) to actually be
covered. Verify with `grep -n '\.ai' <repo>/.gitignore` before treating
`.ai/BRANCH_PLAN.md` as safe to leave unstaged without checking.

## What's NOT here

- **Per-role sub-agents** - live under `claude/agents/orchestrator-agent-<role>_<specialty>.md`
- **Persistent sub-agents** - lifecycle is the `Agent` tool: spawn once via
  `Agent`, reuse it via `SendMessage` for every later round. A one-shot
  agent spawns, runs, returns, and is done - no reuse.
