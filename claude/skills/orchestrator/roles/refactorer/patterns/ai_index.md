# Refactoring Knowledge Base — AI Index

Read this file first. Each line is a trigger plus the pattern or technique it
points to. This index is the whole catalog — there are no per-pattern files
to open next.

---

## Decision Trees — When Multiple Patterns Apply

### Behavioral algorithm selection
- Long if/elif/switch on TYPE, algorithms independent, caller picks → **Strategy**
- Long if/elif/switch on internal STATE, object changes its own behavior → **State**
- Simple polymorphism swap, no separate algorithm objects needed → **Replace Conditional with Polymorphism**

### Object creation
- Complex constructor (5+ params), many optional, fluent API → **Builder**
- Subclass must determine the concrete type created → **Factory Method**
- Families of related objects must be created together → **Abstract Factory**

### Wrapping / extending behavior
- Add behavior without modifying the class, multiple stackable behaviors → **Decorator**
- Add behavior without modifying the class, single concern (access, lazy load, remote) → **Proxy**
- Incompatible interface must plug in unchanged → **Adapter**

### Simplifying complex systems
- Too many classes to interact with, callers need one simple entry point → **Facade**
- Too many classes to interact with, objects must coordinate bidirectionally → **Mediator**

### Code duplication
- Sibling classes share a skeleton, differ only in steps → **Template Method**
- Sibling classes are fully interchangeable, no fixed skeleton → **Strategy**

---

## Design Patterns

### Creational
- Produce families of related objects without specifying concrete classes → **Abstract Factory**
- Construct complex objects step by step, varying the representation → **Builder**
- Superclass defines creation, subclasses alter the type created → **Factory Method**
- Copy an object without depending on its concrete class → **Prototype**
- One instance, one global access point → **Singleton**

### Structural
- Incompatible interfaces must collaborate unchanged → **Adapter**
- Split one large class into two hierarchies (abstraction / implementation) that evolve independently → **Bridge**
- Compose objects into trees, treat individual and grouped objects alike → **Composite**
- Attach behaviors to an object by wrapping it, stackable → **Decorator**
- Provide one simplified interface to a complex subsystem → **Facade**
- Fit more objects into memory by sharing common state → **Flyweight**
- Control access to another object, single concern → **Proxy**

### Behavioral
- Pass a request along a chain of handlers, each decides to process or forward → **Chain of Responsibility**
- Turn a request into a stand-alone object, enabling queuing/logging/undo → **Command**
- Traverse a collection without exposing its internal representation → **Iterator**
- Reduce chaotic dependencies by forcing objects to collaborate through one mediator → **Mediator**
- Save and restore an object's state without exposing its internals → **Memento**
- Notify many objects about events, unknown at compile time → **Observer**
- Object alters its behavior when internal state changes → **State**
- Family of algorithms in separate classes, interchangeable at runtime → **Strategy**
- Skeleton of an algorithm in a superclass, subclasses override specific steps → **Template Method**
- Separate an algorithm from the objects it operates on → **Visitor**

---

## Refactoring Techniques

### Composing Methods
- Groupable code fragment → extract into a method → **Extract Method**
- Hard-to-understand expression → put its result in a named variable → **Extract Variable**
- Method just delegates → replace calls with the method's own content → **Inline Method**
- Temp holds a simple expression → replace the temp with the expression → **Inline Temp**
- Parameter gets reassigned inside the method → use a local variable instead → **Remove Assignments to Parameters**
- Long method, intertwined locals → turn the method into its own class → **Replace Method with Method Object**
- Local variable holds a query result → extract the query into a method → **Replace Temp with Query**
- One temp reused for unrelated values → split into separate variables → **Split Temporary Variable**
- Better algorithm exists for a method's body → **Substitute Algorithm**

### Moving Features Between Objects
- Class does the work of two → split by responsibility → **Extract Class**
- Client navigates through object relationships → add a delegating method → **Hide Delegate**
- Near-empty class contributes little → **Inline Class**
- Utility class can't be modified, needs one more method → **Introduce Foreign Method**
- Utility class needs several more methods → subclass or wrap it → **Introduce Local Extension**
- Field used more by another class than its own → **Move Field**
- Method used more by another class than its own → **Move Method**
- Class only forwards calls to another class → let callers call the end object directly → **Remove Middle Man**

### Organizing Data
- Bidirectional association, one direction unused → **Change Bidirectional Association to Unidirectional**
- Small, rarely-changed reference object → turn into a value object → **Change Reference to Value**
- Two classes each need the other's features, no association exists → **Change Unidirectional Association to Bidirectional**
- Many identical instances of a value object → share a single reference object → **Change Value to Reference**
- GUI class also holds domain data → separate the data, sync via Observer → **Duplicate Observed Data**
- Collection exposed directly → return read-only, add explicit add/delete methods → **Encapsulate Collection**
- Public field → make it private with getters/setters → **Encapsulate Field**
- Mixed-type array → object with a field per element → **Replace Array with Object**
- Primitive field needs its own behavior → **Replace Data Value with Object**
- Meaningful number appears as a literal → **Replace Magic Number with Symbolic Constant**
- Subclasses differ only in constant-returning methods → replace with parent-class fields → **Replace Subclass with Fields**
- Type code never used in a conditional → replace with a dedicated class → **Replace Type Code with Class**
- Type code drives behavior, subclassing not possible → replace with a state/strategy object → **Replace Type Code with State/Strategy**
- Type code drives behavior, subclassing possible → one subclass per value → **Replace Type Code with Subclasses**
- Private field accessed directly even inside its own class → route through getter/setter → **Self Encapsulate Field**

### Simplifying Conditional Expressions
- Multiple conditionals lead to the same result → combine into one expression → **Consolidate Conditional Expression**
- Identical code in every branch → move it outside the conditional → **Consolidate Duplicate Conditional Fragments**
- Complex condition, then-branch, or else-branch → extract each into its own method → **Decompose Conditional**
- Implicit assumption about state → make it an explicit check → **Introduce Assertion**
- Null checks scattered around a value → return a null object with default behavior instead → **Introduce Null Object**
- Boolean flag controls loop/method flow → replace with break/continue/return → **Remove Control Flag**
- Conditional branches on an object's type → replace with subclasses and polymorphism → **Replace Conditional with Polymorphism**
- Nested conditionals bury the main path → isolate special cases as early-return guards → **Replace Nested Conditional with Guard Clauses**

### Simplifying Method Calls
- Method needs data it doesn't have → **Add Parameter**
- Method unused outside its own hierarchy → make it private/protected → **Hide Method**
- Repeating group of parameters → replace with one object → **Introduce Parameter Object**
- Similar methods differing only in one value → merge, pass the value as a parameter → **Parameterize Method**
- Caller extracts several values from an object just to pass them → pass the whole object → **Preserve Whole Object**
- Parameter never used in the method body → **Remove Parameter**
- Setter exists for a field that should be immutable after creation → **Remove Setting Method**
- Method name doesn't convey its purpose → **Rename Method**
- Constructor logic is complex → replace with a factory method → **Replace Constructor with Factory Method**
- Special error return value → throw an exception instead → **Replace Error Code with Exception**
- Exception used for ordinary control flow → check the condition first instead → **Replace Exception with Test**
- Branches driven by a parameter value → one named method per branch → **Replace Parameter with Explicit Methods**
- Parameter is always the result of the same query → call the query inside the method → **Replace Parameter with Method Call**
- One method both returns a value and mutates state → split into two methods → **Separate Query from Modifier**

### Dealing with Generalization
- Subclass is practically identical to its superclass → **Collapse Hierarchy**
- Multiple clients use the same subset of a class's interface → extract that subset into an interface → **Extract Interface**
- Feature used only in certain cases → move it into a new subclass → **Extract Subclass**
- Two classes share fields and methods, no common parent → **Extract Superclass**
- Similar algorithm structure, varying steps, no shared superclass yet → **Form Template Method**
- Identical constructor code across subclasses → move it to the superclass constructor → **Pull Up Constructor Body**
- Identical field across subclasses → **Pull Up Field**
- Identical (or made-identical) method across subclasses → **Pull Up Method**
- Field used only by a few subclasses → move it down from the superclass → **Push Down Field**
- Method used only by a few subclasses → move it down from the superclass → **Push Down Method**
- Class only delegates to another, no polymorphism needed → inherit instead → **Replace Delegation with Inheritance**
- Subclass uses only part of its superclass → replace inheritance with composition → **Replace Inheritance with Delegation**

---

## Code Smells

See `../smells/` — 24 files, one per smell, each with a "Related" section
naming the technique or pattern that fixes it. Look up the smell first when
a scan flags one; look up the trigger here when reasoning from a design
decision instead.
