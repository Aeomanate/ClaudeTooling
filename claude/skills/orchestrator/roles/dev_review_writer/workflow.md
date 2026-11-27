## Dev Review Writer workflow

WORKFLOW NAME: review-segmentation

Builds a human-review segmentation report, then hardens it. Phases 2 to 4
create the review list. Phases 5 to 8 each close a class of defect that a
freshly built list carries by default, and none of them is optional: every
one of them overturned a shipped claim the first time it was run.

This file holds phases and steps only. Every rule it cites lives in the
[dev-review-writer rules](./rules.md).

Each investigation phase dispatches parallel read-only agents under AGT-1.
The role never dispatches an execution role.

---

### Phase 1: SCOPE

#### Step 1.1: Declare the branches and the review mode
Name every branch and MR in scope, including dependency MRs and submodules
on their own branches. A submodule with its own feature branch is a separate
reviewable MR, not vendored code.

Per branch, choose whole-repo or diff-only, and say why. A fix touching
lifecycle code throughout a library earns whole-repo; an additive
integration on top of a large unrelated codebase earns diff-only.

#### Step 1.2: Produce the inventory by command
Run `git ls-files` for whole-repo branches and `git diff --shortstat`
against the stated merge base for diff-only branches. Record file counts and
line counts per branch, and the extension filter used (DRW-2).

#### Step 1.3: Read the plans of record
Read `.ai/BRANCH_PLAN.md` for every branch that has one, plus any cached
plan for a dependency branch. Note which branches have none (DRW-9).

**Completion checklist:**
- [ ] Every branch, MR and submodule in scope named, with its review mode
- [ ] File and line counts produced by command, extension filter stated
- [ ] Plans of record read; branches without one recorded

---

### Phase 2: SURVEY (pass 1 of the list)

#### Step 2.1: Split the scope across parallel agents
Dispatch investigation agents over disjoint slices of the inventory. Give
each agent an explicit file list, never "the rest of this directory" - an
unbounded instruction is how files go unassigned, and Phase 5 exists because
of it.

Keep the assignment record. Phase 5 checks the inventory against it.

#### Step 2.2: Consolidate into segments
Merge the raw sub-segments the agents return into coherent segments. Assign
every file to exactly one segment (DRW-3). Give each segment its summary,
dimensions, checklist and initial spots (DRW-1).

**Completion checklist:**
- [ ] Every agent given an explicit file list, no wildcard instructions
- [ ] Assignment record kept for Phase 5
- [ ] Every inventory file assigned to exactly one segment

---

### Phase 3: DEEP DIG (pass 2 of the list)

#### Step 3.1: One agent per segment
Re-read each segment's code looking for what the survey missed, and verify
or refute the survey's own claims against the real call chains.

A deep-dig agent that refutes a survey claim is doing its job. Record the
refutation rather than keeping both.

**Completion checklist:**
- [ ] One agent per segment, each reporting new spots and verdicts on survey claims
- [ ] Refuted survey claims removed or corrected, not carried alongside

---

### Phase 4: RECOMMENDATIONS (pass 3 of the list)

#### Step 4.1: One agent per high-priority spot
For each spot, generate fix options, a recommended option with its
reasoning, and the test coverage that would verify it.

A recommendation that proposes machinery disproportionate to the defect is
rejected here, not shipped for the reviewer to filter.

**Completion checklist:**
- [ ] Every spot carries a recommendation and a test (DRW-1)
- [ ] Disproportionate recommendations replaced with the smaller fix

---

### Phase 5: COVERAGE AUDIT

Triggered by the question "are you sure you scanned the whole repo?". Run it
before that question is asked.

#### Step 5.1: Cross-check the inventory against the assignment record
Compare Phase 1's inventory against Phase 2's assignment record, not against
the finished document. A basename grep over the document produces false
positives wherever a wildcard was used (DRW-4).

#### Step 5.2: Close the gap
Dispatch one agent over the unassigned files. Fold its findings into the
segments that own those files.

#### Step 5.3: Restate the coverage claim
Say what was checked, how, and what was excluded, with the extension filter
named (DRW-4).

**Completion checklist:**
- [ ] Inventory cross-checked against the assignment record, not the document
- [ ] Every unassigned file read and folded into a segment
- [ ] Coverage claim names its method and its exclusions

---

### Phase 6: PLAN RECONCILIATION

Triggered by "read the branch plans and find gaps, inconsistencies and
duplication".

#### Step 6.1: Findings against the plans
For every branch with a plan, check each finding against it. A recorded
decision becomes "uphold or challenge", never "confirm this was
intentional" (DRW-9). Flag a cached plan that the live plan supersedes.

#### Step 6.2: Plan items with no finding
List every open item, risk, deferred item and decision in a plan that is
material to a reviewer and appears in no segment. Anything a plan parks "for
review-stage discussion" is an instruction to this report.

#### Step 6.3: Duplication and ownership
Find the same defect stated in several segments, and the same topic split
across several. Give each one owner and a keyword clause elsewhere (DRW-14).
A defect crossing a repo boundary gets linked in merge order.

**Completion checklist:**
- [ ] Every finding checked against its branch plan; superseded caches flagged
- [ ] Every material plan item either covered or listed as a gap
- [ ] Each duplicated topic given a single owner

---

### Phase 7: ADVERSARIAL VERIFICATION

Triggered by "eliminate the possible false positives". The agents dispatched
here are told to falsify, not to confirm.

#### Step 7.1: Falsify every confirmed claim
One verdict per claim: CONFIRMED, OVERSTATED, or FALSE POSITIVE. A verdict
needs the mechanism, the reachable trigger, and the thread or input that
fires it (DRW-6).

Ask the reachability question explicitly for each claim. Can this API
actually fail with the arguments passed? Does this value survive the process
boundary? Does anything subscribe to this route? Do these two callers reach
the code on genuinely different threads?

#### Step 7.2: Apply the verdicts
CONFIRMED keeps its wording. OVERSTATED is narrowed to the half that holds.
FALSE POSITIVE takes the `MFP` tag and stays (DRW-5).

#### Step 7.3: Promote what verification uncovered
A verification pass returns real defects that the theoretical ones were
standing in front of. Promote them to spots and re-sort the segment (DRW-10).

#### Step 7.4: Sweep the non-questions
Move self-answering checklist items to a verified list, and
future-hypothetical items to a guard list (DRW-7).

**Completion checklist:**
- [ ] Every confirmed claim carries a verdict with its mechanism
- [ ] Overstated claims narrowed, false positives tagged `MFP`, none deleted
- [ ] Newly uncovered defects promoted to spots
- [ ] Checklists hold only answerable questions

---

### Phase 8: PRIORITIZATION

Triggered by "give each story and sub-task a priority".

#### Step 8.1: Rank every spot, then every segment
Apply the DRW-8 rubric to each spot. A segment takes the highest priority
among its spots.

Priorities come after Phase 7, never before. A finding that verification
narrowed usually drops a level, and one it uncovered may outrank everything
already in its segment.

#### Step 8.2: State the review order
The readme leads with the review order by priority and a `P1`-only list.

**Completion checklist:**
- [ ] Every segment and spot carries a priority
- [ ] Each segment's priority equals its highest spot
- [ ] Review order and `P1` list published in the readme

---

### Phase 9: PUBLISH

#### Step 9.1: Verdict scope
Draw a merge-readiness verdict only where the developer asked for one, and
name which findings are blockers rather than follow-ups. Absent that
instruction, the report states findings and priorities and stops.

#### Step 9.2: Wording pass
Apply DRW-11 to DRW-15 across every line: sentence shape, claim discipline,
code altitude, resolved references, no session residue.

#### Step 9.3: Final checks
- Segment LOC sums to the declared total per branch (DRW-2).
- Every in-scope file appears in exactly one segment (DRW-3).
- Every segment header and spot heading carries a priority.
- The readme's `P1` list matches the spots marked `P1`.
- No `file:line` citation anywhere.

**Completion checklist:**
- [ ] Verdict drawn only where requested
- [ ] Wording rules applied across every rewritten line
- [ ] All five final checks pass

---

### Phase 10: JIRA PUBLICATION

Triggered by "publish each segment as a sub-task" against a named parent
story. Optional - a report can ship without this phase.

#### Step 10.1: Pilot one segment before scaling to the rest
Build and publish exactly one segment first. Report the intermediate
description before it goes out, so the developer can check format and field
placement while the cost of a mistake is one sub-task, not ten. Jira gives
this role no way to delete or move a sub-task once created (AGT-1 tool
grant), so every publish is effectively one-way - the pilot exists to catch
mapping mistakes before they are irreversible.

#### Step 10.2: Build, then publish, each segment
Run `mr script publish_review_subtask build <segment-file> --parent KEY
--estimate 3d|5d|2w [--assignee EMAIL]`, then `mr script
publish_review_subtask publish <segment-file>`. Build writes the local
artifacts under `.ai/temp/review_subtasks/<segment-stem>/` and touches no
network; publish re-reads them - including any hand-edit - re-checks the
target project's Jira configuration, then creates the sub-task or, if
`meta.json` already carries a `jira_key` from an earlier run, updates it in
place (DRW-16).

Estimate per DRW-16's rubric, never guessed. Assignee only if the developer
named one. Once the pilot is confirmed, the rest of the segments follow the
same build-then-publish step - there is no separate bulk action.

#### Step 10.3: Write the parent story's description by hand
Once every segment has a sub-task key, read the readme's remainder - what
names no single segment: scope table, merge order, priority rubric,
cross-cutting items, the source-stopped-path (or equivalent) call chain, the
verified-no-action list, any merge-readiness verdict - against what actually
landed in each sub-task's own description. Do not add a table or list of the
sub-tasks themselves (keys, priorities, estimates, a "review in this order"
list): Jira already shows every sub-task under its parent story, so that
section only duplicates the platform's own UI and goes stale the moment a
sub-task changes. Some of it duplicates a segment
almost verbatim (a cross-cutting item that already names its owning segment,
a P1 highlights list that is really a compressed index of spots already
written out in full); that duplication is not carried over; a segment
reference becomes the sub-task's key instead of a segment number, since the
key is what the reader can click. This judgment is why the step is done by
hand, not scripted: a mechanical section-copier cannot tell "this table row
is new information" from "this table row restates sub-task PROJECTNAME-54970 in
miniature."

#### Step 10.4: Sweep the draft before publishing
Before the first write, re-verify every claim in the draft that names a
fact outside the segment sub-tasks themselves - a commit, a count, a file -
against the source, not against the readme's own wording. A readme claim
like "two commits still carry a dirty marker" names no commit; confirm it
by command (`git log`, `git diff --shortstat`) before it goes to Jira as
fact, and cite what the command found (hash and subject) rather than
repeating the readme's adjective.

Then sweep the draft for two shapes of inconsistency it is prone to:
- A merge-readiness claim living outside the merge-readiness section. A
  cross-cutting item stating "the pin is not releasable" and a
  merge-readiness blocker stating "the Conan pin is a testing-channel
  prerelease" are one finding said twice - fold the cross-cutting version
  into the blocker it supports instead of letting the same claim stand in
  two places with two different levels of evidence.
- A table or list repeating structure the platform already shows. Jira's
  own UI lists every sub-task under its story; a hand-built index of the
  same sub-tasks is not extra context, it is a second, driftable copy of
  something Jira keeps live for free - cut it (this is why the segment
  index table this step used to include is gone).

Publish only after this pass, not before it.

#### Step 10.5: Publish the story description
Write the swept result directly as the parent story's Description field -
it replaces the story's placeholder text, it is not a comment, and it is
written once, after every segment sub-task exists, never before and never
per-segment. Convert markdown tables to Jira's `||header||` / `|cell|`
syntax and code spans to `{{code}}` by hand, the same conversions DRW-16
applies to a segment. Read the field back afterward and confirm the tables
came through as real ADF `table` nodes, not flattened prose.

#### Step 10.6: Resolve format feedback by updating, not recreating
A format correction on a sub-task (wrong field, wrong markup, missing
assignee) is an edit to the existing artifacts followed by another
`publish`, which updates the same ticket. A format correction on the parent
story's description is a re-edit and a second direct write to the same
field. Never create a second sub-task, or post a competing comment, to fix
a first mistake.

**Completion checklist:**
- [ ] One segment published and confirmed correct before the rest are queued
- [ ] Every segment built before it is published, artifacts reviewed
- [ ] Estimate set per DRW-16's rubric on every sub-task, never guessed
- [ ] Parent story's description hand-written from the readme's remainder, checked against every sub-task for duplication, and written only after all sub-tasks exist
- [ ] Every fact the readme stated but did not source (a count, "some commits") re-verified by command before publishing
- [ ] No merge-readiness claim left stranded outside the merge-readiness section
- [ ] No table or list reproducing structure Jira's own UI already shows
- [ ] Every format correction applied as an update to the same ticket or field, never a duplicate
