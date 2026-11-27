# Smell: Parallel Inheritance Hierarchies
Category: Change Preventers
Source: https://refactoring.guru/smells/parallel-inheritance-hierarchies

## Signs and Symptoms
Whenever you create a subclass for a class, you find yourself needing to create a subclass for another class.

## Reasons for the Problem
Hierarchies remain manageable initially, but as new classes accumulate, making modifications becomes increasingly difficult and burdensome.

## Treatment
- Make instances of one hierarchy reference instances of another hierarchy.
- Remove the redundant hierarchy using **Move Method** and **Move Field**.

## Payoff
- Eliminates code duplication across hierarchies.
- Potentially enhances overall code organization and structure.

## When to Ignore
Parallel hierarchies sometimes represent the most practical architectural solution. If de-duplication attempts produce inferior code quality, it may be preferable to retain the existing structure rather than force refactoring that worsens the codebase.

## Related

### Refactoring Techniques
- Move Method
- Move Field

### Design Patterns That Prevent This Smell
- Bridge -- decouples abstraction from implementation so hierarchies evolve independently
- Visitor -- adds operations without parallel subclass hierarchies
- Abstract Factory -- manages families of related objects without requiring parallel class trees
