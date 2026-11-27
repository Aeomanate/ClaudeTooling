# Smell: Captured `this` in Async-Executed Lambda
Category: Couplers
Source: Stability team — recurring crash pattern triaged with null-pointer checks instead of structural lifetime safety

## Signs and Symptoms

A lambda is passed to an async mechanism — queue dispatcher, router callback, timer, thread launch — AND the lambda captures `this`, `[&]`, or `[=]` without a `std::weak_ptr` / `std::enable_shared_from_this` anchor and without a documented lifetime invariant guaranteeing the captured object outlives every possible lambda execution.

Common async mechanisms in this codebase that need scanning:

- `dp_async` / `dpAsync` / `concurrent::dp_async`
- `DpQueue::async` / `IFocusPathQueue::async`
- `router::send_query` response callback / `router::send_set` response callback
- `endpoint_base::register_subscription` handler (invoked from the message-queue dispatch cycle, not the registering call stack)
- `std::thread([this]{...})`
- Timer / scheduled callbacks

Detection grep for an audit:

```bash
grep -rnE '\->async\(\[(this|&|=)' <scope>  # VALIDATED: mr script extraction deferred
grep -rnE 'register_subscription.*\[(this|&|=)' <scope>  # VALIDATED: deferred
grep -rnE 'std::thread\(\[(this|&|=)' <scope>  # VALIDATED: deferred
grep -rnE 'send_query.*\[(this|&|=)' <scope>  # VALIDATED: deferred
```

Each hit needs classification: SAFE (with documented invariant) / RISKY (depends on assumed-but-not-documented invariant) / VIOLATION (no invariant at all).

## Reasons for the Problem

The lambda's execution time is decoupled from the dispatching call site. If the captured object is destroyed before the lambda runs, dereferencing `this` (or the captured members) accesses freed memory or a destroyed object. The resulting crashes are non-deterministic — reproducing only under specific shutdown / contention conditions — so they hit the stability team as null-pointer triage rather than at the original developer's desk.

The cost compounds across the codebase: every `[this]` capture in an async mechanism requires the maintainer to mentally reconstruct the lifetime model (who owns the dispatcher? when does the captured object die? does the destructor synchronously drain the queue?) every time they touch the surrounding code. Weak-ptr capture makes the lifetime model self-documenting.

## Treatment

**Minimum-capture-surface rule (strict, applies BEFORE picking a treatment):** capture EXACTLY what the lambda body uses, never broader. `[=]` and `[&]` blanket captures are an additional smell on top of the captured-`this` smell — they hide which members the lambda actually depends on and silently widen the lifetime surface. `[this]` is itself a smell when the lambda body reads only one or two members; the right answer is to capture those members directly, not `this`. The refactor target is always the smallest capture list that makes the lambda body compile.

Treatment ladder, in preference order:

- **Capture by value** — for small POD data (PIDs, integers, paths, copy-cheap members), capture the SPECIFIC data by value (`[pid = m_pid]`, `[path = m_path]`) instead of `[this]`. Eliminates lifetime concerns entirely AND makes the data dependency self-documenting. Preferred when possible.
- **`std::weak_ptr` to the specific object** — if the lambda needs one heap member of `this`, capture `weak_ptr` to THAT member, not the whole `this`. `lock()` inside the lambda and bail on expiry.
- **`std::enable_shared_from_this`** — only when the lambda body genuinely needs multiple `this`-members on the same atomic snapshot AND the per-member capture is too verbose. Inherit and capture `[weak = weak_from_this()]`. Leave a one-line comment naming WHY the whole object is needed.
- **`std::shared_ptr` p_impl** — convert any `std::unique_ptr<Impl>` private-implementation pointer to `std::shared_ptr<Impl>` so weak-ptr capture is possible.

Canonical write-time discipline lives in `roles/coder/cpp.md` § "Async lifetime — captured `this` in lambdas executed off the dispatching stack" — refactorer cites and applies; coder enforces at write time. The strict minimum-capture-surface rule is mirrored there.

## Payoff

- Eliminates the crash class entirely at the structural level — no runtime null-pointer-check guard needed.
- Lambda capture intent becomes self-documenting: `weak_ptr` says "may not be alive at execution"; capture-by-value says "snapshot at dispatch time"; `[this]` says "lifetime is guaranteed by an invariant named in the inline comment".
- Shutdown ordering becomes less fragile — destructors no longer need to synchronously drain every queue / join every thread for the codebase to be safe.

## When to Ignore

- The captured object is a process-singleton (lives for the entire process lifetime by construction).
- The captured object's destructor synchronously joins the worker thread / drains the queue BEFORE returning, AND this guarantee is documented inline at the destructor (RAII teardown).
- The lambda executes synchronously on the dispatching call stack (not actually async — verify, do not assume).

In each "ignore" case, leave a one-line comment at the lambda site naming which invariant holds (`// process-singleton`, `// RAII drain in ~Foo`, `// synchronous dispatch`) so future maintainers and refactorers don't re-flag the call.

## Related

### Refactoring Techniques

No standard structural refactoring — the fix is a capture-list rewrite, sometimes combined with a `std::unique_ptr<Impl>` → `std::shared_ptr<Impl>` p_impl swap when the captured object IS `this`.

### Design Patterns That Prevent This Smell

- **Observer** with weak references — subscribers register `weak_ptr` handles; publisher walks the list and skips expired entries. Removes the "who outlives whom" coupling that drives this smell in the first place.
