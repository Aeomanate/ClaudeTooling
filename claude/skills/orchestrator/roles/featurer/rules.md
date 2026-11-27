# Featurer Rules

Rules for research-driven feature introduction. Each rule prevents
a known failure mode in feature development.

---

## FE-1: NO-HALLUCINATIONS

**Statement:** Every claim in a research or design artifact carries a verifiable source - an existing file path, a named class or function found in the source, or a URL quoted alongside the passage it supports; a claim with none is a violation.
- An inaccessible resource is logged UNAVAILABLE and raised with the developer. Never invented, assumed or approximated.
- Locations name the file and symbol rather than a `file:line` citation, per STYLE-9 - these artifacts are read by humans and line numbers drift.

## FE-2: REPORT-CHAIN

**Statement:** Each phase reports its content to the orchestrator, and Phase N+1 starts only once Phase N's report - or its `BRANCH_PLAN.md` entry, where a branch plan exists - covers what the phase owes; missing content is a violation.
- Phase 1: research findings - all references, patterns, affected modules.
- Phase 2: converged design - diagrams, code examples, architecture decisions, the critique findings that shaped it.
- Phase 3: prose test-case descriptions.
- Phase 4: actual code. Tests are Hardening's job (WF-21).
- A later phase depends on the reported content, never on a file existing on disk.

## FE-3: APPROVAL-GATES

**Statement:** Three gates need a recorded developer response in the transcript before the next step begins; a gate with no recorded response is a violation.
1. After Phase 1 (research) - the developer validates findings and answers open questions.
2. During Phase 2 Step 2.3 (design) - interactive info-gathering session.
3. After Phase 3 Step 3.1 (test plan) - the developer reviews test specs before implementation.

## FE-4: SCOPE-DISCIPLINE

**Statement:** IN and OUT of scope are documented before implementation, and every changed file or behavior in the final diff traces to an IN-scope item or a logged TODO.
- New requirements emerging mid-implementation become TODO items; scope does not expand.
- One feature per workflow execution. Multiple features are multiple runs.

## FE-5: DOCUMENTATION-REQUIRED

**Statement:** A diff changing user-facing behavior updates all four in the same session - BRANCH_PLAN.md's Description (what changed), Areas of Impact (what risks), manual test cases (where user-visible) and the Decisions Log (what was decided and why). Any missing item is a violation.

## FE-6: PATTERN-ANALYSIS

**Statement:** A design with a branching, wrapping or creation decision runs pattern analysis at Phase 2 Step 2.1, whose output names the specific patterns checked against `refactorer/patterns/ai_index.md` and states per candidate why it was chosen or rejected.
- A design with no such decision satisfies this by saying so in the report.
- Absence of either the named patterns or the per-candidate reasoning is a violation.

## FE-7: API-DOCS-FIRST

**Statement:** Same as coder rules' CODER-5 API-DOCS-FIRST - fetch and quote the actual vendor or platform docs page before citing any platform-API behavior, in research, design and code alike. Never from memory.

## FE-8: EXPANSION-FORECAST

**Statement:** Before a Phase 2 design shape is locked, the expansion-forecast question is relayed, asked and answered on the record; a locked design with no recorded answer is a violation.

Relayed to the orchestrator via `SendMessage(to: "main", ...)` for an
`AskUserQuestion` ask - featurer has no direct access, classic schema, AGT-26
RELAY-IDENTIFY:

```
Expansion forecast: what does adding 2 more of these look like?
Options:
- Low concern - no significant per-feature boilerplate
- Medium concern - consider a shared abstraction
- High concern - switch to an alternative design now
```

- The question surfaces boilerplate costs that only become visible once the pattern repeats. A design chosen without it may be locally correct and structurally expensive at N+1 features.
- Bad: locking per-feature provider instantiation without asking what the 3rd feature looks like, then discovering the ~50-lines-per-feature cost after N ship.

## FE-9: CRITIQUE-CONVERGENCE

**Statement:** Every design draft passes all three Phase 2 Step 2.2 critique groups - People & Value, Operations & Reliability, Risk & Alternatives - before the approval gate, each naming a finding or an explicit "no finding" per dimension in its group.
- Dispatch per AGT-1's reuse-before-spawning rule: reuse a sub-agent already holding matching context, spawn only when none does.
- Each group's critique is more thorough than the draft it evaluates; a shallow critique defeats the point of dispatching it.
- The draft evolves through critique findings, not the reverse: revise, re-critique the affected groups, until every group finds nothing new or the developer says stop.
- A design approved with a group missing, or a critique silently skipping a dimension, is a violation.
- Bad: treating the critique as a formality, or approving after a pass raised findings with no re-critique confirming they were addressed.

---

## Referenced common rules

These cross-cutting rules apply to featurer work. Read them at the canonical paths:

- DEL-1 (Execution Structure; skill-tree editing forbidden for all persistent sub-agents) - `~/.claude/skills/orchestrator/rules/delegation.md`
