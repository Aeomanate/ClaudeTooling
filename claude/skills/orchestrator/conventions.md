# Orchestrator Conventions - Schemas and Reference

Behavioral rules are in [SKILL.md](./SKILL.md)'s `## Rules` section (PLAN, DEL, AGT, WF, DOC groups).
This file contains schemas, format templates, and reference material only.

---

## Rule shape

A rule is one statement phrased as the condition itself, then one line per
exception, per option and per anti-pattern. The statement carries its own
verification: if it cannot be read and applied directly, tighten it.

Two kinds, and only one belongs in a workflow:

- **Self-complying** - obeyed by writing the thing correctly: a commit
  subject's shape, a tag, a vocabulary, a file format. Reading the rule is
  the compliance. Cited where it applies, never given a step.
- **Step-bound** - an action someone takes at a moment, missable unless
  named: a dispatch, a re-read after a write, a build, a tool run. Named at
  the workflow step that performs it.

Never add a workflow step so a rule counts as covered. A self-complying rule
with no step is correct, not a gap.

---

## Dynamic Content Injection

The `!` backtick syntax in Claude Code skill files runs shell commands before
content is sent to Claude. Output replaces the placeholder.

Example: `` !`git rev-parse --abbrev-ref HEAD` `` → actual branch name.

Scope: Works in any file with Claude Code skill frontmatter (SKILL.md files)
and files loaded via SessionStart hook. Does NOT work in role.md, rules.md,
workflow.md, or agent-instructions/ files - those are read as raw text.

---

## Path Convention

All paths in documentation are relative to the project root.

Project root directories:
```

  .ai/          - plan, cache, artifacts (gitignored, runtime)
  .claude/      - skills, agents, hooks, settings (symlinked from ai_tooling source via mr setup)
  <project-source-dirs>/  - product code, tests, configs (project-specific)
```

---

## State File Locations

All state files use `.ai/` as root:

```
.ai/
  BRANCH_PLAN.md                       - current branch plan (single source of truth)
  BRANCH_PLAN_COPY.md                  - backup for leak checks
  cache/{sanitized_branch}/
    cached_BRANCH_PLAN.md              - per-branch plan cache
    base_PLAN.md                       - 3-way merge base
    local_PLAN.md, remote_PLAN.md,     - 3-way merge conflict artifacts
      merged_PLAN.md
    session_state.md                   - compaction resume point (WF-16)
    gen_cache/                         - plangen step cache (step1.md..step6.md)
  artifacts/
    hook.log                           - unified hook log
    TESTS.log                          - test output log
    coverage.json                      - branch coverage data
    refactoring/                       - audit/violation/coverage tables
```

---

## Agent Definition Troubleshooting

If a custom agent defined in `.claude/agents/` doesn't appear as an
available subagent type at session start:

- Verify symlink integrity (`mr setup` repairs dangling symlinks)
- Restart the session - agent definition changes take effect only on session start

---
