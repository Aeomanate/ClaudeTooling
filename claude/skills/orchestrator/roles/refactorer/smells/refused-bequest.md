# Smell: Refused Bequest
Category: Object-Orientation Abusers
Source: https://refactoring.guru/smells/refused-bequest

## Signs and Symptoms
If a subclass uses only some of the methods and properties inherited from its parents, the hierarchy is off-kilter. The unneeded methods may simply go unused or be redefined and give off exceptions.

## Reasons for the Problem
Someone was motivated to create inheritance between classes only by the desire to reuse the code in a superclass. But the superclass and subclass are completely different.

## Treatment
- **Replace Inheritance with Delegation** -- eliminate inheritance when the subclass and superclass have nothing in common.
- **Extract Superclass** -- remove unneeded fields and methods; create a new superclass containing only shared code, with both classes inheriting from it.

## Payoff
Improves code clarity and organization. You will no longer have to wonder why the Dog class is inherited from the Chair class (even though they both have 4 legs).

## When to Ignore
- When the inheritance hierarchy is imposed by a framework and you cannot change the base class, leaving a few inherited methods unused is acceptable.
- Minor cases where only one or two rarely-used convenience methods are inherited but the rest of the contract fits well.

## Related

### Refactoring Techniques
- Replace Inheritance with Delegation
- Extract Superclass
- Push Down Method
- Push Down Field

### Design Patterns That Prevent This Smell
- Strategy -- favors composition over inheritance for sharing behavior
- Decorator -- adds behavior through wrapping rather than inheriting unused members
- Composite -- models part-whole relationships without forcing unrelated inheritance
