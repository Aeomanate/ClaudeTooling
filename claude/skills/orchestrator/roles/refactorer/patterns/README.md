# Refactoring Patterns Library

LLM-consumable decision pointers into GoF design patterns and Fowler-style
refactoring techniques. The library steers a pattern choice — it does not
teach the pattern.

## Catalog layout

- `ai_index.md` — the whole catalog: decision trees, then one line per
  design pattern and refactoring technique (trigger → name)
- `../smells/` — 24 code-smell files, one per smell, each with a "Related"
  section naming the fixing technique or pattern

## Usage

Read `ai_index.md`. Match the trigger phrase to the situation in the code.
Name the pattern or technique. Nothing else in this library needs reading —
there are no per-pattern files or code examples.

The design-pattern step is optional. Run it only when the change has a
branching, wrapping, or creation decision to make. Skip it and say so
otherwise. A pattern name is never authorization to implement it — see the
"Discuss the selected pattern" step in `featurer/workflow.md` and
`refactorer/workflow.md`.
