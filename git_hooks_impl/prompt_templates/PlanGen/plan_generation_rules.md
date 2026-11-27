# Plan section fill rules

Shared between the orchestrator skill and the plan generation prompt.
Edit this file to change how plan sections are filled — both the AI
agent and the developer reference these rules.

## Visible sections (mapped to MR body)

**Context** — Present the problem from the end user's perspective: what
frustrates them today, what's broken or missing, what they're working around.
One paragraph per deliverable. Start each with a bold phrase naming the
user-facing problem, then describe the current experience and what changes.
Preserve exact data points from Jira (numbers, dates, percentages) — don't
paraphrase metrics. Quantify the impact with before/after comparison when
data is available.

**Description** — What the branch delivers in user-facing terms. Use
subsections for distinct features. Suggested structure:
- `### Workflow / lifecycle` — how users interact with the feature
- `### Commands (manual)` — table: | Command | What it does |
- `### Automatic behaviors` — table: | Trigger | Behavior |
  When the branch has no committed implementation yet, retitle the column to "Planned behavior" and use future-tense in row values ("will be created", "is planned to fire").
- `### Interactive dialogs` — GUI elements, user choices, shortcuts
Do NOT put Debugging in Description — it belongs in the hidden section.
Cross-reference related Jira tickets when they share root causes or
dependencies with the current ticket.

**Areas of Impact / Risks** — Two sub-headings:
- `Affected components:` — modules, files, dirs changed; devices/platforms
- `Risks:` — what could go wrong, what QA should watch for

## Hidden sections (below the hidden block marker)

**Success Criteria** — One checkbox per deliverable. Testable, binary pass/fail.

**Verification** — Commands to run + expected output. Include unit test command,
integration test command (if applicable), and manual verification steps.

**Debugging** — Log file paths, direct invocation commands, debug artifacts.

**Architecture** — System diagrams, flow charts, data structures. Use
`<details>` blocks for complex flows. Include `### <subsystem name>` headings
with diagram + explanation. Fill the `Important File Paths` table.
Use real function/class names from the codebase in diagrams — not generic
labels. Call chains should show actual code paths.
Diagrams MUST use plain ASCII only (`+--+`, `|`, `-->`, `v`). Never use
Unicode box-drawing characters — they misalign across fonts and renderers.
Prefer flow diagrams (`A --> B --> C`) over box diagrams.

**Implementation Plan** — Group TODOs by priority using `### P1/P2/P3` headings.
P1 = critical (before merge), P2 = important, P3 = nice-to-have.
All items use `[ ]` — this is a forward-looking TODO list, not a changelog.
Completed work belongs in Decisions Log (interactive sessions only).

**Decisions Log** — Append-only, one line per decision.
Format: `- <domain> - <short summary> - <important details>`
Examples:
- `- Architecture - Shell entry + Python package - matching commit-msg convention`
- `- Cache - checkout=MOVE push=COPY - cache survives restore, self-healing`

**Generation rule:** When generating a plan from scratch, leave Decisions Log
empty (just the section heading). Decisions Log is populated during interactive
AI coding sessions — the generator has no session history to record.

## Title

The first `# ` heading MUST be: `# [TICKET] Jira summary text`
Example: `# [PROJECTNAME-43118] Investigate excessive OAuth2 token refresh traffic`
If the Jira summary is unavailable, derive from the branch name.

## Scope

The plan describes the FEATURE BRANCH work — the product code being
changed. Do not describe the tooling that generates the plan (.git-hooks/,
mr_ai_automation/, Claude skills, Python hook tests).

## Format constraints

- Plan items describe WHAT the system can do, not HOW it was built.
  Bad:  "Add input_data param to run() in utils.py — uses input= ..."
  Good: "Pipe prompts via stdin to bypass Windows 32 767-char limit"
- Never write `<!--` in visible plan text — the parser processes raw text.
- `## Description` and `## Areas of Impact / Risks` sync to MR body on push.
- Verification commands must target the product's test framework (ctest,
  cmake, pytest), not the tooling's unittest suite.
- Important File Paths table must be populated with real paths from context,
  not (TBD) placeholders. If unknown, write "Populate during investigation".
