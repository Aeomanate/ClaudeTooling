# Planning

## PLAN-1: BRANCH-PLAN-LAST

**Statement:** A Read of a repository's full `.ai/BRANCH_PLAN.md` appears in the transcript before the first edit, commit, refactor, planning step or edit-capable sub-agent dispatch touching that repo; missing or out of order is a violation. Work spanning several repositories reads each one's plan before touching it.

The branch plan is that repo's plan-of-record - Implementation Plan TODOs,
Decisions Log, architectural context - and lives for the whole branch across
many sessions. Extend it, never rewrite it from scratch.

- No repo is proceeded on without its branch plan, or without asking the developer to generate one where none exists.
- A file past the Read tool's limit is read in chunks until every section is covered. Grep is never a shortcut to skip parts of it.
- **Completion checkpoint:** after the last chunk, one line per repo read this session, and no other pre-work step - role selection, role-file reading, workflow roadmap - starts until it is printed for the repo about to be touched:
```
{repo}/.ai/BRANCH_PLAN.md fully read: lines 1-{last_line} ({N} chunks)
```
- Bad: grepping straight to the TODOs section, skipping Context, Description, Architecture and the Decisions Log.
- Bad: reading only one repo's plan while supervising work that touches a second.
- Bad: trusting a persistent sub-agent's characterization of the plan instead of reading it first-hand.

---

## PLAN-2: REQUEST-VALIDATION

**Statement:** A large or complex request - several requirements, multi-step instructions, or anything past 3 tool calls - closes with a pass comparing the result against the original requirements, in which every original requirement appears in one of the three diff lists or unchanged in "What was done"; a requirement absent from all of them is a violation.

```
## Request Validation

### Original requirements
{bullet list}

### What was done
{bullet list}

### Diff against requirements
- ADDITIONS (done but not asked): {list}
- DELETIONS (asked but not done): {list}
- MODIFICATIONS (done differently, with reason): {list}
```

- Bad: declaring a multi-part request complete with no final diff pass against the original list.

---

## PLAN-3: NO-CACHE-EDITS

**Statement:** No agent writes under `.ai/cache/`, ever - not `cached_BRANCH_PLAN.md`, `base_PLAN.md`, `local_PLAN.md`, `remote_PLAN.md`, `last_mr_description.md`, nor anything else; a diff touching that path from any agent, on any branch, is a violation.

The orchestrator and plan-writer - its only dispatch target for plan edits, per
"Who triggers plan-writer" in the plan-writer rules - edit only
`.ai/BRANCH_PLAN.md`, the real working file. The cache is a snapshot the hook
system owns (`git_hooks_impl/plan/cache.py`'s `_save_cache` / `_restore_cache`):
a save copies the plan into the cache on push or commit, a restore copies it
back on checkout. An edit to the cache bypasses the working file and is
overwritten, or diverges silently, on the next swap.

- Bad: editing another branch's cached plan instead of switching to that branch and editing its `BRANCH_PLAN.md`.
- Bad: a plan-maintenance sub-agent writing its findings into `cached_BRANCH_PLAN.md`, or any hook-owned file under `.ai/cache/{sanitized_branch}/`, rather than the real plan.

---

## PLAN-4: POST-GENERATION-RECONCILE

**Statement:** A `mr plangen` result is a template, not a plan of record: after a first generation on a branch, a plan-writer dispatch reconciling the whole file appears before the first code edit or commit on it. A generated plan treated as authoritative with no reconciliation pass is a violation.

The generator reads Jira tickets and GitLab MR descriptions, never the
repository, and the pipeline applies none of the style rules. Two failure
classes:

- **Stale facts.** Ticket and MR text describes intent at the time it was written, and a later design decision makes it wrong without editing a word. Every file path, symbol, target name, command and dependency in a generated plan is a claim to verify against source.
- **Missing style.** Generated prose is long, repeats itself across sections and carries none of the STYLE rules. Compress it.

- Session context outranks the generated file: where a fact verified this session contradicts the generation, the session is right and the file gets corrected.
- The correction is plan-writer's work, dispatched with pointers to the verified findings. Not optional cleanup - it is the step where the plan becomes true.
- Bad: planning work against a generated "Important File Paths" table whose paths were copied out of an MR description and no longer exist in the repository.
