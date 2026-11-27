# Smell: Large Class
Category: Bloaters
Source: https://refactoring.guru/smells/large-class

## Signs and Symptoms
A class contains many fields, methods, or lines of code.

## Reasons for the Problem
Classes begin small but expand over time as programs grow. Developers typically find it easier to add new features to existing classes rather than create new ones.

## Treatment
- **Extract Class** -- separates distinct behavioral components into independent classes.
- **Extract Subclass** -- isolates variant behaviors or rarely-used functionality.
- **Extract Interface** -- creates a contract for operations clients can utilize.
- **Duplicate Observed Data** -- moves graphical interface data to domain objects while maintaining consistency.

## Payoff
- Reduces cognitive load by limiting attributes developers must track.
- Prevents code duplication through strategic class decomposition.

## When to Ignore
- Framework base classes or application root classes (e.g., main window, application controller) may legitimately be large due to their coordinating role.
- Generated code (e.g., protocol buffer classes, ORM models) that is maintained by tooling rather than by hand.

## Related

### Refactoring Techniques
- Extract Class
- Extract Subclass
- Extract Interface

### Design Patterns That Prevent This Smell
- Facade -- provides a simplified interface while distributing responsibilities across smaller classes
- Strategy -- moves variant behaviors into separate strategy classes
- Observer -- decouples notification logic from the main class
- Bridge -- separates abstraction from implementation, preventing class bloat
