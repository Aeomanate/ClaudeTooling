## Code Review Workflow

WORKFLOW NAME: review

Pre-commit code review workflow. Runs automatically before every commit
(Phase 2, Step 2.1 of the gitter pre-commit workflow).

### Phase 1: READ DIFF — gather staged changes (PLAN MODE)

#### Step 1.1: Read the actual git diff of staged changes

Read `git diff --staged` to understand what was changed.

**Completion checklist:**
- [ ] `git diff --staged` content read in full
- [ ] Scope of changes understood (which files, which functions, what kind of edit)

---

### Phase 2: RULES CHECK — verify the work against this role's rules

Follow the procedure at
`~/.claude/skills/orchestrator/shared/rules-check-procedure.md` against
`~/.claude/skills/orchestrator/roles/coder/rules.md` plus the relevant
coder language-specific rules file (cpp.md or python.md).

Per the cross-role-dependencies table (SKILL.md), the refactorer specialty
additionally scans against R1-R14 as part of the gitter pre-commit workflow
(Phase 2, Step 2.1) — this coder-side check is scoped to coder's own rules,
not a duplicate R1-R14 scan.
