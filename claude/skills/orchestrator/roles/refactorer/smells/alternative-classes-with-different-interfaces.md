# Smell: Alternative Classes with Different Interfaces
Category: Object-Orientation Abusers
Source: https://refactoring.guru/smells/alternative-classes-with-different-interfaces

## Signs and Symptoms
Two classes perform identical functions but have different method names.

## Reasons for the Problem
The developer who created one class likely didn't realize a functionally equivalent class already existed in the codebase.

## Treatment
- **Rename Method** -- make method names consistent across alternative classes.
- **Move Method** -- relocate methods between classes as needed.
- **Add Parameter** -- introduce parameters to standardize signatures.
- **Parameterize Method** -- generalize methods to accept parameters.
- **Extract Superclass** -- create a common parent class when only partial functionality duplicates.
- After standardization, one class can often be deleted.

## Payoff
- Eliminates unnecessary duplicate code, reducing overall code bulk.
- Improves readability and understanding by clarifying why multiple classes exist.

## When to Ignore
Merging alternative classes may prove impossible or impractical when the classes originate from different libraries, each maintaining their own versions.

## Related

### Refactoring Techniques
- Rename Method
- Move Method
- Extract Superclass
- Extract Interface

### Design Patterns That Prevent This Smell
- Adapter -- unifies incompatible interfaces under a common contract
- Strategy -- defines a shared interface for interchangeable algorithm implementations
- Bridge -- separates interface from implementation, ensuring consistent abstractions
