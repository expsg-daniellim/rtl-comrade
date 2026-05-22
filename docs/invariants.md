# Global Invariants

These apply across the entire harness. Violating any of them produces deadlocks, silent data loss, or incorrect failure semantics.

## `EndSentinel`

`EndSentinel` is the graph's termination signal. Every node that consumes inputs must propagate it downstream after stopping. Wrong behavior here either deadlocks the graph (node never stops) or prematurely terminates it (sentinel fires too early).

## Graph validation is fail-fast

Malformed graphs must be rejected before `Graph.run()` is called. Runtime surprises from config errors are not acceptable. All structural checks belong in `validation.py`.

## Logging is part of the failure model

The log level determines exit behavior — it is not cosmetic.

| Level | Behavior |
|---|---|
| `DEBUG` / `INFO` / `WARNING` | Normal observability; no effect on exit |
| `ERROR` | Deferred failure — best-effort completion, then non-zero exit |
| `CRITICAL` / `FATAL` | Immediate `SystemExit(1)` |

Do not demote a `CRITICAL` to `ERROR` or vice versa without understanding the exit-code contract.

## `structure.py` output-port inference is intentionally conservative

`ModuleStructure` statically infers output ports from the `run(...)` AST. It only recognises static string literals as port names. Dynamic port names are allowed at runtime but set `definite_emits = False`, which weakens graph validation. Do not change the analyzer to be more permissive without understanding what validation guarantees are lost.

## Input ports are single-source

Multiple upstream edges feeding the same input port on a node is a configuration error, not a merge. The harness rejects this at validation time with an "overloaded input" error.
