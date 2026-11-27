# Agent Common

Blocks identical across every persistent orchestrator sub-agent. Each
agent's own MANDATORY pre-work list points here instead of repeating these
sections. Referenced, never read standalone.

## AgentsCommon rules (load BEFORE any non-Read tool use)

- `~/.claude/skills/orchestrator/shared/rules/style.md`
- `~/.claude/skills/orchestrator/shared/rules/agents.md`
- `~/.claude/skills/orchestrator/shared/rules/workflow.md`
- `~/.claude/skills/orchestrator/shared/rules/documentation.md`

## Compaction Reset

Per WF-16 RESUME-ON-COMPACTION (`shared/rules/workflow.md`).

## Sub-agent dispatch

You may spawn per-task sub-agents yourself when a fresh-context pass would
catch what your in-context reading might miss - reuse one already holding
matching context before spawning a new one. Per AGT-1 DISPATCH-DISCIPLINE
(`shared/rules/agents.md`).

## Approval Questions

Per AGT-26 RELAY-IDENTIFY (`shared/rules/agents.md`).

## Shared resources

Common scripts + shared agents catalog:
`~/.claude/skills/orchestrator/shared/common_resources.md`. You may invoke
a cataloged agent directly via `Agent({subagent_type: "orchestrator-agent-<name>", ...})`.
