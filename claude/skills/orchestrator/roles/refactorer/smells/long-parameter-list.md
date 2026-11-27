# Smell: Long Parameter List
Category: Bloaters
Source: https://refactoring.guru/smells/long-parameter-list

## Signs and Symptoms
More than three or four parameters for a method.

## Reasons for the Problem
Methods may accumulate long parameter lists when multiple algorithms merge into one function, or when efforts to reduce class dependencies result in passing created objects as parameters rather than maintaining internal references.

## Treatment
- **Replace Parameter with Method Call** -- use when parameter values are method call results from another object.
- **Preserve Whole Object** -- pass the object itself instead of passing multiple extracted data elements as separate parameters.
- **Introduce Parameter Object** -- group related parameters from different sources into a single parameter object.

## Payoff
- More readable, shorter code.
- Refactoring may reveal previously unnoticed duplicate code.

## When to Ignore
Don't get rid of parameters if doing so would cause unwanted dependency between classes.

## Related

### Refactoring Techniques
- Replace Parameter with Method Call
- Preserve Whole Object
- Introduce Parameter Object

### Design Patterns That Prevent This Smell
- Builder -- replaces long constructor/method parameter lists with step-by-step construction
- Factory Method -- encapsulates complex creation logic, reducing parameter passing
