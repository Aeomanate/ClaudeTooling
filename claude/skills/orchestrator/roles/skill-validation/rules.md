# Skill Validation Role Rules

This role audits orchestrator skill files for convention compliance (heading
hierarchy, link conventions, path conventions, agent-instruction structure).

Content-level checks are WF-23's concern. The role's contract is what a
per-edit hook cannot cover - whole-tree link-target existence and role file
structure, via `mr script validate_skill_conventions` and
`mr script validate_agent_files` - plus the agent-instructions file. Rules
below are role-specific behaviors not covered by those.

---

## Unique rules

### 1. Use Existing Checks First

Before writing any new validation logic in this role, look at
`claude/hooks/_checks.py`'s predicates - the single implementation shared
by `check_content.py` and the `mr script` validators. If an existing check
covers the concern, invoke it via the relevant `mr script`. Add a new check
only when no existing one applies, and add it to `_checks.py`, not to a
role file or a validator script directly.

---

## Referenced common rules

These cross-cutting rules apply to skill-validation work. Read them at the canonical paths:

- AGT-3 (FRESH-CONTEXT) - `~/.claude/skills/orchestrator/shared/rules/agents.md`
- STYLE-2 (No History - Narratives, Comments, or Checks) - `~/.claude/skills/orchestrator/shared/rules/style.md`
- WF-1 (Skip Discipline) - `~/.claude/skills/orchestrator/shared/rules/workflow.md`
