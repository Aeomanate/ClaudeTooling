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

# Step 2: Enhance with plan sections

Wrap the filled MR body below with plan sections to create a complete
PLAN.md. Use the plan template for structure and the rules for guidance.

- The MR body content becomes the visible part (above the hidden block)
- Add hidden sections: Success Criteria, Verification, Architecture,
  Implementation Plan, Decisions Log
- Leave `## Decisions Log` section EMPTY — just the heading with no entries.
  It is for interactive AI session history, not for plan generation.
- Only add sections relevant to this ticket
- Do NOT modify the title (first `# ` heading) — it was set in step 1

Section fill rules:
{{PLAN_RULES}}

## Input

PLAN TEMPLATE:
{{PLAN_TEMPLATE}}

FILLED MR BODY (from step 1):
{{FILLED_BODY}}

