# Style Rules

Answering and writing style. These bind every reply and every written
surface, whatever the task. Unlike the other rule files, this one is never
topic-conditional - there is no request for which it does not apply.

Read this file first. `SKILL.md` carries a one-line digest of each rule;
the full statements live here.

## STYLE-1: BE-SIMPLE

**Statement:** Short sentences, strict technical wording, one fact each. No literature-like style in any answer or document.
- No hedging and no filler openers: "Note that...", "It is worth mentioning...", "In essence...".
- Plain words over sophisticated ones. Bad: "cardinality", "load-bearing", metaphors from non-technical text. Good: "important", "significant", a plain technical noun.
- No semicolons in prose. No arrows in prose - they stay legitimate in diagrams and code notation.
- No em dashes (U+2014) in prose; use a comma, period or colon. `claude/hooks/check_em_dash.py` replaces each with `-` after every Edit/Write on `.cpp`/`.hpp`/`.py`/`.md` and reports the lines. It can touch a line outside the edit's scope; never revert a hook-made `-`, in scope or out.
- Split long multi-clause sentences into short declarative statements.
- One grammatical subject per passage. Every other actor is a dependency, introduced once. Where neither of two actors can be demoted, the concern becomes the subject and the pair folds into one bullet.
- In chat, chain short sentences: the action, then the fact about it, then the next action. Good: "I do X. X is bad." Bad: "I did X, which turned out bad because of Y, so I need your help deciding Q."
- A prose paragraph carrying 2+ distinct claims or 2+ sequential steps becomes a list. So does a sentence with 3+ comma-separated items, more than one nested clause, or a "first / second / third" sequence.
- Use blocks and headers so the text is scannable. Prefer short lines.
- A phase, platform or before/after label belongs in a heading, caption or table cell - never in a sentence, never as a bolded caveat opening a subsection. Declare the variant list once.
- Prefer a table over prose for a comparison, and a pulled-out commented code example over code embedded in a sentence.
- Assumptions and uncertainty go in their own paragraph or block, away from the main text.
- Dense prose belongs only in Risks, Discussion, Summary and Context sections. Facts and design points stay list-like.
- Bad: a semicolon-stacked or arrow-chained paragraph because "it reads like one thought" - multiple claims are multiple thoughts and belong in a list.

---

## STYLE-2: BE-ACTUAL

**Statement:** No history of any kind - narratives, comments, codes or checks - in any written surface. Ask via `AskUserQuestion` before leaving any, and when approved, state why it is load-bearing for current behaviour.
- Commit bodies describe the current code change and nothing else; no session-internal names, codes or phases.
- Plan files hold current behaviour. The branch plan is a high-level description of the branch as it stands.
- Code comments describe current behaviour. Forbidden: change-from-to phrasing, commit references, deprecation warnings, "this used to be X". Git log and blame are authoritative for how code evolved. The one exception is a trick-explanation from observed behaviour.
- No check targeting behaviour that no longer exists: writing behaviour, deleting it, and leaving a test asserting its absence is a hallucinated check.
- No migration code in tooling - obsolete-key cleanup, version-detection polyfills, dual-pattern validators. Code expresses the current contract; a user upgrading handles stale local state manually.
- Forbidden details: dates ("Last updated", "Created on", "NEW"); commit hashes; ticket or MR IDs outside a branch-plan-relevant section; past-incident phrasing ("previously", "formerly", "after the rename", "now uses"); refinement artifacts ("Pass 1 added", "post-unification", "after Phase X").
- Forbidden: opaque session-internal codes anywhere - test-spec slot IDs, commit-stage labels, finding numbers, bare Decisions Log entry IDs in body text, work-step labels, references to gitignored files.
- Forbidden in a public-facing surface: AI-tooling role names and rule IDs. "gitter", "coder's Phase 2 rules-check", "G2 pre-validation", "AGT-26" mean nothing to a reviewer on GitLab. State the verified fact instead.
- Allowed: current-state declarations ("All X use Y", "No X in Y").
- Allowed: append-only Decisions Log entries, which may use "expected" or "hypothesized" wording. The log is history by design, not current-state documentation.
- Replace a forbidden narrative with the substance it stands for - what a test verifies, what a commit changes, what the code does now - or drop it.
- Bad: "Pass 3 of post-unification refinement scrubbed residual legacy refs Pass 2 missed". Good: "Legacy CLI references replaced with `mr` in the skill-validation workflow, `coder/python.md`, and the plan-writer agent prompt."

---

## STYLE-3: DRY-FACTS

**Statement:** A requested fact or number is written alone - no scope caveats, no justification clauses, no meta-commentary. Add a caveat only when asked for one.
- Not this: scope caveats ("single-machine snapshot, not a fleet statistic"), justification clauses ("before this design's own session"), commentary on the data's limits, or commentary on where facts live and how the document is organized.
- Repeat facts, never caveats. Restate a short fact wherever the reader needs it. The same qualifier opening several sibling sections means the structure is wrong.
- State absence, do not narrate it: write "Not applicable" or delete the heading, never explain why a section is empty.
- Bad: "12 files changed (measured on this branch only, may differ elsewhere)" when only the count was requested.

---

## STYLE-4: MINIMAL-DUPLICATION

**Statement:** A duplicated explanation is a defect; a duplicated fact is not.
- Explain a mechanism once. A second full explanation of it collapses into the first.
- A short fact may repeat freely - inline it wherever a sentence needs to stand alone.
- Prose may repeat a key term to keep a sentence self-standing. Only a second full explanation duplicates.
- Link conventions: `shared/rules/documentation.md` DOC-5.
- Bad: replacing a one-clause repeated fact with a link, forcing a jump for something that fits in a few words.

---

## STYLE-5: READING-ORDER

**Statement:** Written work is read once, top to bottom, by a reader who will not follow links and will not re-read. Every section reveals new detail and references only earlier ones.
- Keep the text as narrow as possible without losing meaningful detail, diagrams or code examples tied to the topic. Every surviving paragraph earns its place.
- Negotiate cuts with the developer rather than deciding alone that a tangential item stays.
- Bad: keeping a tangential example because it took effort to write.

---

## STYLE-6: UNIFORM-QUESTIONS

**Statement:** Every approval, option-selection and "should we proceed?" goes through `AskUserQuestion` - never an inline "?" in a paragraph.
- Each option carries a `preview` with a concrete code block where applicable, and the first is marked "Recommended" where applicable.
- Header: a short categorical label, 12 characters or less. Option explanation: a brief summary.
- Wordy choice details go as plain text before the question, never inside the option fields.
- Approval of a direction is not approval of the evidence cited for it, and never promotes a cited fact to "verified".
- Persistent sub-agents have no `AskUserQuestion`: they relay the question to the orchestrator via `SendMessage(to: "main", ...)` in AGT-26 RELAY-IDENTIFY's format, and the orchestrator asks. The relayed message and every option must be complete enough to ask without opening the sub-agent's transcript.
- Bad: "Should we proceed with X?" inline. Good: `AskUserQuestion(question="X?", options=[X, alternative-Y])`.

---

## STYLE-7: TEAM-REPORT

**Statement:** A bug or finding written for a team channel - chat, ticket comment, MR discussion note - is a short first-person narrative of a few sentences, not a list-heavy structure.
- Four parts in order: what happened, in one plain sentence; what the investigation found, one sentence naming the root cause with no code dump; what the user did to unblock themselves; the proposed fix, one short paragraph.
- No severity labels, tables, section headers, or step-by-step plans.
- Informal team communication only. Plans, DRDs, commit messages and code comments keep the STYLE-1 and STYLE-2 shape.
- Bad: posting a full rule table into a Slack thread instead of a short narrative.

---

## STYLE-8: CODE-COMMENTS

**Statement:** A comment states why the code is non-obvious, in at most four lines and never more lines than the code it guards.
- Banned register: first-person plural ("we", "let's", "our"), filler openers ("Note that", "Basically", "In other words", "Here we", "This means that"), and rhetorical setup before the point. `check_content.py` flags these live.
- A longer explanation belongs in a docstring or the design doc, not inline.
- A comment restating what the next line plainly says is deleted, not shortened.
- Keep, per STYLE-2's exemptions: a non-obvious constraint, a deliberate non-change, an observed-behaviour trick-explanation.
- Bad, six narration lines over a three-line guard:

```python
# target_subdir may already be a directory-level symlink resolving
# into this same source subtree (e.g. a whole skill symlinked as one
# unit). Walking into it would compute per-file target paths that
# physically resolve back into source_dir: os.remove() would delete
# the real source file and os.symlink() would recreate it pointing
# at itself. Skip the whole subtree - it's already linked.
```

- Good, same guard within budget:

```python
# A symlinked ancestor here means target_subdir IS source_dir on disk.
# Recursing would resolve target paths back into source and self-delete.
```

---

## STYLE-9: NO-LINE-CITATIONS

**Statement:** Documentation written for human readers names the file, class or function, never a `file:line` citation.
- Good: "`ServiceEventSink::OnSourceStopped` logs a warning and does not restart the session." Bad: the same sentence trailing a parenthesised source path and line numbers.
- Applies to every human-facing document a role produces: DRDs, BRANCH_PLAN.md, READMEs, hand-written design docs, EVT sheets.
- Does not apply to a role's own verification work - grepping for `file:line` to confirm a fact is normal and required. The citation must never survive into the output.

---

## STYLE-10: NO-DELETED-REFERENCES

**Statement:** Write what is there. Never mention what was removed, replaced, renamed or used to be - in any surface, including this one. Applied first, before anything else is written.
- A reader of the current text has never seen the old text. A sentence defining the present by contrast with something they cannot see costs them a fact and gives none.
- Applies to rule files, docs, commit bodies, code comments, plans, MR descriptions and replies alike.
- Deleting something is complete when the text reads as though it was never there. A note marking its absence is the deletion left unfinished.
- The change is visible in the diff, and the reason belongs in the commit body as a statement about what is needed now (G8), never as a comparison with what stood before.
- Bad: "No `Check:` clause any more" in a rule about rule shape.
- Bad: "This replaces the old gate", "the X section was dropped", "no longer uses Y", "renamed from Z".
- Bad: a heading kept with "removed" or "deprecated" under it instead of the heading being gone.
- Good: state the shape, the contract, or the behaviour that exists now, and stop there.

---
