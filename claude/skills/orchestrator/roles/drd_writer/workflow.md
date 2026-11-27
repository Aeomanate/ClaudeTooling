## DRD Writing Workflow

A DRD is a design research document. It gives a high-level explanation of
planned changes, or of changes already implemented as a proof-of-concept.

See [DRD writer rules](rules.md) for all rules and limits.

### Phase 1: Setup

Working artifacts:

* The target DRD file in `../sw-arch-drd/drds/new-<short-slug>.md` for the active DRD-writing branch (one branch per DRD effort). CI renames it to `drd-NNNN-<kebab-title>.md` at merge - do not number or rename it yourself.

Read these before continue:

* The current branch plan: `.ai/BRANCH_PLAN.md`.
* The parent-branch plan if applicable:
  * From local source: `.ai/cache/{sanitized_branch}/cached_BRANCH_PLAN.md`, with `{sanitized_branch}` computed from the *parent* branch's name (`git_hooks_impl/plan/cache.py::_sanitize_branch_name` is the source of truth) - read-only, per PLAN-3 NO-CACHE-EDITS.
  * From GitLab description directly via `glab` CLI tool.
* Any reference DRD branch in `sw-arch-drd` with a committed DRD document for style and pattern guidance.

#### Step 1.1: Identify the target DRD file path and branch

Confirm the target DRD file under `sw-arch-drd/drds/` (named `new-<short-slug>.md`) and the active branch. If the DRD is new, scaffold from `sw-arch-drd/templates/drd_template.md` - it opens with YAML frontmatter (`title`, `created`, `authors`, `topics`) and has no revision table. Fill only those four author fields. Never set the CI-owned fields (`drd`, `mr`, `merged`, `status`) - lint rejects a wrong filename or frontmatter. DRDs are immutable once accepted. A substantive change to an accepted DRD goes in a new DRD that declares `supersedes: [N]`, not an in-place edit.

#### Step 1.2: Read the relevant plans

Read the current-branch `BRANCH_PLAN.md` and the parent-branch `cached_BRANCH_PLAN.md`
if applicable. Plans hold context the DRD will reference (decisions,
scope, design rationale).

#### Step 1.3: Check the reference DRD branch for style and ideas

In the `sw-arch-drd` repo, check any reference branch with a committed DRD document. Reuse style, structure, and patterns. The `sw-arch-drd/README.md` is a must-read for the DRD template conventions.

#### Step 1.4: Print the workflow roadmap and proceed after approval

List all phases + step names visibly before starting Phase 2.

---

### Phase 2: Section-by-section loop

> Enumerate all significant sections to have a full picture.
> Keep your focus on one section at one time.
> Don't produce the whole document at once.

For each significant section in the DRD template, run Step 2.1 then Step 2.2 before moving to Step 2.3.

#### Step 2.1: Investigation

> Investigate before writing. Optionally spawn one sub-agent for a broad search - not a team.
> Think, check documentation, APIs, and codebase. Don't generate answers "on the fly".
> Do it even if you "know the API from your training dataset."

The investigation may include:

* Repository searching for common patterns to defend the section's point of view.
* Searching the internet, reading API and vendor documentation.
* Reading the project-local Sphinx documentation, and relevant or semi-relevant internet pages.

#### Step 2.2: Implementation

> After investigation, start "implementation" of your findings. Describe your findings
> consistently for one section.

#### Step 2.3: De-bloat + wall-of-text restructure

Apply de-bloat to the section before moving to the next section.
Run the sentence test, the paragraph test, and the cross-section duplication rule from `rules.md`.

Continue Step 2.1 + Step 2.2 + Step 2.3 in sequence until all sections are filled.

---

### Phase 3: Full-pass polish (PLAN MODE)

#### Step 3.1: De-duplication consolidation pass (after key edits)

Run after any round of key edits - the initial section fill, or a large revision. Scan the whole document for repeated content: verbatim repeats, semantic duplicates, concept re-explanations, and table-vs-prose redundancy. For each repeated concept:

* Pick one canonical home. Prefer the earliest dedicated section, so references point backward.
* Keep the full explanation there. At every other site, state the fact inline in one clause, so the sentence stands alone.
* Reserve a cross-reference for material genuinely too long to inline. Every inward link is a readability cost - see DRD-15 in `rules.md`.
* If two occurrences disagree, that is a contradiction to resolve, not a duplicate to merge. Surface it.

This may be delegated to a fresh general-purpose sub-agent (sonnet model). Give it
the DRD path and a pointer to DRD-11 MINIMAL-DUPLICATION in `roles/drd_writer/rules.md`
(per AGT-3 FRESH-CONTEXT - no pasted rule text). Ask it to report verbatim and semantic
duplicate explanations, with section citations, excluding repeated key terms per
DRD-11's nuance clause. It is read-only on the DRD (AGT-3's verifier discipline).
Verify its clusters against the text before applying.

#### Step 3.2: Full-pass polish

> After filling all sections with this workflow, do one full pass to eliminate any gaps, mistakes, inconsistencies.
> Research the codebase, Sphinx documentation, and the internet if needed.
> Follow the rules and general style in `rules.md`. Propose fixes for inconsistencies and duplications.
> Check every inserted fact/number against STYLE-3 DRY-FACTS: strip scope caveats, justification clauses, and meta-commentary - keep the bare fact.
> Run the mermaid compilation check:

```bash
mr script compile_mermaid "<DRD_PATH>"
```

#### Step 3.3: Reader-path audit

Run after Step 3.1 and Step 3.2, before the Phase 4 mock review. This step enforces DRD-15 (Reader Path) across the whole document.

Spawn a fresh general-purpose sub-agent (sonnet model). Pass:

* `DRD_PATH` - the DRD under audit.
* `OUTPUT_PATH` - where the findings are written.
* A pointer to DRD-15 in `roles/drd_writer/rules.md` for the readability thresholds
  (per AGT-3 FRESH-CONTEXT - no pasted rule text).

Ask it to measure document structure (link density, heading counts, section balance)
against the DRD-15 thresholds and report a metrics table plus failed checks. It is
read-only on the DRD (AGT-3's verifier discipline).

After the agent returns:

* Read its output. Spot-check at least two of its counts yourself. A metric that disagrees with a hand count means the agent's bash is wrong.
* Stage the findings as a disposition table (finding, measured value, corpus baseline, proposed action).
* Relay the disposition table to the orchestrator via `SendMessage(to: "main", ...)`
  for an AskUserQuestion approval (drd-writer has no direct `AskUserQuestion`
  access - classic schema, AGT-26 RELAY-IDENTIFY in shared/rules/agents.md).
  Do not apply edits autonomously.
* Apply approved items, then re-run the auditor and report the metric deltas.

---

### Phase 4: Reviewer sub-agent

> Run a sub-agent to imitate a real review. Read `sw-arch-drd/ci/distill_architecture_rules.sh` first.

**Important.** The script itself cannot be executed. It requires CI environment variables and a merge request. The reviewer sub-agent uses the script's `claude -p` heredoc as the template for its prompt, and reads the same source documents the script feeds to its Claude call.

#### Step 4.1: Spawn the reviewer once, then reuse it

Iteration 1 only: spawn `orchestrator-agent-drd_fake_reviewer` per
`agent-instructions/drd-reviewer-dispatch.md`. Keep its agentId. Every
later iteration re-enters this same instance via `SendMessage` with the
new `ITERATION_NUMBER` and `PRIOR_GAPS` - do not call `Agent` again for
this role (AGT-1's reuse-before-spawning rule). The agent reads the DRD, the
template, the distilled ARC rules, and the reviewer roster, then writes a
one-page review:

* verdict line
* completeness note
* up to 5 architecture-alignment bullets
* up to 4 open-questions bullets
* one suggested reviewer
* a convergence line (`CONTINUE` / `STOP`)

#### Step 4.2: Read the agent's output

Read the review and decide the next step.

When a fake-review generates a todo list of dispositions, do not apply edits autonomously. Stage the disposition table, send it for developer review, wait for explicit approval, then apply.

---

### Phase 5: Fix gaps

For each gap from Phase 4:

1. Investigate the gap precisely (codebase, vendor docs, Sphinx).
2. Apply a single focused fix to the DRD body gap.
3. Surface any controversial decisions.
4. Move to the next gap.

---

### Phase 6: Loop or stop (PLAN MODE)

#### Step 6.1: Decision gate

* If iter < 10 AND the last cycle found improvements: return to Phase 3.
  Phase 4's reviewer is the same instance spawned at Step 4.1 - re-enter it
  via `SendMessage`, never a fresh `Agent` call.
* If iter == 10: stop. Hard cap.
* If the last cycle found no improvements: stop. Convergence.

#### Step 6.2: Handoff to developer

* Surface the final DRD path for sign-off.
* Do not commit, per DRD-2. The developer commits the final DRD at sign-off.

---

### Phase 7: Post-completion cleanup + end-to-end verification

#### Step 7.1: Architecture-altitude cleanup pass

After all sections are written, do one dedicated pass to pull the whole document to architecture altitude (see DRD-14 in `rules.md` for the place-vs-delegate criteria). Strip code-level noise: exact variable, member, or field names, hex constants, function-argument lists, CAS/lock/exception internals, log lines, call-by-call sequences. Remove out-of-scope operational decisions - legacy-path retention duration, removal/rollout tracking, telemetry-productionization timelines and owners - and delegate them to the relevant MR. Delete stale content. Fix references broken by the trimming. Keep architecturally meaningful numbers, the permission/security model, and the diagrams. Re-run the mermaid compile gate after editing.

#### Step 7.2: End-to-end DRD read

Read section-by-section using the section index built in Step 7.1, per
AGT-3 FRESH-CONTEXT's ranged-read discipline. Reserve a full, chunked end-to-end read for
a case where a cross-section contradiction is already suspected and the
section index alone can't resolve it.

#### Step 7.3: Adversarial gap-hunt across failure classes

Hunt explicitly across all failure classes:

* **Structural** - stale cross-references between sections, internal contradictions (Section A says X, Section B says not-X), silent omissions.
* **Content-quality** - possible bugs in code blocks, pseudocode, or API examples. Unwarranted assumptions ("X probably does Y" without verification). Unverified or forbidden claims (a cited file:line, a wrong API signature). Silly or garbage phrases (notes-to-self, placeholders, AI hallucination tells, filler hedging). Speculation framed as fact (no citation and no "verify at impl time" hedge).
* **Format** - arrow chains or semicolon-stacking in prose, history-narrative violations (dates outside a Decisions Log, opaque session codes), format inconsistencies, and any other rule from `rules.md`.

#### Step 7.4: Fix gaps or accept

* If gaps found: loop back to Phase 5 (Fix gaps) with the gap list and each gap's failure-class label.
* If no gaps: proceed to Step 6.2 (developer handoff).

**Completion checklist:**

- [ ] DRD read end-to-end
- [ ] All failure classes explicitly scanned, checked, and corrected (not sampled)
- [ ] Quantitative claims spot-verified
- [ ] Zero gaps, or all gaps known and described

---

### Phase 8: RULES CHECK - verify the work against this role's rules

Follow the procedure at
`~/.claude/skills/orchestrator/shared/rules-check-procedure.md` against
`~/.claude/skills/orchestrator/roles/drd_writer/rules.md` (DRD-2 through
DRD-15), scoped to the DRD path.
