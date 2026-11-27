# Smell: Speculative Generality
Category: Dispensables
Source: https://refactoring.guru/smells/speculative-generality

## Signs and Symptoms
There's an unused class, method, field or parameter.

## Reasons for the Problem
Code is sometimes created "just in case" to support anticipated future features that never materialize, making the codebase harder to understand and maintain.

## Treatment
- **Collapse Hierarchy** -- for removing unused abstract classes.
- **Inline Class** -- to eliminate unnecessary delegation of functionality.
- **Inline Method** -- to remove unused methods.
- **Remove Parameter** -- for methods with unused parameters.
- Delete unused fields directly.

## Payoff
- Slimmer, more concise code.
- Easier maintenance and support.

## When to Ignore
- Framework development: creating functionality needed by framework users is acceptable.
- Unit tests: don't delete elements if tests require them for accessing internal information or special testing actions.

## Related

### Refactoring Techniques
- Collapse Hierarchy
- Inline Class
- Inline Method
- Remove Parameter

### Design Patterns That Prevent This Smell
- YAGNI discipline is the primary prevention. Avoid premature application of patterns like Abstract Factory or Bridge until actual variation demands them.
