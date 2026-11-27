# Smell: Inappropriate Intimacy
Category: Couplers
Source: https://refactoring.guru/smells/inappropriate-intimacy

## Signs and Symptoms
One class uses the internal fields and methods of another class.

## Reasons for the Problem
Classes that interact too closely are harder to maintain and reuse. Good classes should know as little about each other as possible.

## Treatment
- **Move Method** / **Move Field** -- transfer parts between classes when one doesn't truly need them.
- **Extract Class** / **Hide Delegate** -- make class relationships official and explicit.
- **Change Bidirectional Association to Unidirectional** -- resolve mutual dependencies.
- **Replace Delegation with Inheritance** -- when intimacy exists between subclass and superclass.

## Payoff
- Improves code organization.
- Simplifies support and code reuse.

## When to Ignore
- Tightly coupled classes that are always deployed and versioned together (e.g., a class and its dedicated helper or builder) may justify intimate knowledge of each other.
- Friend classes in C++ or package-private access in Java are sometimes used intentionally to restrict visibility to a controlled set of collaborators.

## Related

### Refactoring Techniques
- Move Method
- Move Field
- Extract Class
- Hide Delegate
- Change Bidirectional Association to Unidirectional

### Design Patterns That Prevent This Smell
- Mediator -- centralizes inter-class communication, reducing direct coupling
- Facade -- provides a simplified interface that shields internal class details
- Observer -- replaces direct field access with event-based notification
