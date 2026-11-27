# Smell: Shotgun Surgery
Category: Change Preventers
Source: https://refactoring.guru/smells/shotgun-surgery

## Signs and Symptoms
Making any modifications requires that you make many small changes to many different classes.

## Reasons for the Problem
A single responsibility has been distributed across numerous classes, sometimes resulting from excessive application of the Divergent Change refactoring pattern.

## Treatment
- **Move Method** and **Move Field** -- consolidate class behaviors into a single class.
- If no appropriate existing class exists, create a new one for the relocated code.
- **Inline Class** -- remove now-empty classes after code migration.

## Payoff
- Better organization.
- Less code duplication.
- Easier maintenance.

## When to Ignore
- Cross-cutting concerns (logging, authorization, metrics) inherently touch many classes; these are better addressed with aspect-oriented techniques than consolidation.
- When changes span multiple modules because each module owns its own implementation of a shared interface, that distribution is by design, not a smell.

## Related

### Refactoring Techniques
- Move Method
- Move Field
- Inline Class

### Design Patterns That Prevent This Smell
- Facade -- consolidates scattered operations behind a single unified interface
- Mediator -- centralizes communication so changes affect one class instead of many
- Observer -- decouples notification logic, reducing the need to modify multiple classes
