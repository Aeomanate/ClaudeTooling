## Feature Introduction Workflow

WORKFLOW NAME: introduction

Research-driven feature introduction, POC first. Each phase reports to the
orchestrator - nothing is written to a separate artifact file. When
`.ai/BRANCH_PLAN.md` exists for this branch, design and test-case content
gets embedded there for developer review via plan-writer; when none
exists, ask the developer whether to create one (PLAN-1) or report
directly. Human approval required between phases.

**When to invoke:**
- Introducing a new feature, approach, or improvement
- Adding new functionality to existing system
- Significant behavioral changes to existing features

---

### Phase 1: RESEARCH - deep investigation (PLAN MODE)

Goal: understand everything needed BEFORE making any design decisions.

#### Step 1.1: Read documentation

Read ALL relevant documentation - internal and external. No hallucinations.
- Internal: BRANCH_PLAN.md, PROJECTNAME_CONTEXT.md, relevant module docs, Sphinx docs
- `.ai-stuff/` (when present in the project, e.g. reponame, kiros): the
- `.ai-stuff/` (when present in the project, e.g. reponame, kiros): the
  submodule's architecture and context docs - `PROJECTNAME_OPTIONSPLUS/context.md`,
  `options-plus-context.md`, `backend-architecture.md` - plus its coding
  standards when the affected language has one under `Languages/`
- External: Microsoft API docs, protocol specs, dependent tool docs
- If a resource is inaccessible or not found - DO NOT skip or imagine content.
  Log it as "UNAVAILABLE: {resource} - ask developer for reference."
  Ask the developer to provide documentation links.

Launch Explore agents (1 per documentation domain). Each agent:
- Reads the actual documentation
- Extracts relevant sections, quoting exact passages with source citations
  for anything a later phase may need to re-verify

#### Step 1.2: Research codebase

Investigate the actual codebase for:
- Existing implementations to reuse
- Patterns already in use (class hierarchies, message flow, threading)
- Files and modules that WILL be affected
- Files and modules that MAY be affected

Featurer PREPARES `Explore` spawn prompts (1 per module area or per query
type) and SendMessages the orchestrator requesting dispatch - only the
orchestrator holds the Agent tool for a fresh dispatch's targeting (AGT-1
DISPATCH-DISCIPLINE). The orchestrator invokes `Agent` with
`subagent_type: "Explore"` and forwards the result back. For each prepared
prompt, specify the query (e.g., "find all callers of X", "where is Y
referenced", "what files mention Z"), the search breadth
("quick"/"medium"/"very thorough"), and the expected output format.

#### Step 1.3: Compile findings

Merge all agent outputs into your report to the orchestrator. Cover:
- All references used (internal docs with file paths, external URLs)
- Existing code patterns found (with file:line citations)
- Affected modules list (definite + possible)
- Reusable components identified
- Open questions (things that need developer clarification)

#### Step 1.4: Verify research - no hallucinations

Launch verification agents:
- Agent 1: Check every internal reference against actual files on disk
- Agent 2: Check every code citation against actual source lines
- Agent 3: Check every external reference against cached documentation

Any claim without verifiable source is flagged as UNVERIFIED.
Developer reviews flagged items.

**Completion checklist:**
- [ ] All documentation read (internal + external)
- [ ] Codebase explored (existing implementations, patterns, affected modules)
- [ ] Findings reported with verifiable sources
- [ ] Verification agents confirmed zero unverified claims

---

### Phase 2: DESIGN - draft, then critique until convergence (PLAN MODE)

Goal: a design that survives real scrutiny before any code is written. The
draft is a starting point; the critique pass is where the real thinking
happens (FE-9 CRITIQUE-CONVERGENCE) - critique should be more thorough
than the draft it tests, and the draft evolves through critique findings,
not the other way around.

#### Step 2.1: Draft

Based on Phase 1's findings, draft the design:

Diagrams (ASCII for simple, Mermaid for complex) - the developer must see
these. Embed into `.ai/BRANCH_PLAN.md` when one exists for this branch
(via plan-writer), otherwise present directly in the report:
- C4 Context diagram - system boundaries and actors
- C4 Container diagram - high-level components
- C4 Component diagram - internal structure of affected modules
- DFD (Data Flow Diagram) - data movement through the feature
- Execution flow diagram - sequence of operations

Code examples:
- Key code changes with before/after
- New class/function signatures
- Integration points with existing code

Pattern analysis (optional - run only when the design has a branching,
wrapping, or creation decision to make; skip and say so otherwise):
- Read `refactorer/patterns/ai_index.md` and name applicable triggers
- Note suggested improvements per
  `featurer/agent-instructions/introduction-design-patterns.md`

#### Step 2.2: Critique, by group

Dispatch one per-task sub-agent per group below against the draft -
per AGT-1 DISPATCH-DISCIPLINE's reuse-before-spawning rule, reuse a
sub-agent already holding matching context instead of spawning a new one.
The three groups are independent lenses on the same draft; dispatch them
in parallel.

**Group A - People & Value:**
- **Ownership**: who owns this long-term? Who maintains it after ship?
- **Usage**: who uses it, how, how often? Is it discoverable in the actual workflow?
- **Value**: is this compelling enough that a user switches from today's
  approach? What's the cost of NOT building it?

**Group B - Operations & Reliability:**
- **Reliability**: how do we know it broke? How do we know it's working?
  What's the rollback plan?
- **Operational visibility**: what telemetry or logging surfaces a
  problem in production?
- **Scale**: what does adding N more of these look like (FE-8
  EXPANSION-FORECAST)?

**Group C - Risk & Alternatives:**
- **Security**: new attack surface, data handled, permissions required?
- **Risk**: what has to be true for this to succeed? Name the biggest risk.
- **Alternatives**: what else was considered, and why was it rejected,
  including doing nothing?

Each sub-agent reports findings for its own group only, one line per
dimension minimum. A group reporting no finding on any of its three
dimensions on a first pass is suspect - re-read the draft instead of
reporting "no issues."

#### Step 2.3: Revise and re-critique

Update the draft per all three groups' findings. Re-run Step 2.2 only for
the group(s) whose section of the draft changed. Repeat until every group
finds nothing new, or the developer explicitly says stop.

#### Step 2.4: Discuss the selected pattern

A pattern name is not a design. The same pattern takes different shapes
depending on ownership, lifetime, and how the call site is reached.
Selecting a pattern never authorizes implementing it.

Present the concrete shape, not the pattern name. State:
- the exact call site or construct it replaces
- who owns each new object and how long it lives
- pros: what this buys, in this codebase
- cons: added indirection, new files, test surface, what gets harder to read
- the alternative, including doing nothing

Relay to the orchestrator via `SendMessage(to: "main", ...)` for an
AskUserQuestion ask (featurer has no direct `AskUserQuestion` access -
classic schema, AGT-26 RELAY-IDENTIFY in shared/rules/agents.md). Options:
apply the pattern, apply a named alternative, or leave the code as it is.
Include the pros and cons in the option descriptions - the developer reads
the orchestrator's context, not this workflow file.

Do not edit until the developer answers.

**Completion checklist:**
- [ ] At least one critique pass ran, covering every dimension listed in Step 2.2
- [ ] Draft revised per critique findings, re-critiqued to convergence
- [ ] Concrete pattern shape stated, not just the pattern name (when a pattern applies)
- [ ] Pros and cons both present, including the cost of the pattern
- [ ] "Leave as is" offered as a real option

#### Step 2.5: Human approval (interactive)

Present the converged design to developer. This is an INFO GATHERING SESSION:
- Developer reviews diagrams, code examples, architecture choices, and the
  critique findings that shaped them
- Developer provides corrections, preferences, handoff decisions
- Developer resolves complex tradeoffs flagged by agents
- Multiple rounds of Q&A are expected

After developer approval, incorporate feedback. If significant changes,
re-run Step 2.1 with updated inputs.

#### Step 2.6: Final design verification

One more pass using Phase 1's findings + the converged design:
- Design against research (Phase 1 facts still valid?)
- Design against patterns library (any useful patterns missed?)
- Design against the documentation cited in Phase 1 (architecture matches product context?)
- Quote any newly-checked external page's relevant passage directly in the report
- Check all diagrams align with approved decisions from Step 2.5

Additional developer conversation if needed.

#### Step 2.7: Update BRANCH_PLAN.md (EXIT PLAN MODE)

When `.ai/BRANCH_PLAN.md` exists for this branch, route these through
plan-writer:
- Description section (what the feature does)
- Areas of Impact (affected modules, risks)
- Implementation Plan (TODO items)
- Decisions Log (architecture choices with rationale, including what the
  critique pass changed)
- The Phase 2 diagrams

When no branch plan exists, ask the developer (AGT-1) whether to create
one before proceeding.

**Completion checklist:**
- [ ] Design produced (diagrams + code examples + pattern analysis) and critiqued to convergence
- [ ] Design verified against Phase 1 findings
- [ ] Developer approved via interactive session
- [ ] BRANCH_PLAN.md updated with design decisions and diagrams (when one exists)

---

### Phase 3: PLANNING - test cases, verbal only (PLAN MODE -> EXIT)

Goal: name what to test, in prose. No test code, no stubs - writing and
running tests is Hardening's job (Phase 4), after the developer approves
the POC.

#### Step 3.1: Test case descriptions (PLAN MODE)

Based on Phase 2's converged design, describe in prose:
- General flow tests (happy paths)
- Edge cases and error paths
- Integration boundaries
- Performance/stress scenarios (if applicable)

Embed these into BRANCH_PLAN.md (when one exists) alongside the design,
via plan-writer; otherwise include them in your report. Developer reviews
the list.

#### Step 3.2: Implementation (EXIT PLAN MODE)

Hand the design and the Step 3.1 test-case list to coder. This is POC
work: per SKILL.md's "Mode: POC or Hardening," commits land as
`Verb (dirty) description` with no tests written yet - dispatched to gitter,
since a coder produced the diff.

#### Step 3.3: Manual testing and iteration

Developer runs manual scenarios from the Step 3.1 test-case list.
- Update the design if it needs adjustment
- Update the test-case list if new edge cases surface
- Iterate until developer satisfied

**Completion checklist:**
- [ ] Test cases described in prose, reviewed by developer
- [ ] POC implementation written per coder rules, dirty commits
- [ ] Manual testing iterated to developer satisfaction

---

### Phase 4: HARDENING

On developer approval of the POC, run WF-21 DIRTY-COMMIT-PROTOTYPING's
deferred stack (`shared/rules/workflow.md`) against the accumulated range,
using the Phase 3 test-case list as the tester's input.

**Completion checklist:**
- [ ] WF-21's deferred stack run to `CONVERGED` and closed with its
      `(hardening of <range>)` commit

---

### Phase 5: RULES CHECK - verify the work against this role's rules

Follow the procedure at
`~/.claude/skills/orchestrator/shared/rules-check-procedure.md` against
`~/.claude/skills/orchestrator/roles/featurer/rules.md` (FE-1 through
FE-9).
