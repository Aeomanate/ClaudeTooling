# Smell: Dead Code
Category: Dispensables
Source: https://refactoring.guru/smells/dead-code

## Signs and Symptoms
A variable, parameter, field, method or class is no longer used (usually because it's obsolete).

## Reasons for the Problem
Code becomes obsolete when software requirements change or corrections are made without cleanup. Unreachable branches in complex conditionals arise due to errors or changed circumstances.

## Treatment
- Delete unused code and unnecessary files.
- **Inline Class** or **Collapse Hierarchy** -- when a subclass or superclass is unnecessary.
- **Remove Parameter** -- eliminate unneeded method parameters.

Use an IDE to efficiently identify dead code.

## Payoff
- Reduced code size.
- Simpler maintenance and support.

## When to Ignore
- Feature-flagged code waiting for activation in an upcoming release.
- Public API methods that must remain for backward compatibility even if no internal callers exist.
- Hook or callback methods required by a framework contract that are not yet wired up.

## Related

### Refactoring Techniques
- Inline Class
- Collapse Hierarchy
- Remove Parameter
- Remove Assignments to Parameters

### Design Patterns That Prevent This Smell
- Continuous refactoring discipline and code review practices are the primary preventive measures for dead code accumulation.
