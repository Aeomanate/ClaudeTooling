# Smell: Middle Man
Category: Couplers
Source: https://refactoring.guru/smells/middle-man

## Signs and Symptoms
If a class performs only one action, delegating work to another class, why does it exist at all?

## Reasons for the Problem
- This smell can result from overzealous elimination of Message Chains.
- A class's useful work gradually moves to other classes, leaving it as an empty shell that merely delegates.

## Treatment
- **Remove Middle Man** -- apply when most of a class's methods simply delegate to another class.

## Payoff
Less bulky code.

## When to Ignore
Don't delete middle man classes created for specific reasons:
- A middle man may exist to avoid interclass dependencies.
- Some design patterns intentionally create middle man (e.g. Proxy or Decorator).

## Related

### Refactoring Techniques
- Remove Middle Man
- Inline Method

### Design Patterns That Prevent This Smell
- Balance is key: Proxy and Decorator intentionally use delegation, so not every middle man is a smell. Avoid creating delegation-only classes when no access control, lazy loading, or behavioral extension justifies them.
