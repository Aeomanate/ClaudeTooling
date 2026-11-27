## Skill Validation Workflow

WORKFLOW NAME: skill-validation

Validates all orchestrator skill conventions after any file changes.
Run before committing skill changes.

---

### Phase 1: AUTOMATED CHECKS - run scripts (PLAN MODE)

Content-level checks are WF-23's concern. This phase covers what a per-edit
hook cannot: whole-tree link-target existence and role file structure.

#### Step 1.1: Run full validation

```bash
mr script validate_skill_conventions .ai/SKILLS_REFACTORING.md
mr script validate_agent_files
```

#### Step 1.2: Review report

Read the report. Group violations by category.
If zero violations - proceed to Phase 3.
If violations found - proceed to Phase 2.

---

### Phase 2: FIX VIOLATIONS - one category per commit (EXIT PLAN MODE)

#### Step 2.1: Fix structural violations first

Missing files, wrong headings, broken links.

#### Step 2.2: Fix content violations

Incomplete agent instructions, stale references.

#### Step 2.3: Fix inline command violations

Extract raw commands to scripts. Use `mr` or script calls only.

#### Step 2.4: Re-run validation

Re-run Step 1.1's commands. If violations remain - back to Step 2.1.
If zero - proceed to Phase 3.

---

### Phase 3: DEEP VALIDATION - 1 agent per file (PLAN MODE)

#### Step 3.1: Launch validation agents

For each .md file in the orchestrator tree, launch a validation agent
using the validate-file agent instruction. Each agent receives:
- The file content
- conventions.md content
- Checklist: self-containment, no cross-role content, no duplications,
  adequate instructions, consistent terminology

1 agent per file. Max 10 in parallel.

#### Step 3.2: Collect and review

Merge all agent reports. If issues found - fix and re-validate.

---

### Phase 4: SYNC - propagate changes

```bash
mr setup
```

Verify report shows zero warnings.
