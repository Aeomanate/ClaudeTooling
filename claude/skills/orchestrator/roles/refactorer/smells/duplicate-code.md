# Smell: Duplicate Code
Category: Dispensables
Source: https://refactoring.guru/smells/duplicate-code

## Signs and Symptoms
Two code fragments look almost identical.

## Reasons for the Problem
Multiple programmers working simultaneously on different tasks may independently create similar code without realizing colleagues have already written reusable solutions. Subtle duplication occurs when code performs identical functions despite appearing different. Intentional duplication happens when developers rush deadlines, copy-paste "almost right" code, or lack motivation to refactor.

## Treatment
- **Extract Method** -- for identical code in multiple methods within one class.
- **Pull Up Field** / **Pull Up Constructor Body** -- for duplicate code in same-level subclasses.
- **Form Template Method** -- for similar but non-identical duplicate code.
- **Extract Superclass** / **Extract Class** -- for duplication across unrelated classes.
- **Consolidate Conditional Expression** / **Consolidate Duplicate Conditional Fragments** -- for repeated conditional logic.

## Payoff
Merging duplicate code simplifies the structure of your code and makes it shorter. Simplified, shorter code is easier to maintain and cheaper to support.

## When to Ignore
In very rare cases, merging two identical fragments of code can make the code less intuitive and obvious.

## Related

### Refactoring Techniques
- Extract Method
- Pull Up Method
- Form Template Method
- Extract Superclass

### Design Patterns That Prevent This Smell
- Template Method -- defines an algorithm skeleton with overridable steps, eliminating near-duplicate methods
- Strategy -- extracts variant logic into reusable strategy objects
- Decorator -- composes shared behavior instead of duplicating it across subclasses
