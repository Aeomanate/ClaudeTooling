# Smell: Comments
Category: Dispensables
Source: https://refactoring.guru/smells/comments

## Signs and Symptoms
A method is filled with explanatory comments.

## Reasons for the Problem
Comments often mask underlying code quality issues. The best comment is a good name for a method or class. When code requires extensive comments to understand, it signals the need for structural improvements rather than explanation layers.

## Treatment
- **Extract Variable** -- for complex expressions that need clarification.
- **Extract Method** -- convert commented code sections into well-named, self-documenting methods.
- **Rename Method** -- when extracted methods still need explanation, rename them meaningfully.
- **Introduce Assertion** -- for documenting required system states and conditions.

## Payoff
Code becomes more intuitive and obvious.

## When to Ignore
Comments remain valuable for:
- Explaining design rationale (the "why" behind implementation choices).
- Documenting complex algorithms when all simplification attempts have been exhausted.

## Related

### Refactoring Techniques
- Extract Variable
- Extract Method
- Rename Method
- Introduce Assertion

### Design Patterns That Prevent This Smell
- Self-documenting code practices and meaningful naming conventions are the primary preventive measures. When code requires explanation, the need is typically for refactoring, not comments.
