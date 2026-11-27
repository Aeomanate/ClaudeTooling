# Smell: Data Clumps
Category: Bloaters
Source: https://refactoring.guru/smells/data-clumps

## Signs and Symptoms
Sometimes different parts of the code contain identical groups of variables (such as parameters for connecting to a database). These clumps should be turned into their own classes.

## Reasons for the Problem
These data groups typically stem from poor program structure or duplicated code patterns. A good test: remove one value from the group -- if the remaining values lose meaning, they should be combined into an object.

## Treatment
- **Extract Class** -- move repeated class fields into their own class.
- **Introduce Parameter Object** -- convert repeated method parameters into a class.
- **Preserve Whole Object** -- pass entire data objects instead of individual fields to methods.
- Move operations on these fields to the data class itself.

## Payoff
- Improves code organization and understanding, with related operations consolidated in one location rather than scattered throughout.
- Reduces overall code size.

## When to Ignore
Passing an entire object in the parameters of a method, instead of passing just its values (primitive types), may create an undesirable dependency between the two classes.

## Related

### Refactoring Techniques
- Extract Class
- Introduce Parameter Object
- Preserve Whole Object

### Design Patterns That Prevent This Smell
- Builder -- encapsulates related construction parameters into a structured builder
- Composite -- groups related objects into tree structures, avoiding loose parameter groups
