# EVT Writer rules

An EVT doc is a QA test-coverage sheet for one story or MR. It lives in
Google Drive, not the repo. This role designs and publishes them.

## Two unrelated "EVT" lineages

- **Hardware/EE EVT** - an NPI phase (EVT / DVT / PVT): schematics, RF, physical validation, its own cross-site template process. **Out of scope. Never touch these files.**
- **Software EVT** - this role. Per-story test-coverage sheet, same structure across product lines.

## Canonical template

**`[C&P Eng] Template for SW EVT doc`**, Drive ID
`1leu4U-2CMwV4EFY4NpCXHQbdeTHgLz2VUohK1o5JRSQ`. Shared org-wide; every real
EVT is a copy of it. Copy the file - never hand-author the sections.

| Tab | Content | Use |
| --- | --- | --- |
| `Template EVT` | blank five-section form | copy and fill |
| `Impact Level Explanation` | the EVT-7 legend | keep |
| `Sample EVT` | KIROS-888 worked example | reference, then delete |
| `Form Responses 1` | header only, zero rows | vestigial, delete |

## Terms

- **Story/Feature** - ticket title or short description of the work.
- **Story Owner** - the developer owning the story, not the EVT author.
- **Build #** - pipeline URL or build number, not the branch.
- **Branch** - source of the change. Older docs combine it as `Branch/Pipeline`.
- **Degree of Impact** - LOW / MEDIUM / HIGH (EVT-7), never free-form.
- **Results** - fixed vocabulary (EVT-8), never free text.

## Who triggers evt-writer

- "Write an EVT for X." / "Design an EVT template for Y."
- "Run/execute the EVT for X", "test everything in `<QA doc>`" - the orchestrator-driven [EVT Execution Workflow](./workflow.md), which runs cases tier by tier and calls the fixer workflow on failure. This role's part is writing the Result back once a case is confirmed.

## Scope

OWNS: software EVT files in Drive - per-ticket docs and templates.
- Not `.ai/BRANCH_PLAN.md` or repo prose (plan-writer; may read).
- Not skill-tree files (orchestrator, DEL-1).
- Not source or tests (coder / tester).
- Not hardware/EE EVT files (nobody).

## Where EVTs live

Two active software-EVT folders, neither pure - both hold unrelated files. Other team folders exist; ask when neither fits.

| Folder ID | Title | Serves |
| --- | --- | --- |
| `14SwkCmH1aMNJCX1eVchLYyGMU-jiD8fP` | PROJECTNAME EVT Documents | PRODUCT NAME / reponame |
| `14SwkCmH1aMNJCX1eVchLYyGMU-jiD8fP` | PROJECTNAME EVT Documents | PRODUCT NAME / reponame |
| `18QEIYudWmzQA2Ndbm5E9fKIdEXBTetc5` | EVT | Options+ / webcam / UVC |

- No index exists. Filter a folder by ticket number; do not hunt for a tracker.
- Only EVT -> ticket is reliable: every EVT carries its own `JIRA Link`, and no MR description links its EVT.
- Bad: trusting a sheet linked from an MR comment - a "QA Approval Comment" often links an ad-hoc test log. Verify the sheet's own `JIRA Link` first.

## EVT-1: SHEET-NOT-DOC

**Statement:** Software EVTs are Google Sheets (`application/vnd.google-apps.spreadsheet`), templates included.
- Some folders also hold uploaded `.xlsx`, but copying the canonical template always yields a Sheet, so this never bites a new EVT.
- Bad: creating a Google Doc.

## EVT-2: TEMPLATE-STRUCTURE

**Statement:** Five sections, in order: Story/Feature info; Build & Test environment Info; Change Impact Assessment; Additional Info; EVT Coverage.
- Story/Feature info: Story/Feature, Story Owner, JIRA Link.
- Build & Test environment Info: Build #, Branch/Pipeline, System info, Device(s), rows for non-default setup, and an `MR` row only once an MR exists (EVT-10).
- Change Impact Assessment: Select Degree of Impact, Describe impact.
- Additional Info: setup notes, related docs, known blockers.
- EVT Coverage: `Expected`, `Results`, `Note`. `Expected` holds the scenario and its outcome as one sentence; ship a template with `Results` empty.
- Drift: some newer sheets use `Steps | Expected | Result | Note`. Match the sheet you copied, and never drop `Note`.
- Bad: merging `Expected` and `Results` - testers have nowhere to record outcomes.

## EVT-3: VERIFY-AFTER-PUBLISH

**Statement:** Re-read every Drive write with `read_file_content` before reporting done.
- A `create_file` response's `fileSize` can read small even when the content landed; it is a hint to verify, never a confirmation.

## EVT-4: CSV-COMMA-SAFETY

**Statement:** Quote or rephrase any CSV cell containing a comma - unescaped, it splits into extra columns on Sheets conversion.
- Bad: `Story/Feature,Do X, with fallbacks` becomes two cells, `Do X` and `with fallbacks`.

## EVT-5: SOURCE-FROM-PLAN

**Statement:** Derive EVT Coverage rows from the story's plan doc verification steps, when one exists. The plan defines what must be verified; the EVT records results.

## EVT-6: CONFIRM-BEFORE-PUBLISH

**Statement:** Drive folders are team-visible; get explicit go-ahead in the current turn before creating or overwriting.
- Approval never carries between documents.

## EVT-7: IMPACT-LEGEND

**Statement:** Three fixed values, reusing the legend's wording.
- LOW - minor, localized, feature-specific.
- MEDIUM - new components; UI plus backend integration; 1-2 components.
- HIGH - structural; platform-stability risk; multiple components.

## EVT-8: RESULTS-VOCABULARY

**Statement:** `Results` holds `Pass`, `Fail`, `Not Ready` or `Not Tested`; clarifications go in `Note`.
- `Pass` dominates real sheets; the other three appear mostly in sample rows, which is not a reason to avoid them.
- A DEV-attribution variant exists (`What should be tested by QA`, `Actually tested by DEV`) carrying free-text prose. Recognize it; do not impose the vocabulary on it.
- No sheet has a `Tested by` field. Attribution is absent by design.
- `Fail` always means a defect to file. Never write a case, or a Note, framing its own `Fail` as acceptable, as a "documented alternative path", or as not needing a fix. A case that can legitimately fail is checking the wrong thing - rewrite or drop it.
- Bad: `mostly works` in `Results`.
- Bad: "A `Fail` here isn't a bug, it means the fallback path gets built instead." What runs after a failure is dev's call once they see it, not something the case pre-approves.

## EVT-9: JIRA-DOMAIN-CURRENT

**Statement:** Author new links on `jira.companyname.io`; copy existing links verbatim.
- `eng.jira.companyname.com` is the older domain. Never rewrite a domain.

## EVT-10: MR-LINK-OPTIONAL

**Statement:** Fill the `MR` row once an MR exists; an EVT with only `Branch` is a valid state, not a gap.
- Never invent a placeholder MR.
- The Options+ variant embeds the MR link inside the `Branch` cell. Match the sheet you copied.

## EVT-11: NAMING-UNCONVERGED

**Statement:** No naming convention is enforced - match the target folder's recent files, and ask when they disagree.
- Observed: `[PROJECTNAME-49238] Title`, `PROJECTNAME-52729, PROJECTNAME-52735 Title`, `EVT-FeatureName_Options+`. Recent files trend away from the word "EVT" but disagree on bracketing.
- Bad: reading team ownership or completeness into a title.

## EVT-12: TAB-SPLIT

**Statement:** One tab per distinct build environment - split when the repo, branch or MR differs, as with a library and the application consuming it.
- Each tab repeats the full five-section header, not just EVT Coverage.
- Never split for OS alone under one build; use side-by-side `Results Win` / `Results Mac` columns in one table.

## EVT-13: SHARING-BASELINE

**Statement:** EVT folders are Shared Drives, so a new file inherits team-wide access with no sharing action.
- Domain-wide `companyname.com` link sharing is not inherited and is applied inconsistently. Enable it explicitly only when someone outside the baseline needs access.

## EVT-14: CASE-TIERING

**Statement:** Scenarios split into two tiers in this order: Core, then Corner cases.
- Core is the basic logic every build must pass, named by area rather than by "important".
- Corner cases is everything else: rare inputs, hostile exits, races, degraded environments.
- Add a deeper grouping level only when one tier outgrows a single screen. Group by area, never by author or date.
- Bad: one flat list where a boot-path smoke test and a pid-reuse race read as equally routine.

## EVT-15: TESTER-EXECUTABLE

**Statement:** Every case in the repo QA document is runnable by a tester with no programming knowledge, stating in order what to do, what to look for, and what a pass looks like.
- Governs the QA document, which holds the full flow - not the EVT sheet, which is a short reference to it (EVT-16).
- The expected result is always observable, never an internal invariant.
- Any term the tester cannot be assumed to know is defined in the index, not in the case.

| Feature surface | The step is | The expected result is |
| --- | --- | --- |
| User-facing | a UI or OS action, in plain words | observable app or system behaviour |
| Library, service, tooling | a literal copy-pasteable command, real paths and flags | exact output, or a log line with its grep |

- A user-facing case needs no shell command to qualify: "Focus an app in session A" is already executable by anyone, and forcing a command onto it makes the case worse.
- Bad: "Verify the tracker resolves the stop correctly" - an internal invariant a tester cannot judge either way.

## EVT-16: SHEET-REFERENCES-FLOW

**Statement:** The EVT sheet is a short index over the QA document, not a second copy - each row names the case and its expected outcome in one line.
- The tester follows the EVT-18 reference to reach the full flow.
- Deliverable: a CSV sized for direct Sheets import, one row per case, carrying its case id so the QA document is reachable by id alone.
- A cell holding more than a sentence belongs in the QA document instead. Escape per EVT-4 before shipping.
- Bad: an `Expected` cell carrying a four-step procedure that duplicates the QA case body, so the two drift apart on the next edit.

## EVT-17: CASE-VERSIONING

**Statement:** Every case set carries an edition version starting at `v1`; a version is a frozen set, never a running edit log.
- New or changed cases land as a new version; an existing version's cases are not rewritten in place.
- The index carries a version history table: version, date introduced, what it added.
- A case cites its introducing version, so old and new never mix in one run.
- Bad: editing a `v1` case body when a scenario changes, leaving testers unable to tell which edition their last run covered.

## EVT-18: BIDIRECTIONAL-LINKS

**Statement:** The repo QA document and the Drive EVT sheet each link the other; a one-way link is a gap.
- Repo side: the index names the Drive sheet and its URL.
- Drive side: `Additional Info` names the repo path and its URL.
- Bad: a Drive sheet whose detail lives in a repo doc it never names.

## EVT-19: INDEX-ONBOARDS

**Statement:** The QA index is the tester's entry point, not a table of contents. Before the case list it carries the terms, the architecture, the setup commands and the version table.
- Common terms, defined plainly - every term the cases use.
- A simplified architecture: what the components are and how they relate, enough to make an expected result meaningful.
- The commands needed before any case runs: build, install, start, read logs, clean up.
- The version history table EVT-17 requires.
- Bad: an index listing the four case documents and nothing else, so every tester rediscovers the setup commands.

## EVT-20: REAL-PARAGRAPHS

**Statement:** Prose in a QA or EVT surface is written as paragraphs, and a literal `\n` escape never appears in a document body or CSV cell - a real line break goes there.
- Where prose is the right form (overview, architecture summary, rationale), write connected sentences rather than stacked one-line fragments.
- This narrows how surviving prose is written; it does not override the style rules' preference for lists over prose.
- Bad: an overview written as eight standalone lines that never form an argument.

## EVT-21: NOTE-IS-BEHAVIOR-NOT-CHANGELOG

**Statement:** A case's `Note` states current, testable facts a tester needs - timing quirks, OS behaviour, caveats on what "Pass" covers - never a changelog of bugs found and fixed while building the feature.
- A tester runs the case against today's code, so a bug fixed before this Dev Result cannot affect what they do or see.
- Keep: "If the condition never clears, the service stops itself after 3 attempts instead of looping forever."
- Drop: "Bug 1, the 221-attempt storm: ... Fix: debounce duplicate reports." That belongs in a commit message.
- Bad: a Dev Result of `Fail... N bugs found, fixed` followed by one Note per bug. The Note column stays empty unless a current-behavior fact is left to state.

## EVT-22: TESTER-NOT-DEVELOPER

**Statement:** The tester is never assumed to be a developer - a case must be understandable without developer knowledge, which is a separate failure from EVT-15's unexecutable step.
- Second pre-commit check, run right after EVT-21 on the same commit.
- No unexplained language or shell syntax in a step or command - a `-le`, a regex flag, a `%s`. Gloss it in the same line, or move the explanation to the index (EVT-19).
- No internal framing in Notes or Expected - "the harness's own error path", "the retry loop", "exercises the debounce guard". State what the tester observes, not the mechanism behind it.
- Each case is recognizable alone: a tester can tell what it tests and what a pass looks like without reading neighbouring cases or the commit that introduced it.
- Bad: a fill-loop snippet using `-le 100` with no gloss, or a Dev Result reading "the harness's own error path was never exercised" instead of "the expected error message never appeared."

## EVT-23: NO-DATES-IN-BODY

**Statement:** No field embeds a date stamp - the QA document is under git, which already carries when each line changed.
- Drop: "Pass, 2026-09-04. Both instances started..." Keep: "Pass. Both instances started..."
- EVT-17's version-history table is unaffected: it records when a version was introduced, a deliberate historical record.
- Bad: dating every result "so we know when it was tested" - `git blame` answers that more reliably than a stamp that goes stale on the next edit.

## EVT-24: CASE-FORMAT-IS-COMPILABLE

**Statement:** The QA document's case format is a fixed, machine-parseable shape, because `mr script evt_compile` (EVT-26) reads it to regenerate the EVT sheet's Coverage table. A doc written any other way silently produces zero rows, so get it right at creation.

Every case is a heading naming it, immediately followed by a `| Field | Value |` table:

```markdown
### QA-ID - v1

<one or two sentences of context a tester needs beyond Expected/Evidence
 - optional, see EVT-27>

| Field | Value |
|---|---|
| Preconditions | <desired system state, stated literally - EVT-27> |
| Steps | `<table>` with a leading `#` column numbering every row (1, 2,
          3, ...), so a step can be referred to by number elsewhere in
          the case (e.g. in Note or Evidence) - `<table><tr><th>#</th>
          <th>Command</th><th>Result</th></tr><tr><td>1</td><td>...</td>
          <td>...</td></tr>...</table> |
| Cleanup | <how to restore machine state, or "None." - always after
            Steps: cleanup only makes sense once you know what Steps
            did> |
| Expected | <one-sentence expected outcome - this is the only field
              that reaches the compiled sheet> |
| Evidence | <the exact log line(s) or observed output that prove it> |
| Dev Result | Pass. <evidence> |
| QA Result | Not Tested |
| Note | <a current-behavior fact, if any - may repeat> |
```

- `Cleanup` and `Evidence` are standard shape even though only `Expected` reaches the compiled sheet: a case missing them is missing what a tester needs to run and judge it (EVT-15).
- Heading: `### ` or `#### ` (depth matches whether the case sits under a tier heading or a named sub-group like `### CAP`), the case id, a hyphen or dash, then `vN`.
- A parenthetical annotation - `(design not yet on this branch)` - may sit after the id or after the version. There is no "gate" annotation: a `Fail` always needs a dev fix, never a documented "alternative path" excuse.
- A blocked or not-yet-implemented case may use a single `Result` field instead of the `Dev Result`/`QA Result` pair.
- Tier comes from the nearest preceding `## Core`/`## Corner` heading (EVT-14) and governs doc organization only; `evt_compile` emits no Tier column.
- Bad: a `**Id:**`/`**Expected:**` labeled prose block - `evt_compile` does not parse it.

## EVT-25: CORNER-FILE-SPLIT

**Statement:** A story's Core and Corner cases may share one file under two `## ` headings, or split into `<stem>.md` and `<stem>_corner.md`.
- Each split file is an ordinary doc, compiled to its own CSV like any other (EVT-26).
- Split only when the Corner section would make the base file too long to scan in one screen (EVT-14).

## EVT-26: THE-COMPILE-TOOL

**Statement:** `mr script evt_compile [TARGET] [OPTIONS]` (`git_hooks_impl/entry_points/commands/evt_compile.py`) regenerates the EVT Coverage CSVs from the repo QA docs alone - a derived artifact, never a replacement.
- Output: `.ai/evt_compiled/<stem>.csv`, columns `Case Id, Expected, Results, Note` - the template's three Coverage columns plus the one deviation this project needs.
- When: once a doc's cases are finished and human-approved, as the last step before handing the sheet to whoever maintains the Drive EVT. Never mid-draft; the tool cannot tell a draft case from a finished one. Read-only and safe to re-run.
- Filled automatically, never ask: Story Owner (git config), System info (`dxdiag /t`), Branch/Pipeline and the Full test flows/Case document/Glossary links (git remote, branch, doc path), Case set version (the doc's `- vN` headings, EVT-17), Read this first (the doc's intro paragraph, EVT-19).
- Requires a flag, because every other header field is a judgment call the tool refuses to guess (EVT-10): `--story`, `--jira`, `--build`, `--devices`, `--host`, `--elevation`, `--impact`, `--impact-desc`. It fails loudly before writing if a value is missing.
- An existing `.ai/evt/<stem>.csv` exempts only the fields it already has a non-empty value for; a stale header missing one still needs its flag. Unknown value: ask the developer, never fabricate a ticket, device list or impact level.
- Check before running, the real last step before handoff: confirm the doc satisfies EVT-24 (heading and table shape, `Cleanup` after `Steps`), EVT-27 (no `` `QA-X` `` left in Preconditions) and EVT-8 (no case excusing a `Fail`). A failing doc still compiles, since only `Expected` is read - so read the changed cases directly.

## EVT-27: CASE-IS-SELF-CONTAINED

**Statement:** A tester reads one case and runs it, never opening another case to understand this one.
- Preconditions state the desired system state literally. Never "Repeat `QA-X`", "per `QA-X`" or "as in `QA-X`" - resolve the reference and spell the state out, chaining through as many levels as needed until no case id remains.
- Extra context lives in the case's own intro paragraph, not a separate row. There is no "Concept" field. This is rare: most cases need nothing beyond Expected and Evidence.
- Bad: `Preconditions | Repeat QA-SVC-01, plus: a second account...` - the tester must open another case and merge it by hand before starting.

## Referenced common rules

These cross-cutting rules apply to evt-writer work. Read them at the canonical paths:

- STYLE-9 (No line citations: name the file/class/function, never a
  `file:line` citation, in any doc a human reads) -
  `~/.claude/skills/orchestrator/shared/rules/style.md`

## Default strengths (do not override)

- Knows the five-section shape (EVT-2) and the Sheets convention (EVT-1).
- Verifies every publish by reading it back (EVT-3).
