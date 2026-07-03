# Code Style

## Type annotations

Omit the space before the colon in all annotation contexts — function parameters, return types, and module-level variable annotations:

```python
def run(self, x:int, y:str = "default") -> bool:
log:HarnessLogger = cast(HarnessLogger, structlog.get_logger())
```

This applies consistently; do not add a space before the colon anywhere.

## Spelling

Use British spellings: `finalise` not `finalize`, `initialise` not `initialize`.

## Comments

Write comments only when the *why* is non-obvious. A comment that restates what the next line does is noise.

**Length.** Keep each comment to one line. If a thought genuinely needs two lines, ask whether both halves are load-bearing; usually one can be cut or folded in.

**Placement.** Attach a note to the specific line it explains, not as a block above the whole section. A block comment above five lines says the same thing five times. An inline comment on the one surprising line is precise.

**What to capture.** Hidden constraints, invariants that aren't obvious from the types, and workarounds for specific bugs. Not summaries of what the code does, not the name of the caller, not a description of the block that follows.

**Before decorators.** When a class or function needs a stand-alone explanatory note (rather than an inline remark), place it as a `#` comment on the line immediately before the first decorator, not between the decorator and the `class`/`def` keyword.

## Docstrings

**Blank line after the closing `"""`-line of the summary.** Every method body starts with a blank line separating it from the docstring:

```python
def foo(self) -> int:
    """Return the answer."""

    return 42
```

**`Returns: None.` in `__init__`.** Document the return explicitly even though `__init__` always returns `None`. This keeps the format uniform across all methods that have a docstring.

## Naming

Do not prefix names with a leading underscore — not functions, methods, module-level names, or `self.` attributes. Dunders (`__init__`, `__post_init__`, …) are the only exception.

**Discarded names.** When unpacking a tuple and a bound name is never used, name it `_` (Rust style) rather than inventing a descriptive name you then ignore. This is a discard, not a leading-underscore prefix, so it is exempt from the rule above. Rename only the unused element: `_, table = mod.finalise()` when the port is discarded, `port, _ = mod.finalise()` when the payload is.

## Expressions

Prefer single-line expressions where they fit readably. Chained method calls and list comprehensions with a filter clause do not need to be broken across multiple lines just because they are long. The existing codebase puts the `plugin_name` derivation and the `to_get` list comprehension on one line each — follow that precedent.

**Generators and comprehensions.** Use spaces inside the brackets: `[ x for x in foo ]`, `{ k: v for k, v in items }`, `( x for x in foo )`.

## Classes

**`@dataclass` with a custom `__init__`.** When a class needs `slots=True` (or auto-generated `__repr__`/`__eq__`) but requires non-trivial construction logic, apply `@dataclass(slots=True)` and write the `__init__` by hand. The decorator handles the boilerplate; the hand-written `__init__` handles the logic. Do not add `__post_init__` as an intermediate step.
