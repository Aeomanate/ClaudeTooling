# Refactorer - Python-specific rules

Part of the orchestrator/refactorer. Load when the scan touches Python
files, alongside `rules.md`'s language-agnostic R-rules. R6 and R8 live
here; every other R-rule is language-agnostic and stays in `rules.md`.

### R6: ABSOLUTE-IMPORTS

**Statement:** Every import sits at the top of the file and is absolute from the package root (`from pkg.X import ...`); an `import` inside a function body, or a `from .` / `from ..` relative import, is a violation unless it is the documented lazy-loading exception.
- **Exception:** an entry point deferring an import as an optimization, where the package is needed by only a subset of commands. Not a circular-dependency workaround, and never converted to top-level.
- A circular import is broken by refactoring the modules, never worked around with a deferred import.

```
BAD:
def f():
	from pkg.logger import warn
	warn("...")

GOOD:
from pkg.logger import warn

def f():
	warn("...")
```

A deferred import signals coupling between modules, and the fix is module
extraction - move the shared logic to a third module both can import at the
top level:

```
# Symptom:
# module_a.py: from pkg.module_b import X  (top-level)
# module_b.py: from pkg.module_a import Y  (deferred, inside function)

# Diagnosis: X and Y are shared concerns that belong in neither module

# Fix: extract to module_c.py
# module_a.py: from pkg.module_c import X  (top-level)
# module_b.py: from pkg.module_c import Y  (top-level, deferral gone)
```

- A deferral that resists removal is a function-, class- or module-extraction candidate, in that order.
- Bad: keeping a deferred import as the answer - it masks an architectural problem rather than solving it.

### R8: RAW-OR-F-STRINGS

**Statement:** Regex patterns and any string carrying backslash escapes are raw strings (`r'...'`), and string building uses f-strings; a changed line with `\\` where `r''` works, or `.format()`/`%`-style building where an f-string would, is a violation.
