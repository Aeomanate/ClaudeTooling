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

# Step 1: Fill MR body template

Fill the MR body template below using the provided context.

- Replace placeholder text in parentheses with real content from Jira
  and diffs.
- Keep ALL section headers exactly as they are.
- If you don't have enough context for a section, write what you know
  and mark gaps with (needs investigation).
- For "Bug description" / "Description": use Jira description as base.
- For "Root cause" / "Solution": use diffs and comments if available,
  otherwise mark as (needs investigation).
- For "Areas of impact": list affected components from the diff.
- Strip any terminal formatting artifacts (box-drawing characters,
  decorative lines) from the Jira content — use clean markdown only.
- **Subtasks from Jira → Implementation Plan checkboxes, never a standalone section.** If `{{JIRA_CONTENT}}` contains a Subtasks list/table (child Jira tickets), DO NOT reproduce it as a standalone `**Subtasks:**` heading or `## Subtasks` section. Instead, integrate each subtask as a `- [ ]` checkbox item under the relevant priority bucket in `## Implementation Plan`, formatted as `- [ ] [<TICKET>](<url>): <subtask summary>`. Each subtask represents work this branch INTENDS to deliver (matching the content-aware tense rule) — make it a TODO checkbox, never a delivered fact. If a subtask is genuinely out of THIS branch's scope (e.g. tracked in a separate MR), reference it inline in prose ("the WMI fallback work is tracked under PROJECTNAME-NNNNN") rather than as a checkbox.

IMPORTANT: The plan is about the FEATURE BRANCH, not the tooling system
that generates it. Do not reference .git-hooks/, mr_ai_automation/,
Claude skills, or Python hook tests. Focus on the product work described
in Jira.

If the diff is empty or contains only tooling changes, this is a NEW
BRANCH created for investigation — not a failure. Fill the template
using Jira context alone. Mark "Root cause" and "Solution" as
"(needs investigation)". Never ABORT just because there are no product
diffs yet — the plan is being generated BEFORE the developer starts work.

## Content-aware tense guard

`{{BRANCH_DIFFS}}` tells you what THIS branch has shipped beyond its parent (`{{PARENT_BRANCH_NAME}}`). Use tense per-claim based on what the diff backs:

**If `{{BRANCH_DIFFS}}` is empty / "(no diff stats)" / scaffolding-only:**
This branch has shipped NO product work yet — use future-tense for ALL deliverables. Verbs: "intends to", "will", "is planned to", "scope includes". Forbidden: "delivers", "implements", "introduces", "adds", "extends".

**If `{{BRANCH_DIFFS}}` shows partial implementation:**
Mix tenses per-claim. For each Description bullet, Workflow step, Automatic behavior row, Risk: check `{{BRANCH_DIFFS}}` to see if the named code (class, route, signal, helper, schema) actually appears.
- Code present in the diff → present-tense OK ("delivers", "implements")
- Code planned but not in the diff → future-tense ("will deliver", "is planned to implement")

**Subsection narratives:** `### Workflow / lifecycle`, `### Automatic behaviors`, and similar subsections are NOT exempt from this rule. Either:
- Mix tenses per-step/per-row based on what's actually shipped, OR
- Retitle the subsection ("### Intended workflow (not yet implemented)") if NONE of the named behavior is shipped yet.

**Automatic behaviors table:** when the no-commits guard fully applies (no shipped behavior yet), rename the "Behavior" column header to "Planned behavior" and write each row's value in future-tense.

**Implementation Plan items:** stay TODO (`- [ ]`) until the work actually ships. Never `- [x]` unless the named work IS present in the diff.

**If Jira ticket has no acceptance criteria AND no commits exist:** mark Description as "(scope to be defined)" — never invent deliverables.

## Parent branch context

This MR is INCREMENTAL on top of `{{PARENT_BRANCH_NAME}}`. The branch
diff below shows ONLY changes made on top of `{{PARENT_BRANCH_NAME}}`,
not the parent's own work.

CRITICAL — when filling the body:
- Describe ONLY this MR's incremental work.
- DO NOT describe parent-branch work as this MR's deliverables.
- If the parent branch introduced infrastructure (classes, libraries,
  endpoints) that this MR uses, reference it as PRE-EXISTING (e.g.
  "uses the <ComponentName> from `{{PARENT_BRANCH_NAME}}`") rather
  than as new work in this MR.

## Resource attribution

The MRs and Jira tickets in `{{AVAILABLE_RESOURCES}}` describe OTHER work — not this branch's deliverables.

This branch MAY: REUSE infrastructure those MRs introduced, BUILD ON their approach, LEVERAGE their helpers, EXTEND their surface.

This branch MUST NOT: DELIVER, IMPLEMENT, or INTRODUCE work those MRs already shipped; claim their deliverables as this MR's content.

USE: "reuses X from `MR !N`", "builds on Y established by `{{PARENT_BRANCH_NAME}}`".
AVOID: "delivers X", "implements Y", "introduces Z" — unless X/Y/Z is new in THIS diff (`{{BRANCH_DIFFS}}`).

## Available resources

These resources were discovered from the Jira ticket and its linked
tickets/MRs. You can request any of them for step 3 evidence enrichment.

**How to request:** Use the `id` field for jira_tickets and gitlab_mrs,
the `filename` for attachments.

**Always request:**
- GitLab MRs mentioned in the ticket description — they contain code
  changes and implementation context
- The parent ticket if it provides broader design context
- Attachments that are screenshots, logs, or config samples

Do NOT leave the REQUIRED_RESOURCES empty if there are available MRs or
parent tickets — they almost always provide useful context.

{{AVAILABLE_RESOURCES}}

## Input

MR BODY TEMPLATE:
{{MR_BODY_TEMPLATE}}

JIRA TICKET:
{{JIRA_CONTENT}}

BRANCH DIFFS:
{{BRANCH_DIFFS}}

## Output format

See format requirement at top of this prompt.

For REQUIRED_RESOURCES, list which resources to download:

<!-- REQUIRED_RESOURCES -->
{"jira_tickets": ["PROJECTNAME-1234"], "gitlab_mrs": ["12345"], "attachments": ["debug.log"]}
<!-- /REQUIRED_RESOURCES -->
