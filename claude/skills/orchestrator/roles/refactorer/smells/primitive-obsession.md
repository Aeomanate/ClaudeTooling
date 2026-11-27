# Smell: Primitive Obsession
Category: Bloaters
Source: https://refactoring.guru/smells/primitive-obsession

## Signs and Symptoms
- Use of primitives instead of small objects for simple tasks (such as currency, ranges, special strings for phone numbers, etc.).
- Use of constants to encode information (e.g. `USER_ADMIN_ROLE = 1`).
- Use of string constants as field names for data array access.

## Reasons for the Problem
Developers create primitive fields rather than new classes out of convenience. Primitives simulate types through numbered or string constants, and fields use arrays with string constant indices instead of proper data structures.

## Treatment
- **Replace Data Value with Object** -- group related primitive fields into dedicated classes with associated behavior.
- **Introduce Parameter Object** / **Preserve Whole Object** -- for primitive fields used in method parameters.
- **Replace Type Code with Class** / **Replace Type Code with Subclasses** / **Replace Type Code with State/Strategy** -- when complicated data is encoded in variables.
- **Replace Array with Object** -- when arrays contain mixed variables.

## Payoff
- Code becomes more flexible thanks to use of objects instead of primitives.
- Improved code organization and understandability.
- Easier duplicate code detection.

## When to Ignore
- Performance-critical code paths where object allocation overhead is measurable and primitives are justified by profiling data.
- Simple local variables with short lifetimes that do not cross API boundaries.
- Interop or serialization boundaries where primitives are required by the protocol or format.

## Related

### Refactoring Techniques
- Replace Data Value with Object
- Introduce Parameter Object
- Replace Type Code with Class
- Replace Type Code with State/Strategy
- Replace Array with Object

### Design Patterns That Prevent This Smell
- Strategy -- replaces type-coded behavior with proper objects
- State -- replaces state-encoding primitives with state objects
- Flyweight -- makes small value objects efficient enough to replace primitives
