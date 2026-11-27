# Smell: Switch Statements
Category: Object-Orientation Abusers
Source: https://refactoring.guru/smells/switch-statements

## Signs and Symptoms
You have a complex `switch` operator or sequence of `if` statements.

## Reasons for the Problem
Switch operators are relatively uncommon in object-oriented code. When present, switch logic often scatters across multiple program locations. Adding new conditions requires finding and modifying all switch instances. When you see `switch` you should think of polymorphism.

## Treatment
- **Extract Method** and **Move Method** -- to isolate switch statements.
- **Replace Type Code with Subclasses** or **Replace Type Code with State/Strategy** -- for type-based switches.
- **Replace Conditional with Polymorphism** -- after establishing inheritance structure.
- **Replace Parameter with Explicit Methods** -- for switches with same method calls using different parameters.
- **Introduce Null Object** -- when conditions include null cases.

## Payoff
Improved code organization.

## When to Ignore
- When a switch operator performs simple actions, refactoring is not justified.
- Switch statements are often used by factory design patterns (Factory Method or Abstract Factory) for class selection.

## Related

### Refactoring Techniques
- Replace Conditional with Polymorphism
- Replace Type Code with State/Strategy
- Replace Type Code with Subclasses
- Introduce Null Object

### Design Patterns That Prevent This Smell
- Strategy -- replaces conditional branching with interchangeable algorithm objects
- State -- replaces state-based conditionals with state objects
- Factory Method -- centralizes object creation, replacing type-selection switches
- Abstract Factory -- encapsulates families of related object creation
