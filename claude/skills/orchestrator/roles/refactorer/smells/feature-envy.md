# Smell: Feature Envy
Category: Couplers
Source: https://refactoring.guru/smells/feature-envy

## Signs and Symptoms
A method accesses the data of another object more than its own data.

## Reasons for the Problem
This smell emerges when fields migrate to a data class. The underlying issue is that related operations haven't moved alongside the data, creating misalignment between where data lives and where it's used.

## Treatment
- **Move Method** -- transfer the entire method to the appropriate class.
- **Extract Method** -- isolate the problematic portion accessing external data, then relocate that segment.
- When multiple classes' data is involved, extract and split the operation into parts placed where their respective data resides.

## Payoff
- Reduces code duplication through centralized data handling.
- Improves organization by collocating methods with their data.

## When to Ignore
When behavior is intentionally separated from data classes to enable dynamic behavior changes, as seen in design patterns like Strategy and Visitor.

## Related

### Refactoring Techniques
- Move Method
- Extract Method

### Design Patterns That Prevent This Smell
- Observer -- decouples data producers from consumers, reducing cross-class data access
- Strategy -- keeps algorithm logic co-located with the data it operates on
- Visitor -- formalizes operations on foreign data into a well-defined protocol
