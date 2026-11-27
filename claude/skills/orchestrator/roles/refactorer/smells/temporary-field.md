# Smell: Temporary Field
Category: Object-Orientation Abusers
Source: https://refactoring.guru/smells/temporary-field

## Signs and Symptoms
Temporary fields get their values (and thus are needed by objects) only under certain circumstances. Outside of these circumstances, they're empty.

## Reasons for the Problem
Temporary fields arise when algorithms require many inputs, prompting programmers to create class fields instead of large parameter lists. These fields are used only during specific operations and remain unused otherwise, creating confusing code where object fields appear perpetually empty.

## Treatment
- **Extract Class** -- move temporary fields and related code into a separate class, creating a method object (same effect as Replace Method with Method Object).
- **Introduce Null Object** -- replace conditional code checking for temporary field existence with a null object.

## Payoff
Better code clarity and organization.

## When to Ignore
- Caching or memoization fields that are intentionally populated lazily and remain empty until first use.
- Fields used by serialization frameworks that require a default-constructed state before hydration.

## Related

### Refactoring Techniques
- Extract Class
- Replace Method with Method Object
- Introduce Null Object

### Design Patterns That Prevent This Smell
- Strategy -- encapsulates algorithm-specific state in a separate strategy object
- Command -- packages operation parameters and state into a self-contained command object
- Builder -- collects construction parameters incrementally rather than storing them as temporary fields
