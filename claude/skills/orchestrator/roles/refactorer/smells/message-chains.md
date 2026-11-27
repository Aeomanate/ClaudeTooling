# Smell: Message Chains
Category: Couplers
Source: https://refactoring.guru/smells/message-chains

## Signs and Symptoms
In code you see a series of calls resembling `$a->b()->c()->d()`.

## Reasons for the Problem
Message chains occur when a client requests one object, which requests another, continuing down a chain. This creates client dependency on the navigation structure. Any modifications to these relationships require client updates.

## Treatment
- **Hide Delegate** -- removes the message chain by encapsulating intermediate objects.
- **Extract Method** + **Move Method** -- extract the end goal's functionality and relocate it to the chain's beginning.

## Payoff
- Reduces dependencies between classes in the chain.
- Decreases the amount of verbose, bloated code.

## When to Ignore
Overly aggressive delegate hiding can create code where functionality's actual location is unclear. This risks introducing the [Middle Man](middle-man.md) code smell, so balance is necessary.

## Related

### Refactoring Techniques
- Hide Delegate
- Extract Method
- Move Method

### Design Patterns That Prevent This Smell
- Facade -- provides a single entry point that hides chain navigation
- Mediator -- centralizes communication, eliminating the need for traversal chains
- Command -- encapsulates requests so clients need not navigate object graphs
