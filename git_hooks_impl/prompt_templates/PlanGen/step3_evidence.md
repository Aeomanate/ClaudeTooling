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

# Step 3: Enrich plan with evidence

For each evidence, decide: does this help plan the current task with
higher quality? If yes, add a structured note block to the most relevant
plan section. If no, skip it entirely — no noise.

## How to write evidence notes

Use `> [!note]` ONLY as a heading. Bullets below are plain markdown.
Each note block MUST have 2+ bullets. Single-line observations are
noise — expand with specifics or remove entirely.

> [!note] From !<MR_ID> (<short MR title>)
- Implements <approach> for <feature area> on <platform>
- Partial implementation — no <gap-1>, no <gap-2>
- Be aware of: <known caveat the developer should know>
- Useful for: <how this informs THIS branch's approach>

> [!note] From <TICKET-ID>
- <One-line summary of what the related ticket addresses>
- <How that relates to THIS branch's scope or supersedes/enables it>

**What to write in bullets:**
- What the evidence does, changes, or fixes (concrete facts)
- What's useful for planning THIS task (approaches, patterns, pitfalls)
- Blockers or dependencies that affect THIS task
- Caveats the developer should be aware of

**What NOT to write:**
- Relationship labels only ("is parent of", "relates to") — describe
  relationships ONLY when they're strategic blockers or enablers
- Vague observations ("this ticket exists", "there is related work")
- Noise from tickets that don't help plan the current task
- Don't describe relationships if the evidence content itself is what
  matters — focus on the useful content, not the org chart
- Hedging language in evidence note bullets ("expected", "may need", "should be", "might", "likely") — restate as direct assertions, since evidence notes describe what OTHER work did, not future possibilities. If the evidence source itself is hedged ("may evolve to support X"), quote it explicitly with a "From MR !N:" preface so the hedge belongs to the source, not your characterization.

**Jira tickets:** Describe what the ticket's CONTENT means for our
approach. If a linked bug describes a user scenario our task must
handle, say that. If a sibling task will produce input we depend on,
say that. If the link is just organizational, skip it.

**GitLab MRs:** Describe what the code does, what approach it uses,
whether it succeeded or failed, and what we can learn or reuse.

## Rules

- Do NOT remove existing plan content — only add new information
- Do NOT modify the title (first `# ` heading)
- Place notes in the most relevant plan section (Context, Description,
  Areas of Impact, or Implementation Plan)
- Preserve all existing `> [!note]` blocks from previous steps
- Every `> [!note]` block MUST have 2+ bullets — no single-liners
- **Evidence MRs are OTHER work.** When adding `> [!note]` blocks from evidence, attribute the work TO that evidence — never restate it as THIS branch's deliverable. Use "From MR !N: reusable approach for X" not "Implements X via approach from MR !N". Evidence notes provide background context; the plan body describes ONLY this branch's incremental work.

## Available evidence

{{AVAILABLE_EVIDENCE}}

## Evidence content

{{EVIDENCE_BLOCKS}}

## Input

CURRENT PLAN:
{{PLAN}}

