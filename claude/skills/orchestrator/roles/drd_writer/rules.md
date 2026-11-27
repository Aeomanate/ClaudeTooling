# DRD Role Rules

Rules governing the `drd_writer` role - DRD writing and maintenance.

This file is the single home for every DRD rule and limit. `workflow.md`
holds the phases and steps only, and links here for rules.

---

## DRD-2: NO-COMMITS-WHILE-WRITING

**Statement:** `git log` shows no commit touching the DRD file before developer sign-off - the writing session only writes and polishes.
- Bad: committing DRD checkpoints "for safety". The file on disk is the safety; a commit is for the final reviewed artifact.

---

## DRD-4: CODE-IMPROVEMENTS-LOG

**Statement:** Every imperfection found while re-reading the codebase gets an entry in `.ai/CODE-IMPROVEMENTS.md` - problem, context, possible solutions, and whether it is an architecture fix rather than an immediate one.
- An in-code fix made to suppress a later reviewer warning is allowed, uncommitted, and only alongside its matching entry. DRD-2's no-commit rule covers it.
- Something structural - moving modules, new classes, a big blind spot - is noted in the DRD itself to suppress the warning.
- Bad: silently fixing what you find, leaving the developer no audit trail.

---

## DRD-6: INVESTIGATION-RULES

**Statement:** Every API or platform behaviour stated in the DRD carries a citation from this session - a fetched vendor doc page or a codebase reference - never training-data memory, since vendor behaviour mutates between releases faster than that memory stays accurate.
- Same rule as coder's CODER-5 API-DOCS-FIRST.
- Bad: asserting "Win32 API X behaves like Y" without grepping the codebase or fetching the docs first.

---

## DRD-7: REVIEW-FEEDBACKS-HUMANS-ONLY

**Statement:** The "Review Feedbacks" section stays empty until the developer fills it - it carries feedback from independent human reviewers only, and the writer adds nothing there absent a direct instruction.
- Bad: treating the orchestrator's own reviewer agent as "the reviewer" and writing its findings into that table.

---

## DRD-8: NO-AUTONOMOUS-DISPOSITION

**Statement:** Each fake-review iteration ends with a disposition table - finding, proposed action (fix / defer / escalate / accept), rationale - sent to the developer via SendMessage, and no edit tied to it lands before an explicit approval message arrives.
- Approved dispositions are applied, then the fake-reviewer is re-dispatched for the next iteration.
- Bad: applying all findings immediately because they look editorial. The developer may hold context that changes the disposition.

---

## DRD-9: GROUND-TRUTH-BEFORE-TRIAGE

**Statement:** A finding claiming a code bug - deadlock, leak, race, resource semantic - gets its severity only after the cited file has been read in this session; "plausible from the DRD description alone" is not sufficient.
- The file confirming the bug means BLOCKER or MAJOR per impact; the file refuting it means NIT, or closure with a doc-only citation noting the DRD's description was imprecise.
- Applies to every code-ground finding in Phase B of a fake-review pass.
- Bad: assigning severity to a threading finding on the assumption that the DRD's description is an accurate proxy for the code.

---

## DRD-10: HIGH-LEVEL-ARCHITECTURE

**Statement:** The DRD body carries no language-syntax rules, no log lines, no large code dumps, and no `file:line` citations.
- Line citations are governed by STYLE-9 NO-LINE-CITATIONS, which covers every human-facing document, not just DRDs.
- Bad: citing `src/foo.cpp:142` to point at a function instead of naming the function.

---

## DRD-11: MINIMAL-DUPLICATION

**Statement:** Each mechanism has exactly one full explanation, and no scope caveat opens several sibling subsections - that shape means the document is structured wrong, per DRD-15.
- Follows STYLE-4 MINIMAL-DUPLICATION.
- Bad: replacing a one-clause repeated fact with a link to the canonical section, forcing a jump for something that fits in a few words.

---

## DRD-12: LIKE-A-STORY

**Statement:** Read top to bottom, no section references a later one, and each cross-cutting concern - security first among them - appears only inside its owning section.
- Follows STYLE-5 READING-ORDER.
- Bad: describing security constraints inside the glossary or a component section.

---

## DRD-14: ARCHITECTURE-ALTITUDE

**Statement:** The DRD states intent, boundaries, decisions and diagrams; implementation mechanics are delegated to the MRs, including MRs not yet created.

* PLACE in the DRD: the problem and requirements, the chosen architecture
  and the options weighed, component/process/deployment structure, the
  security and permission model (with a permissions table when relevant),
  cross-product and packaging boundaries, diagrams, and architecturally
  meaningful numbers (a flush cadence, a session cap, protocol or event
  ids, provider names, the API names in a permission table).
* DELEGATE to the MR: exact variable/member/field names, hex constants,
  function-argument lists, CAS/lock/exception-handling internals, log
  lines, call-by-call sequences, and operational decisions the MR owns
  (legacy-path retention duration, removal/rollout tracking,
  telemetry-productionization timelines and owners). Anything derivable
  from git or the code stays out too.

- GLOSSARY holds actual entities and terms only - services, components, packages, concepts. No mechanism or code-level entries.
- OPEN QUESTIONS holds architecture-level unknowns and decisions only. Never names, confirmations, or implementation details.
- A draft or unexecuted session or branch plan is input, not truth: state architectural intent from the user's direction rather than copying a draft's mechanism in as settled.
- The cleanup pass enforcing this altitude across the whole document is workflow Phase 7, Step 7.1.
- Bad: listing exact struct field names or a call-by-call trace in the DRD body instead of in the owning MR.

---

## DRD-15: READER-PATH

**Statement:** The document reads once, top to bottom, for a reviewer who will not follow links, and passes the Hard limits table below. Follows STYLE-1, STYLE-3, STYLE-4 and STYLE-5 for sentence shape, fact repetition and link text.

* CROSS-CUTTING SECTIONS ARE FLAT OR ABSENT. Never one subsection per
  component. Security earns length from the count of new external
  interfaces, not the count of components.
* ONE AXIS PER ID SCHEME. Considered Options answers one question and
  marks one option chosen. Two questions mean two schemes or two
  sections.
* NARROW BY DEFAULT. Keep the document as narrow as possible without
  losing meaningful detail, diagrams, or code examples tied to the main
  topic. Negotiate cuts with the developer.

- This rule is prose guidance for the limits below, not a second copy of the numbers. The audit enforcing it is workflow Phase 3, Step 3.3.
- Bad: keeping a tangential example because it took effort to write, not because a reviewer needs it.
- Bad: opening three sibling subsections with the same bolded "this differs on Windows vs macOS" caveat instead of one comparison table.

---

## Other DRDs summarized style

How human-written DRDs read, stated as limits and checks. Apply while drafting, not
as a cleanup pass - every item here is cheaper to satisfy on the first write than to
retrofit.

### Hard limits

| Metric | Limit |
|---|---|
| Internal `](#...)` links | ≤2 per 100 lines |
| `##` headings | ≤16 |
| `###` headings | ≤14 |
| TOC entries | ≤13, or no TOC |
| Bare codes as link text | 0 |
| `<a id>` inside heading text | 0 |
| Bolded label acting as a heading | 0 |
| Variant label as a paragraph opener | 0 |
| Largest `#` section | ≤25% of the document |
| Sentences naming two actors as co-subjects | ≤5% |

### Repeat the fact, never the explanation

* A short fact is cheaper inlined than linked. State it where it is needed.
* A link costs the reader a stop, a jump, and a return. Spend it only on a full
  table, a diagram, or a multi-paragraph mechanism.
* The full explanation lives at one canonical home. Every other site gets a
  keyword clause, not a link and not a second explanation.
* Never link with a bare code as the visible text. `[F8](#f8)` tells the reader
  nothing, so the jump is forced. Write the named fact, then the code in plain
  text: "the source resolver (F8)".

### Variants are columns, not caveats

Applies to any pair the document carries throughout - two phases, two platforms,
two products, before and after.

* The concern is the grammatical subject. The variant is a table column.
* A subsection must not open with a bolded variant caveat. One comparison table at
  the top of the section replaces every per-subsection restatement.
* A caveat that says "unchanged" or "does not apply" carries no fact. Delete it.
* Variant labels belong in headings, captions, and table cells only.
* Where one variant can be demoted, make the other the sole subject and quarantine
  the first into one section. Where they are true peers, keep the concern as
  subject and fold the pair inside as a column.

### Sections

* Cross-cutting sections are flat. Never one subsection per component.
* A security section is sized by new external interfaces, not by component count.
* Merge any subsection under about ten lines into a list entry of its parent.
* Diagrams sit next to the prose they illustrate. A diagram gallery detached from
  its explanation forces the cross-referencing reviewers complain about.
* Absence is stated once. "Not applicable", or delete the heading.

### Options

* One decision axis per option group. Readability collapses when one flat ID
  scheme spans several questions, not when the option count is high.
* Group options under a heading per axis. Each axis names the question it answers
  and marks exactly one chosen option.
* Only the rejected option is labelled rejected. The chosen design is presented as
  fact.

### Text

* Every actor used as a subject is defined in the Glossary once.
* A bolded label is a caption for a table or a diagram. Anywhere else, promote it
  to a real heading or fold it into the sentence.
* Anchors go on their own line above a clean heading, never inside heading text.
* No sentence describes the document's own organisation. Headings carry that.
* Sentence length is not a defect. Do not shorten prose to hit a word count.

### Anchor ids are frozen

Once a DRD has been reviewed, its anchor ids are a public interface. Review
Feedbacks and reviewer notes link into them.

* Change link text freely. Never rename or delete a link target.
* Merging a heading away removes its auto-generated slug. Add an explicit
  `<a id="the-old-slug"></a>` in its place.
* After any restructure, check that every `](#...)` target resolves to either an
  explicit anchor or a surviving heading slug.

## Referenced common rules

- DEL-1 EXECUTION-STRUCTURE, skill-tree editing forbidden for every persistent sub-agent - `~/.claude/skills/orchestrator/rules/delegation.md`
- STYLE-9 NO-LINE-CITATIONS, used by DRD-10 - `~/.claude/skills/orchestrator/shared/rules/style.md`
