CRITICAL — OUTPUT FORMAT REQUIRED:
Begin your response with exactly this line (nothing before it, not even a blank line):
<!-- PLAN_CONTENT -->
Then write your output. Then end with exactly this line:
<!-- PLAN_STEP: OK -->
Do NOT begin output with `#`, `##`, or any heading before the opening marker.
Responses not wrapped in these exact markers are discarded by the parser.

Example of correct output shape:
<!-- PLAN_CONTENT -->
# [TICKET-123] Feature title
## Context
...content...
<!-- PLAN_STEP: OK -->

---

# Step 4 — Validate + Polish

You receive the plan as written through step 3. Validate + polish in ONE pass. Apply ALL rules.

## Rules

### A. TODO discipline (feature-level only)
- Classify each Implementation Plan item: KEEP (feature-level) / MERGE-INTO-PARENT / REWRITE-TO-FEATURE-LEVEL.
- Feature-level: "Pipe prompts via stdin to bypass 32 767-char limit". NOT: "Add input_data param to run()".
- KEEP: leave as-is. MERGE-INTO-PARENT: fold the item's intent into its parent feature bullet and delete the child. REWRITE-TO-FEATURE-LEVEL: rewrite as a user-observable outcome (1 sentence, present tense).
- Use `- [ ]` checkboxes grouped under `### P1`, `### P2`, `### P3`. Never `[x]`.
- Multi-stage items may nest sub-checkboxes (2-space indent). Example: `- [ ] Wire AI provider` with child `  - [ ] Replace CLI call with provider.text_completion`.

### B. Section content discipline
- **Title**: must match `# [{{JIRA_TICKET}}] {{JIRA_SUMMARY}}`. Fix if wrong; derive from branch if summary empty.
- **All template sections** present and non-empty. Missing → add `(needs investigation)` placeholder.
- **Architecture**: substantive (≥1 paragraph OR ≥1 mermaid diagram OR explicit named components) or `(needs investigation)` placeholder. A 1-line restatement of the goal is NOT substantive.
- **Success Criteria**: 3-7 bullets, user-observable requirements only (no class/method/field names, threading model, RAII, event IDs, build steps, test inventories). If currently >7, remove the least-observable bullets to fit. If <3, add `(needs investigation)`.
- **Cross-references**: every `(see Section X)` / `per the Architecture section` / etc. must point to a section that exists in this plan. Broken refs → fix the target name or remove the reference.
- **Areas of Impact / Risks**: impacts + risks only. Not test inventories, config constants, sequencing facts, architecture facts.
- **Decisions Log**: EMPTY (just the heading). Remove any generated entries — Decisions Log is for interactive sessions only.
- **No tooling references**: remove any `.git-hooks/`, `mr_ai_automation/`, Claude skills, Python hook tests.
- **Symbol-level and path-level claims** (function/class/method names, file paths) are NOT verified by this step — the AI cannot read project source or run `git ls-files`. Leave them as-is and surface ONE recall line at the bottom of the Decisions Log: `> [!recall] In next interactive session: verify all referenced file paths against \`git ls-files\` AND verify all named symbols (functions, classes, methods, structs) against project source.`
- **Verification commands**: use product test framework (`ctest`, `cmake`, `pytest`), not tooling's `unittest`.
- **No standalone Subtasks section**: any `**Subtasks:**` heading + table (or `## Subtasks` section) describing child Jira tickets is FORBIDDEN. Delete the heading + table. Each subtask should appear as a `- [ ]` checkbox in `## Implementation Plan` (formatted as `- [ ] [<TICKET>](<url>): <summary>`); if missing from the plan, MOVE the subtasks into Implementation Plan as checkboxes rather than deleting them outright. Inline prose references to specific subtasks ("tracked under PROJECTNAME-NNNNN") for context are OK.

### C. Spoiler policy
- ONLY Decisions Log inside `<details>`. All other sections VISIBLE.

### D. Plan-writer discipline
- Facts + intentions only. No commit-history narrative ("previously tried X"), no session codes.
- No local-only details: no commit SHAs, `C:/...` paths, `/tmp/...` paths, agent IDs, backup refs (`ORIG_HEAD`, `MERGE_HEAD`, stash refs).
- Wall-of-text → bullets (≥3 distinct claims or >80 words).
- ANY `→` arrow outside a fenced mermaid block is a violation, regardless of context (prose, inside backticks, table cells, list items, sub-bullets). Includes single arrows (`` `Hooks→Etw` ``), arrow chains (`` `master → etw_core → focus` ``), and state-transition notation. Rewrite as (a) prose with words ("CAS from Hooks to Etw"), (b) numbered list for sequences, or (c) move into a mermaid block if a diagram is the right shape. Exception: `→` inside a fenced ```mermaid block IS mermaid syntax — leave untouched.
- Semicolons stacking separate claims → separate bullets.
- Hedging strip: "expected", "may need", "should be" → direct assertions where defensible.
- Facts preserved: do NOT paraphrase or remove numbers, dates, metrics from earlier steps.
- Evidence notes (`> [!note] ...` blocks from step 3) are FACTS — never delete. May reorganize across sections per their content type.

### E. Mermaid repair
- Fix syntax errors listed in `{{MERMAID_ERRORS}}`. Do NOT remove mermaid blocks; do NOT alter correct diagrams.
- Prefer `flowchart TD` unless ≤5 nodes genuinely flow left-right.

### F. Linkification
- Bare Jira refs → `[PROJECTNAME-N](https://jira.companyname.io/browse/PROJECTNAME-N)`. Already-linked refs: untouched.
- Cross-repo MRs (`group/project!N`) → `[label](https://gitlab.companyname.com/group/project/-/merge_requests/N)`.
- Same-repo MRs (`!N`) → leave bare (GitLab auto-links).
- Never wrap a markdown link in backticks.

### G. Content-aware tense check

`{{BRANCH_DIFFS}}` tells you what THIS branch has shipped beyond its parent (`{{PARENT_BRANCH_NAME}}`). Validate that every delivery claim matches the diff state:

**Where to check:** Description bullets, Workflow / lifecycle steps, Automatic behaviors table rows, Architecture component descriptions, Risks bullets, Decisions Log entries.

**Per-claim verification:**
- Present-tense claim ("delivers X", "implements Y", "introduces Z") → verify X/Y/Z appears in `{{BRANCH_DIFFS}}`. If absent, demote to future-tense ("will deliver", "is planned to implement").
- Future-tense intent ("will deliver X") → leave as-is (no risk of misattribution).
- Subsection narratives (`### Workflow / lifecycle`, `### Automatic behaviors`) — apply the same per-claim check as top-level bullets. If the entire subsection describes unshipped behavior, retitle ("### Intended workflow (not yet implemented)").
- Automatic behaviors table — if all rows are unshipped, ensure column header is "Planned behavior" (not "Behavior" or "What happens"). Rows use future-tense.
- Risks bullets — failure modes of THIS branch's planned scope must be phrased as future-state ("Once X is implemented, an X outage will leave …"), never as present-state behavior of code not in the diff.

**Empty diff special case:** when `{{BRANCH_DIFFS}}` is empty / "(no diff stats)" / scaffolding-only, demote EVERY delivery claim across all sections to future-tense. No exceptions. Plan reads as pure intent / scope.

**Decisions Log carve-out:** Decisions Log entries are append-only historical reasoning; original tense preserved per PW-3. Do not retroactively demote.

### H. MR body template compliance

`{{MR_BODY_TEMPLATE}}` is the repo's chosen MR description template
(from `.gitlab/merge_request_templates/`). It may be a fallback skeleton
if the repo has no committed template. The template is pre-stripped of
GitLab directives (`/draft`, `/label`, `/assign`) before substitution —
those lines do not appear in `{{MR_BODY_TEMPLATE}}`.

**Precedence rule:** The plan template (Input section `{{PLAN_TEMPLATE}}`)
is the CANONICAL plan structure. Rule H only ADDS missing headings from
`{{MR_BODY_TEMPLATE}}`; it never RENAMES or REMOVES headings already
present in `{{PLAN_TEMPLATE}}`. If `{{MR_BODY_TEMPLATE}}` and
`{{PLAN_TEMPLATE}}` use different names for the same concept (e.g.,
MR template `## Areas of impact` vs plan template
`## Areas of Impact / Risks`), the plan-template name wins. Treat
heading comparison as case-insensitive and ignore trailing suffixes
(`/ Risks`, `(optional)`, `— TBD`) when deciding "same heading".

**Section structure check:** every `##` heading that appears in
`{{MR_BODY_TEMPLATE}}` (excluding `## Checklist`) must be present in the
plan, either by canonical plan-template name OR by exact MR-template name
when no plan-template equivalent exists. Examples:

- MR template has `## Bug description` (fix template) and plan template
  has no equivalent → ADD `## Bug description` heading with
  `(needs investigation)` placeholder.
- MR template has `## Areas of impact` and plan template has
  `## Areas of Impact / Risks` → MATCH; do NOT add a duplicate. The
  plan-template name stays.

**Strip MR-template scaffolding:** the MR template contains
instructional placeholders the AI MUST NOT migrate to the plan:

- Parenthesized prose like `(Meaningful description of the MR)`,
  `(A brief explanation...)`, `(Add a description of...)` — strip; these
  are author-prompts for the human filling the template, not content.
- Intro lines like "As a developer, I have ensured that:" — strip; this
  is checklist preamble, not a plan-bearing fact.
- Bracketed link placeholders like `[Jira Ticket Link]` — already replaced
  with the actual URL by the loader before reaching this prompt; no
  action needed.

**Checklist → P2 TODOs:** if `{{MR_BODY_TEMPLATE}}` contains a
`## Checklist` heading, every `- [ ]` item under it MUST appear as a
`- [ ]` checkbox under `### P2` in the plan's `## Implementation Plan`.
Add missing items verbatim. Do not reword. Items marked `(if applicable)`
stay as-is. Skip the intro line above the checklist items (e.g., "As a
developer, I have ensured that:") — only the `- [ ]` items migrate.

**No-Checklist branch:** if `{{MR_BODY_TEMPLATE}}` has NO `## Checklist`
heading (common for projects without a committed merge_request_template —
fallback skeleton has no Checklist), skip the Checklist → P2 rule
silently. Do NOT emit a "no checklist found" note or annotation.

**Checklist hygiene-item character:** checklist items are typically
universal pre-merge hygiene attestations ("My code follows the code style
guidelines", "All commits are properly formatted") rather than
branch-specific feature work. Migrate all of them to `### P2` per the
rule above; their universal-vs-branch-specific character is the project's
chosen convention and is not yours to filter.

## BAD examples

- Success Criteria: "<ServiceClass> spawns a background thread using `std::thread`" — implementation detail, not observable.
- Risks: "24 unit tests across 4 test files cover the new path" — test inventory, not a risk.
- TODO: "Add `input_data` param to `run()` in utils.py" — implementation, not feature-level.
- Evidence header: "From <TICKET-N> (<description> — Done)" — forbidden state suffix.
- Prose: "Backend subscribes /<route> → first event received → signals m_stop → joins worker" — use numbered list.
- Path: `C:/repo/path/to/file.cpp` — absolute machine path, strip to repo-relative.
- Description: "Implements <ComponentName> endpoint" — when <ComponentName> was delivered by a linked parent MR; should be "Reuses <ComponentName> established by <parent MR ref>".

## GOOD examples

- Success Criteria: "Game process list updates within 500ms of a process launch or exit."
- TODO P1: "Replace legacy <old-mechanism> subscription with <new-mechanism> registration."
- Evidence note: "From <TICKET-N> — prior <feature> implementation; approach reusable for <this branch's scope>."
- Teardown sequence: 1. Receive first event on `/<route>`. 2. Signal `<stop-event>`. 3. Join worker thread.
- Description: "Extends the <existing infrastructure> from <parent-branch> to cover <new scope>" — correctly attributes the baseline to parent and describes only this branch's incremental scope.

## Output

Emit the ENTIRE revised plan (every section, every line) between the markers — not a diff, not a summary. The plan ships as-is to the user.

## Input

CURRENT PLAN:
{{PLAN}}

MERMAID ERRORS (empty if mermaid is clean):
{{MERMAID_ERRORS}}

PLAN TEMPLATE (for section structure reference):
{{PLAN_TEMPLATE}}

MR BODY TEMPLATE (repo's chosen template — for rule H compliance):
{{MR_BODY_TEMPLATE}}

DOCS MANIFEST (for path validation):
{{DOCS_MANIFEST}}
