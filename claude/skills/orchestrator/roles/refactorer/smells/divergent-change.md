# Smell: Divergent Change
Category: Change Preventers
Source: https://refactoring.guru/smells/divergent-change

## Signs and Symptoms
You find yourself having to change many unrelated methods when you make changes to a class. For example, when adding a new product type you have to change the methods for finding, displaying, and ordering products.

## Reasons for the Problem
Often these divergent modifications are due to poor program structure or "copypasta programming".

## Treatment
- **Extract Class** -- split up the behavior of the class.
- **Extract Superclass** / **Extract Subclass** -- if different classes have the same behavior, combine them through inheritance.

## Payoff
- Improves code organization.
- Reduces code duplication.
- Simplifies support.

## When to Ignore
- Configuration or registry classes that are intentionally designed as central coordination points may legitimately change for multiple reasons.
- During early prototyping, splitting responsibilities prematurely can slow iteration without clear benefit.

## Related

### Refactoring Techniques
- Extract Class
- Extract Superclass
- Extract Subclass

### Design Patterns That Prevent This Smell
- Strategy -- isolates each axis of change into its own strategy class
- Bridge -- separates abstraction from implementation so each varies independently
- Observer -- decouples notification concerns from core class responsibilities
