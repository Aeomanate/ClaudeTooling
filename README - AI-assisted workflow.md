# AI-assisted workflow

## How invocation works

The orchestrator skill auto-loads at every Claude session start. For each
request, the orchestrator picks the right role from fixer / featurer /
refactorer / tester / coder / gitter / plan-writer / drd-writer. The
orchestrator spawns that role's persistent sub-agent once via the `Agent`
tool, then reaches it for every later round via `SendMessage` - filename
`orchestrator-persistent-<role>`. A persistent sub-agent may spawn its own
one-shot sub-agents (a general-purpose sonnet sub-agent for a bounded check,
or one of the two cataloged one-shot agents) to keep its own context clean,
but it never spawns another persistent sub-agent - cross-role work always
routes back through the orchestrator. You stay in the loop via
`AskUserQuestion` gates. A persistent sub-agent has no direct
`AskUserQuestion` access - it relays the question to the orchestrator via
`SendMessage(to: "main", ...)`, which presents it to you. Plan mode covers
non-trivial work the same way.

## Per-intent table

| You want… | You ask AI this | You control | You rely on |
|---|---|---|---|
| **A new feature** | "I want to add X" | Review the featurer's plan; approve via AskUserQuestion or Plan-mode ExitPlanMode | featurer→coder→tester pipeline; refactorer convergence on quality issues |
| **A bug fixed** | "X is broken; repro: …" | Approve fix shape (concrete code preview) before any code change; review tests for the regression | fixer→tester mock-audit; R1-R14 rule check; regression tests written and passing |
| **Code quality cleanup** | "Code in X is poor; refactor it" | Approve scope after Phase 1 catalog; review each smell-fix candidate | 6-phase convergence loop (mock audit, rule convergence, coverage convergence, final pass, pre-commit, rules check) |
| **New tests** | "Write tests for X" | Review test design before any test write; review mock plan | tester mock-audit pass before any test run; coverage delta reported |
| **A commit** | "Commit this" | Approve commit boundaries; review commit message | gitter pre-commit pipeline (5 phases, G1–G15 rules); leak check; rules-check phase |
| **PLAN.md update** | "PLAN.md is stale; sync with current state" | Review proposed atomic edits BEFORE write | plan-writer convergence loop; per-section parallel agents; no-rewrite discipline |

## What you can trust without watching every step

- **Mock audit** - every test that hits a class with virtual methods is
  mock-checked before run; leaking mocks fail loudly, not silently.
- **R1-R14 rule scan** - code changes are scanned for the 14 refactoring
  rules before commit; violations block the commit.
- **PLAN.md atomicity** - plan-writer uses Edit calls per section; never full
  Write/overwrite. Decisions Log is append-only.
- **Symlink integrity** - `mr setup` re-validates that
  `~/.claude/skills/orchestrator/SKILL.md` resolves (via readlink) to the
  source file at `${AI_TOOLING_SRC}/claude/skills/orchestrator/SKILL.md`.
- **Post-compaction resume** - a `PreCompact` hook records the current
  workflow step just before compaction; the `SessionStart` hook with
  matcher `compact` injects a short resume block naming that step
  afterward, instead of the full mandatory-read manifest (WF-16
  RESUME-ON-COMPACTION). No developer action required.

## Hook discipline

Hooks keep AI focus on actual rules and workflows. They are symlinked
from `claude/hooks/` into `~/.claude/hooks/` and fire automatically in
every Claude session that touches this repo.

Gating by hook:
- `gate.py`, `session_start.py`, `precompact.py`, `resume_after_compact.py`
  - honor `AI_TOOLING_ENABLED`, silent outside a git repo and on the
  default branch.
- `check_em_dash.py`, `check_line_citations.py` - no gating. Run on every
  Edit/Write regardless of repo or branch.
- `check_persistent_agent_dup.py`, `clear_persistent_agent_registry.py`
  - no `AI_TOOLING_ENABLED` gating. Both no-op outside a git repo.

**PreToolUse - `gate.py` (matchers `Agent|Task`, `Bash|PowerShell`)**
States the current orchestrator mode, and only where the mode changes what
the next action should be: a role-agent dispatch, and a `git commit` or
`git push`. An investigation dispatch (`Explore`, `general-purpose`) and
every non-git shell command pass silently, as does any call made from
inside a sub-agent.

Mode comes from `IS_HARDENING` in the bashrc managed block, set with
`mr hardening on|off` and read back by the hook on every call, so a switch
applies from the next tool call. Off is the default: prototyping, direct
work, `Verb (dirty) description` commits, no verification stack. On is full
orchestration: role selection, dispatch, and the standing instructions
about style rules, session rules, and shared resources.

**SessionStart - `session_start.py` (matcher: `startup|resume|clear`)**
Fires at session open, resume, or `/clear`. Emits branch context,
`BRANCH_PLAN.md` status, a `glab` MR-plan check, the MANDATORY-TO-READ
manifest (the skill-file read list from `SKILL.md`), and a line naming the
available persistent roles. Prevents the common failure where a session
starts without ever reading the rules that govern it.

**SessionStart - `clear_persistent_agent_registry.py` (matcher: `startup|resume|clear`)**
Fires alongside `session_start.py`. Deletes the per-branch persistent-agent
duplicate-spawn registry that `check_persistent_agent_dup.py` maintains
under `.ai/cache/{sanitized_branch}/`, so a genuinely new session starts
with no memory of prior spawns. Not wired to the `compact` matcher - a
compaction is the same session continuing, and its live persistent
sub-agents are usually still reachable via `SendMessage`.

**PreCompact - `precompact.py`**
Fires just before a compaction. No stdout is injected (PreCompact output
is never added to context) - its only job is writing the current workflow
position (role, workflow, phase, step) to
`.ai/cache/{branch}/session_state.md`, read from the transcript's last
`[Orchestration: ...]` status line (WF-2B).

**SessionStart - `resume_after_compact.py` (matcher: `compact`)**
Fires immediately after a compaction. Reads the state file `precompact.py`
just wrote and injects a short `RESUME:` block naming the step to continue
- not the full mandatory-read manifest. Per WF-16 RESUME-ON-COMPACTION, the
session continues the named step and re-reads a rule file only for a new
task or a rule it must quote. Falls back to the full manifest if no state
file exists.

**PostToolUse: `check_em_dash.py`**
Fires after every Edit/Write on a `.cpp`, `.hpp`, `.py`, or `.md` file.
Reads the touched file, replaces each em dash (U+2014) with `-`, and
writes the file back. Reports the changed line numbers to stdout.

**PostToolUse: `check_line_citations.py`**
Fires after every Edit/Write on a `.cpp`, `.hpp`, `.h`, `.py`, `.md`, or
`.txt` file. Reads the touched file and reports any line containing a
`file:line` citation (STYLE-9 NO-LINE-CITATIONS). Detection only, it
never edits the file.

**PreToolUse (matcher: `Agent`) - `check_persistent_agent_dup.py`**
Fires before every `Agent` tool call. Blocks a second dispatch of the
same `orchestrator-persistent-<role>` type against the same repo (a
`C:\Kragle\<repo>` path matched anywhere in the dispatch prompt text),
enforcing AGT-24 SINGLE-PASS-VS-PERSISTENT at dispatch time. The literal phrase "unique
spawn" in the dispatch overrides the block for a genuinely intended
second instance.

## What you should still watch yourself

- **Architecture decisions** - orchestrator never decides "should we use
  OAuth or JWT?"; it asks via AskUserQuestion and waits.
- **Cross-role handoffs** - if a fixer needs a refactorer's structural
  change, the user is asked before the handoff.
- **Repo-wide conventions** - orchestrator checks against codebase
  conventions (mock-prefix, NVI precedent, etc.) but defers to user on
  whether to drift.

## Convergence loops you can rely on

- **Refactorer 6-phase** - mock audit → rule convergence → coverage
  convergence → final pass → pre-commit → rules check. Re-runs until clean.
- **Mock audit loop** - 4-phase, runs before any test run; loops until
  all mocks are correct.
- **Gitter pre-commit** - 5-phase (GATHER → REVIEW → VERIFY → APPROVE
  → COMMIT) with G1–G15 rule enforcement; non-skippable G7 gates on
  plan-update, consistency, approval, commit.
- **Plan-writer maintenance** - convergent edits per `## ` section; parallel
  agents (up to 10).
- **Post-workflow rules check** - coder, refactorer, tester, drd-writer,
  plan-writer, featurer, and gitter each end with a RULES CHECK phase: a
  general-purpose sonnet sub-agent reads the role's `rules.md` plus the
  changed files and produces a rule-by-rule verdict table (PASS /
  VIOLATION-CRITICAL / VIOLATION-MINOR / SKIPPED). Every violation gets
  fixed and the check re-runs, capped at 3 iterations, until the verdict is
  CLEAN.

## Common antipatterns the orchestrator catches for you

- "Just edit the file directly" - DEL-1 forces delegation to coder.
- "Skip the mock audit, the test is simple" - WF-1 SKIP-PERMISSION blocks
  any silent skip; skipping requires an explicit `AskUserQuestion`.
- "Bundle 5 unrelated fixes into one commit" - strengthened G1 blocks
  bundling AND over-splitting.
- "Trust the comment that says X" - comments-untrusted convention;
  agents grep for the actual behavior.

## Agent infrastructure

### Persistent sub-agents

Spawned once per role via the `Agent` tool, then reached for every later
round via `SendMessage`. Filename: `orchestrator-persistent-<role>`. A
persistent sub-agent may spawn its own one-shot sub-agents to keep its
context clean, but never dispatches another persistent sub-agent -
cross-role work routes through the orchestrator.

### Common (role-agnostic) one-shot agents

Two cataloged one-shot agents, callable from any persistent sub-agent or
role via the Agent tool:

| Agent | Purpose | Typical caller |
|---|---|---|
| `orchestrator-agent-drd_fake_reviewer` | Imitates the real CI ARC reviewer against a draft DRD in-session | drd-writer (review-loop iteration) |
| `orchestrator-agent-tester_mock_auditor` | Audits test mock correctness; read-only on source | tester (mock-audit phase) |

Every other bounded check - rule scans, consistency checks, plan-drift
verification - is an in-workflow dispatch of a general-purpose sonnet
sub-agent, not a cataloged agent type. The dispatching role gives it the
rule file path, the scope, and an output path; the sub-agent reads the
rules itself.

Catalog: `claude/skills/orchestrator/shared/common_resources.md`
(authoritative inventory of common agents + shared scripts).

### One-shot sub-agents (per role)

Spawned by a persistent sub-agent for a specific task within its own role
workflow, or dispatched by the orchestrator on a role's behalf.
