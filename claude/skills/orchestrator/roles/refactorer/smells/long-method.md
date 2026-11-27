# Smell: Long Method
Category: Bloaters
Source: https://refactoring.guru/smells/long-method

## Signs and Symptoms
A method contains too many lines of code. Generally, any method longer than ten lines should make you start asking questions.

## Reasons for the Problem
Code continuously gets added to methods without removal. Developers find it easier to add lines to an existing method than to create new ones, leading to accumulated complexity and spaghetti code.

## Treatment
- **Extract Method** -- primary technique for reducing method body length.
- **Replace Temp with Query** -- addresses interference from local variables.
- **Introduce Parameter Object** -- handles parameter-related obstacles.
- **Preserve Whole Object** -- alternative approach for parameter issues.
- **Replace Method with Method Object** -- used when other techniques are insufficient.
- **Decompose Conditional** -- specifically for conditional operators.

## Payoff
Classes with short methods live longest. The longer a method or function is, the harder it becomes to understand and maintain it. Long methods also hide duplicate code more easily.

## When to Ignore
- Complex algorithms (e.g., state machines, mathematical computations) that lose clarity when split into smaller pieces.
- Methods consisting primarily of a single declarative structure (e.g., a long switch mapping or configuration builder) where extraction would scatter related logic without improving readability.

## Related

### Refactoring Techniques
- Extract Method
- Replace Temp with Query
- Replace Method with Method Object
- Decompose Conditional

### Design Patterns That Prevent This Smell
- Strategy -- delegates variant behavior to separate classes, keeping methods focused
- Command -- encapsulates requests as objects, breaking monolithic methods into discrete actions
- Template Method -- splits algorithm steps across overridable methods
