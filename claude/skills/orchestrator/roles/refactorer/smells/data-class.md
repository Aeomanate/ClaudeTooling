# Smell: Data Class
Category: Dispensables
Source: https://refactoring.guru/smells/data-class

## Signs and Symptoms
A data class refers to a class that contains only fields and crude methods for accessing them (getters and setters). These classes lack independent functionality and serve merely as data containers for other classes.

## Reasons for the Problem
Newly created classes often start with only public fields and basic accessors. However, the real strength of object-oriented design lies in objects containing behavior and operations on their own data.

## Treatment
- **Encapsulate Field** -- hide public fields and require access through getters/setters only.
- **Encapsulate Collection** -- apply encapsulation specifically to array and collection data.
- **Move Method** / **Extract Method** -- transfer functionality from client code into the data class itself.
- **Remove Setting Method** / **Hide Method** -- eliminate overly permissive accessor methods once the class has gained proper behavior.

## Payoff
- Improves code organization by consolidating operations on data in a single location.
- Helps identify and eliminate duplication in client code.

## When to Ignore
- Simple DTOs (Data Transfer Objects) and value objects that exist solely to carry data between layers or across boundaries are fine as data-only classes.
- Immutable record types or structs used for serialization/deserialization do not need behavior.

## Related

### Refactoring Techniques
- Encapsulate Field
- Encapsulate Collection
- Move Method
- Extract Method

### Design Patterns That Prevent This Smell
- Strategy -- attaches behavior to data by delegating operations to strategy objects
- Visitor -- adds operations to data-holding classes without bloating their interface
- Command -- encapsulates operations alongside the data they act upon
