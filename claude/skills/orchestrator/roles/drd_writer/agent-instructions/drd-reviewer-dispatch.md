# Agent Instructions: DRD Reviewer Dispatch

Sub-agent dispatch documentation for the reviewer step (Phase 4,
Step 4.1) of the DRD writing workflow. This file exists for
role-discovery parity (matches the plan-writer role's
`agent-instructions/` pattern) - it documents how to dispatch the
dedicated reviewer agent; it contains no executable prompt content
of its own.

## Purpose

Document how Phase 4, Step 4.1 of the DRD writing workflow dispatches
the DRD reviewer, so the orchestrator can build a correct spawn
prompt without reading the reviewer agent's own definition file.

## Inputs

The dedicated agent (`orchestrator-agent-drd_fake_reviewer`) declares
these in its body. The orchestrator must pass each one in the spawn
prompt:

* **DRD_PATH** - absolute path to the DRD file under review.
* **DRD_TEMPLATE_PATH** - defaults to
  `../sw-arch-drd/templates/drd_template.md`.
* **ARC_RULES_PATH** - defaults to
  `${DRD_REVIEW_AUTOMATION_REPO}/skills/drd-review/references/arc-architecture-rules.md`
  (the distilled Kiros + Lego rubric; sole source of architectural
  alignment truth - the reviewer does NOT read the full reference
  docs).
* **ARC_MEMBERS_PATH** - defaults to
  `${SW_ARCH_DRD_REPO}/ARC_MEMBERS.md` (reviewer roster; the
  reviewer picks one handle per the real CI procedure).
* **OUTPUT_PATH** - absolute path where the reviewer writes its
  output.
* **ITERATION_NUMBER** - current iter (1..10) for convergence
  tracking only; does not change output shape.
* **PRIOR_GAPS** - optional list of gaps from the prior iter. Pass
  this for iter > 1 so the reviewer can flag carryovers + new
  findings in the same single-page schema.

## Output Format

The reviewer's output schema matches the real CI verbatim
(verdict + completeness + ≤5 architecture-alignment bullets + ≤4
open-questions bullets + suggested reviewer). It does NOT use a
BLOCKER/MAJOR/MINOR/NIT severity scale - only the verdict line. The
agent writes this output to its own agent directory under
`OUTPUT_PATH`.

## Rules

* The actual reviewer logic lives in the dedicated sub-agent
  registered under the name **`orchestrator-agent-drd_fake_reviewer`**
  - this file only documents how to dispatch it, never re-implements
  its logic.
* Drd-writer dispatches the fake-reviewer directly via `Agent`, once,
  at iteration 1 (per AGT-1 DISPATCH-DISCIPLINE - a persistent sub-agent
  may spawn its own per-task verifiers):

  ```
  Agent({
    subagent_type: "orchestrator-agent-drd_fake_reviewer",
    description: "Review DRD against architecture references",
    prompt: "<spawn prompt drd-writer prepared, forwarded verbatim>"
  })
  ```

* Every later iteration (2..10) reuses that same spawned instance via
  `SendMessage` with the new `ITERATION_NUMBER` and `PRIOR_GAPS`, per
  AGT-1's reuse-before-spawning rule. A per-task agent stays addressable by
  `SendMessage` for its whole session; AGT-1 restricts who may dispatch a
  **persistent role coordinator**, not whether a spawned per-task agent can
  be resumed by the actor that spawned it.
* Drd-writer reads the reviewer's output directly and stages the
  disposition table per DRD-8 NO-AUTONOMOUS-DISPOSITION.

## Scope

One reviewer instance per DRD-writer session, re-entered once per
iteration (1..10) via `SendMessage`. Documents dispatch mechanics only -
DRD content decisions and gap fixes are drd-writer's job, not this file's.
