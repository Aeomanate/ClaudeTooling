# Smell: Incomplete Library Class
Category: Couplers
Source: https://refactoring.guru/smells/incomplete-library-class

## Signs and Symptoms
Sooner or later, libraries stop meeting user needs. The only solution to the problem -- changing the library -- is often impossible since the library is read-only.

## Reasons for the Problem
The author of the library hasn't provided the features you need or has refused to implement them.

## Treatment
- **Introduce Foreign Method** -- for adding a few methods to a library class.
- **Introduce Local Extension** -- for making substantial changes to a class library.

## Payoff
Reduces code duplication (instead of creating your own library from scratch, you can still piggy-back off an existing one).

## When to Ignore
Extending a library can generate additional work if the changes to the library involve changes in code.

## Related

### Refactoring Techniques
- Introduce Foreign Method
- Introduce Local Extension

### Design Patterns That Prevent This Smell
- Adapter -- wraps an incompatible library interface to match expected contracts
- Decorator -- adds missing functionality to library classes without modifying them
- Facade -- provides a simplified, extended interface over a deficient library
