# Code Style

## Comments

Write comments only when the *why* is non-obvious. A comment that restates what the next line does is noise.

**Length.** Keep each comment to one line. If a thought genuinely needs two lines, ask whether both halves are load-bearing; usually one can be cut or folded in.

**Placement.** Attach a note to the specific line it explains, not as a block above the whole section. A block comment above five lines says the same thing five times. An inline comment on the one surprising line is precise.

**What to capture.** Hidden constraints, invariants that aren't obvious from the types, and workarounds for specific bugs. Not summaries of what the code does, not the name of the caller, not a description of the block that follows.

## Expressions

Prefer single-line expressions where they fit readably. Chained method calls and list comprehensions with a filter clause do not need to be broken across multiple lines just because they are long. The existing codebase puts the `plugin_name` derivation and the `to_get` list comprehension on one line each — follow that precedent.
