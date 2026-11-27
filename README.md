# AI tooling

>  [!WARNING]
>  This repo is an AI integration project around GitLab
>  As long as I don't have my own GitLab server now and prefer GitHub,
>  this repo remains untouched.
>
>  It's better to use it as a scripts and skills reference. 

After `mr setup`: `git push` syncs your local `BRANCH_PLAN.md` to the GitLab MR
description automatically. `git checkout <branch>` swaps in that branch's
plan from local cache. `mr new` creates a branch, opens a draft MR, and
pulls any existing plan in one command. Claude sessions in any project load
the orchestrator skill immediately - no per-project config, no copied files.

## What this is

AI tooling is a standalone repo containing the orchestrator skill, git hooks,
and install machinery that let Claude Code sessions follow team conventions
automatically across all your projects. Consumer projects (e.g. your work
repos) receive the tooling via symlinks into `~/.claude/` created by
`mr setup` - no submodule dependency, no per-project config.

Three things ship together:

- **Orchestrator skill + agents** - auto-loaded at session start in any
  project, enforcing role workflows (fixer / featurer / refactorer / tester /
  coder / gitter / plan-writer).
- **Git hooks** - 8 stubs symlinked into each consumer project. 6 sync your
  local plan to the MR description on push, swap plans on branch checkout,
  and prune cache on branch delete. The other 2 (`pre-commit`, `commit-msg`)
  forward to the external `pre-commit` framework and carry no plan-sync logic.
- **`mr` CLI** - on-demand commands for plan ops (`mr sync`, `mr planget`,
  `mr status`), branch lifecycle (`mr new`), and tooling
  control (`mr on`, `mr off`).

## Quick Start

```bash
# 1. Install (once per machine)
cd /path/to/ai_tooling && ./mr setup
source ~/.bashrc        # or open a new terminal

# 2. Wire each project (once per project)
cd /path/to/your-project && mr setup
```

**3. After updating ai_tooling** (e.g. after `git pull` in your local ai_tooling clone) - re-run `mr setup` to refresh hooks, agents, and scripts:

```bash
cd $AI_TOOLING_SRC && ./mr setup
```

A single `mr setup` re-links `.git-hooks/` stubs and refreshes `~/.claude/` (skills, agents). Claude Code hooks run straight from `$AI_TOOLING_SRC/claude/hooks/*` per `settings.json`, so there's no hook copy to refresh. Run once per machine after any ai_tooling update; consumer projects pick up the change automatically via the symlinks.

**4. Start a ticket** - creates the branch, pushes it, opens a draft MR, and
pulls any existing plan from the MR description into `.ai/BRANCH_PLAN.md`:

```bash
mr new --branch-name productname/fixes/PROJ-1234_short_description
mr new --branch-name productname/fixes/PROJ-1234_short_description
```

**5. Work normally** - on every `git push`, the hook reads `.ai/BRANCH_PLAN.md` and
updates the MR description automatically. No manual sync needed.

**6. Switch branches** - `git checkout other-branch` swaps `.ai/BRANCH_PLAN.md` out
for that branch's cached plan. `git checkout -` swaps it back. The swap is
silent; your working tree is unaffected.

**7. On-demand operations** (when you need them):

```bash
mr sync       # force-push local BRANCH_PLAN.md to MR description
mr planget    # pull plan from MR description into local BRANCH_PLAN.md
mr status     # show whether local plan is ahead, behind, or in sync
```

## Verify installation

```bash
# Re-run setup - idempotent, re-links anything diverged
mr setup

# Hook stubs accept expected args
bash git-hooks/post-merge

# Agent definitions have correct frontmatter
mr script validate_agent_files
```

## Troubleshooting

```bash
# Hook errors
tail -50 ~/.ai/artifacts/hook.log

# Check symlink target (should resolve to the source path)
readlink -f ~/.claude/skills/orchestrator/SKILL.md

# Check which hooks Claude Code loaded this session
grep "skill" ~/.claude/settings.json
```

If a symlink diverges from the source (points elsewhere, or was replaced by a
real file), run `mr setup` to re-link.

## Pick a doc

- **[README - Plan management.md](README%20-%20Plan%20management.md)** - install
  details, `mr` commands, settings.json merge, where files live, tooling
  on/off. Includes the data-flow and hook-execution sequence diagrams.
- **[README - AI-assisted workflow.md](README%20-%20AI-assisted%20workflow.md)** -
  orchestrator roles, pipeline phases, convergence loops, post-compaction
  rule preservation.
- **Source of truth for architecture** - `claude/skills/orchestrator/SKILL.md`
  is the canonical entry point that every Claude session loads at start.

## Tooling on/off

`mr on` / `mr off` flips `AI_TOOLING_ENABLED` in the `~/.bashrc` managed block (persistent across shells).

For one-off disable in current shell:

```bash
export AI_TOOLING_ENABLED=false
```
