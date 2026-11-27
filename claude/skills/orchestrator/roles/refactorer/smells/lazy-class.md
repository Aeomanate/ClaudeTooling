# Smell: Lazy Class
Category: Dispensables
Source: https://refactoring.guru/smells/lazy-class

## Signs and Symptoms
Understanding and maintaining classes always costs time and money. So if a class doesn't do enough to earn your attention, it should be deleted.

## Reasons for the Problem
- A class was designed as fully functional but became ridiculously small after refactoring.
- It was designed to support future development work that never materialized.

## Treatment
- **Inline Class** -- components that are near-useless should receive this treatment.
- **Collapse Hierarchy** -- for subclasses with few functions.

## Payoff
- Reduced code size.
- Easier maintenance.

## When to Ignore
A Lazy Class is sometimes created to delineate intentions for future development. In such cases, maintain a balance between clarity and simplicity in your code.

## Related

### Refactoring Techniques
- Inline Class
- Collapse Hierarchy

### Design Patterns That Prevent This Smell
- Discipline in applying YAGNI (You Aren't Gonna Need It) and avoiding [Speculative Generality](speculative-generality.md) are the primary preventive measures.
