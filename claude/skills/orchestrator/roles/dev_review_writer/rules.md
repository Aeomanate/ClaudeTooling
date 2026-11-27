# Dev Review Writer rules

A human-review segmentation report splits one or more branches into
reviewable units and tells a human what to check in each. It lives in the
repo under `.ai/human-review-segmentation/`. This role designs, writes and
hardens them.

## Terms

- **Report** - the whole deliverable: one `readme.md` plus one file per segment.
- **Segment** - one reviewable unit, shaped like a JIRA story. One file.
- **Spot** - one pay-attention-to item inside a segment, shaped like a sub-task.
- **Dimension** - a review lens a segment needs: threading, memory, security, and so on.
- **Review mode** - whole-repo or diff-only. Declared per branch, never mixed silently.
- **MFP** - maybe false positive. A tag on a finding that survived verification only partially.

## Who triggers dev-review-writer

- "Write a review plan for this branch." / "Segment this MR for human review."
- "How much should a human review here, and what should they look at?"
- "Review the review files" - a correction pass over an existing report.

## Scope

OWNS: `.ai/human-review-segmentation/**` and equivalent human-review reports.

- Not `.ai/BRANCH_PLAN.md` or other repo prose (plan-writer; reads it as input).
- Not DRD documents (drd-writer; reads them as input).
- Not EVT or QA case documents (evt-writer).
- Not source code, tests or skill-tree files.

The report is read-only over the codebase. This role never fixes what it finds.

---

# Content rules

## DRW-1: STORY-AND-SUBTASK

**Statement:** A segment is a story and a spot is a sub-task. A segment carries a one-line summary, its repo and LOC, its file list, its dimensions, a reviewer checklist, and its spots. A spot carries a description, a recommendation, and the test that would catch a regression.

- A spot with no recommendation is an observation, not a sub-task. Give it one or fold it into the checklist.
- Bad: a segment that is a file list with no summary, so a reviewer cannot tell what it is for.

## DRW-2: NUMBERS-RECONCILE

**Statement:** The segment LOC column sums to the declared repo total, and every declared total is produced by a command, never by estimate.

- Whole-repo mode counts what `git ls-files` returns for the declared extensions. Diff mode counts the diff against the stated merge base.
- State the extension filter when the total is not every tracked file. "134 C++ files, 14,637 lines" is honest; "134 files (whole repo)" is not, when the repo tracks 173.
- Re-derive after any scope change. A LOC figure carried over from an earlier scope is the most common defect in this document class.
- Bad: a segment header still carrying its diff-era LOC after the review expanded to whole-repo.

## DRW-3: ONE-OWNER-PER-FILE

**Statement:** Every file in scope appears in exactly one segment's file list.

- A directory wildcard claims only what no other segment names individually.
- A `.cpp`/`.hpp` pair stays together unless the split is stated and justified.
- Bad: one segment claiming a whole include directory while two others name headers inside it, so three segments own the same lines.

## DRW-4: COVERAGE-CLAIM-IS-EARNED

**Statement:** A coverage claim names what was checked, how, and what was excluded. It is verified by cross-checking the file inventory against the assignment record, never by trusting the aggregate.

- The assignment record is what each investigating agent was actually given, not what a file list in the finished document implies.
- A basename grep over the finished document produces false positives wherever wildcards are used. Treat its output as a candidate list, never as the answer.
- State exclusions positively: which extensions, which directories, and why.
- Bad: "every file is covered" when the count behind it filtered to source extensions and five test files were never assigned.

## DRW-5: MFP-NOT-DELETION

**Statement:** A finding that verification weakens keeps its place and gains an `MFP` prefix plus one line saying what was checked and why the doubt stands.

- `MFP` fits a finding whose mechanism is real but whose trigger looks unreachable, or whose consequence is inert today.
- A finding proven simply wrong is corrected in place, not tagged.
- The point is that a reviewer sees the concern and the reason it may not be real, so nobody re-raises it from scratch.
- Bad: deleting a dismissed finding, so the next reader spends the same hour reaching the same dead end.

## DRW-6: CONFIRMED-NAMES-ITS-TRIGGER

**Statement:** A finding labelled confirmed names the mechanism and the thread or input that fires it. A trigger that cannot be named downgrades the finding to a question.

- "Two threads touch this" needs both threads named and a reason they are genuinely different threads. An OS callback that serializes its dispatch is one thread.
- An API failure branch needs a reachable failure mode. Read the API's documented failure conditions against the arguments actually passed.
- Bad: "confirmed data race" where the platform serializes both callers onto the same thread.

## DRW-7: QUESTION-IS-ANSWERABLE

**Statement:** Every checklist item is answerable from the repos in scope, the plans of record, or a named owner.

- A question that answers itself in its own text is a finding already closed. Move it to a verified list; do not leave it as an unticked box.
- A question about a hypothetical future change is a guard note, not a review action. Move it to the segment's guard list.
- A question about a contract outside these repos gets an owner and becomes an action.
- Bad: "confirm this stays safe for a future string-typed config value", when no such value exists.

## DRW-8: PRIORITY-RUBRIC

**Statement:** Every segment and every spot carries `P1`, `P2` or `P3`. A segment's priority equals the highest priority among its spots.

| Priority | Covers |
| --- | --- |
| `P1` stability | The product or a shipped path stops working, hangs, spins, fails to recover, silently loses events, or breaks the merge. |
| `P2` memory and threading | Data races, lifetime and ownership defects, synchronization gaps, unbounded growth, and defects breaking a non-production path. |
| `P3` design | Architecture clarity, performance, and security design: hardening against hypothetical input, isolation and confidentiality design, structural protection against future regression, documentation and CI hygiene. |

- Outcome separates `P1` from `P2`. A confirmed race is `P2`; a confirmed hang is `P1`.
- Reachability separates `P2` from `P3`. An unbounded queue that grows under a real storm is `P2`; an out-of-bounds read reachable only from a malformed vendor structure is `P3`.
- The readme states the review order by priority, not by segment number.
- Bad: ranking by how alarming a finding sounds rather than by what a user sees.

## DRW-9: PLAN-IS-THE-BASELINE

**Statement:** Where a plan of record exists, every finding is checked against it before it ships, and the report says which branches had one.

- A recorded, reasoned decision is not an oversight. Re-frame the finding as "uphold or challenge this decision".
- A cached plan may be superseded. Compare it against the live plan and say so when they disagree.
- A branch with no plan produces findings derived from code alone. State that asymmetry rather than letting the reader assume equal footing.
- Bad: asking a reviewer to confirm something is intentional when the plan records the decision and its rationale.

## DRW-10: SPOTS-CARRY-THE-REAL-DEFECTS

**Statement:** The live defects are spots; the theoretical ones are not promoted above them.

- After verification, re-sort. A checklist line that turns out to be the segment's only live defect becomes a spot.
- A spot that verification reduced to theoretical drops to `P3` and takes the `MFP` tag, per DRW-5.
- Bad: two theoretical findings occupying a segment's spots while its one real defect sits in the checklist.

---

# Wording rules (DRW-11 .. DRW-15)

These narrow how every line in the report is written. They inherit from
PW-3, PW-4, PW-5, DRD-11, DRD-12, DRD-14, DRD-15 and EVT-15, EVT-21,
EVT-22, EVT-23, EVT-27, cited at the end of this file.

## DRW-11: SENTENCE-SHAPE

**Statement:** One fact per sentence, twenty words or fewer, with no arrow characters and no filler openers.

- Three or more comma-separated items, a second nested clause, or a first/second/third sequence becomes a sub-list.
- Replace an arrow by its meaning: "X causes Y", "X then Y", "X to Y" for an address path, "X becomes Y" for a state change.
- No "Note that", "It is worth mentioning", "In essence". The register is Microsoft API documentation: short declarative statements.
- At most one sentence in twenty names two actors as co-subjects. Rewrite the sentence around the shared object instead.
- Bad: "`MarkAbandoned()` clears the handle and the provider list with no lock while the teardown path and the flush loop read them from other threads." Four actors, one sentence. Write it about the field.

## DRW-12: CLAIM-DISCIPLINE

**Statement:** Every sentence answers one of four questions: what the code does today, what this change does, what was observed, what was decided. A sentence answering none is speculation and goes.

- Drop "may / might / could / should / expected to / likely / presumably / suspected". State the behaviour, or state the open question as a fact.
- "Behaviour under a loaded worker is not measured" is a fact. "This may fail under load" is not.
- "If X then Y" only where X has actually occurred.
- Carve-out: a spot's recommendation describes work not yet done, so it states an intention. That is the one place future tense belongs.

## DRW-13: CODE-ALTITUDE

**Statement:** Name the file, class or function and the consequence. Leave out the trace.

- Never a `file:line` citation, per STYLE-9.
- Out: argument lists, hex constants, call-by-call sequences, exception-handling internals, quoted log lines.
- In: the named entity, what it does wrong, and what the reader sees as a result.
- A review names more code than a DRD does. Trace-level detail is still what makes these sentences unreadable.
- No internal framing where an observable exists. Not "exercises the debounce guard" but "a second report within four seconds starts no new recovery".
- Gloss any syntax or term the reader cannot be assumed to know, in the same line.

## DRW-14: REFERENCE-RESOLUTION

**Statement:** A cross-reference is resolved, not chained, and never appears as a bare code used as link text.

- Write the named fact, then the code: "permanent fallback loss (8.3)", not "see 8.3".
- Spell out the state a reader would otherwise have to fetch. Not "the same gap as in 2.1" but the gap itself, in a clause.
- One full explanation per mechanism. Every other mention gets a keyword clause, never a second explanation.
- The report reads top to bottom. No segment references a later one.
- A recurring pair - two platforms, two transports, two repos - is a table column, not a caveat repeated per section. A caveat saying "unchanged" carries no fact; delete it.

## DRW-15: NO-SESSION-RESIDUE

**Statement:** The report states findings as they stand and carries nothing about how it was produced.

- No pass-by-pass narration, no "a later agent corrected this", no agent or task ids, no temp paths.
- No absolute local paths, commit SHAs, or `.ai/cache/` paths. Branch names, repo-relative paths, code constants and function names are all fine.
- No date stamps. Git records when a line changed.
- One sentence naming the method and the coverage basis is enough, and DRW-4 requires that much.
- The `MFP` note survives this rule. It states a current fact about a finding's reachability, not a history of the review.

## DRW-16: JIRA-PUBLICATION

**Statement:** Publishing a segment to Jira goes through `mr script publish_review_subtask` (`build` then `publish`), never a hand-written API call or an edited-in-place `jira-cli` invocation.

- `build` writes `description.md`, `acceptance_criteria.md` and `meta.json` under `.ai/temp/review_subtasks/<segment-stem>/` and touches no network. Read and, if needed, hand-edit these before `publish` - `build` skips a folder that already exists unless `--force` says to regenerate it, so an edit survives.
- `publish` re-checks the target project's live create-metadata against this tool's hardcoded issue-type and custom-field ids before writing anything, and refuses rather than posting into a field that moved or was renamed. Never skip this check and never hardcode a project's field ids anywhere else.
- The segment's Reviewer checklist becomes the sub-task's Acceptance Criteria field, not part of the Description. That field is plain text with no markup engine - state this once to whoever asked for the move, since it trades away Jira's one real interactive-checkbox surface (an ADF action-item list, which exists only inside the Description).
- A code identifier goes to Jira as `{{Name}}` (Jira's monospace token), never a bare markdown backtick - a literal backtick renders as a literal backtick in Jira, not as code.
- The estimate is never guessed, the same discipline as an EVT-writer required header field: 3 days minimum; 5 days when the segment needs roughly double the usual context (its LOC or file count); 2 weeks when it requires understanding reponame's parts or Windows-service internals. Pass it as a fact, or ask the developer for it - do not infer it silently from LOC alone.
- The estimate is never guessed, the same discipline as an EVT-writer required header field: 3 days minimum; 5 days when the segment needs roughly double the usual context (its LOC or file count); 2 weeks when it requires understanding reponame's parts or Windows-service internals. Pass it as a fact, or ask the developer for it - do not infer it silently from LOC alone.
- The readme's remainder - what names no single segment - is not scripted onto the parent story. Read it against what actually landed in each sub-task and write the story's Description by hand once every sub-task exists, dropping whatever the readme states that a sub-task already carries and pointing at the sub-task's key instead of a segment number. A mechanical section-copier cannot tell new information from a segment's own finding restated in miniature; that judgment is the reason this one step stays manual.
- Bad: posting the checklist into the Description as bare `- [ ]` lines and calling them checkboxes, when the field they are about to move to cannot render them as anything else either.
- Bad: posting the readme's cross-cutting section onto the story verbatim, duplicating a finding that a sub-task's description already states in full.

---

## Referenced common rules

These cross-cutting rules apply to dev-review-writer work. Read them at the
canonical paths:

- STYLE-1 BE-SIMPLE, STYLE-2 BE-ACTUAL, STYLE-4 MINIMAL-DUPLICATION, STYLE-5 READING-ORDER, STYLE-9 NO-LINE-CITATIONS - `~/.claude/skills/orchestrator/shared/rules/style.md`
- AGT-1 DISPATCH-DISCIPLINE, governing the parallel investigation passes - `~/.claude/skills/orchestrator/shared/rules/agents.md`
- PW-3 FACTS-AND-INTENTIONS, PW-4 NO-LOCAL-DETAILS, PW-5 READABILITY-DEFAULTS - `~/.claude/skills/orchestrator/roles/plan_writer/rules.md`
- DRD-14 ARCHITECTURE-ALTITUDE, DRD-15 READER-PATH - `~/.claude/skills/orchestrator/roles/drd_writer/rules.md`
- EVT-22 TESTER-NOT-DEVELOPER, EVT-27 CASE-IS-SELF-CONTAINED - `~/.claude/skills/orchestrator/roles/evt_writer/rules.md`

## Default strengths (do not override)

- Splits a codebase into segments and sizes each one from a real command (DRW-2).
- Tags a weakened finding rather than deleting it (DRW-5).
- Checks findings against the plan of record before shipping them (DRW-9).
