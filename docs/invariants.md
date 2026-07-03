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

## External port names are distinct from `run(...)` parameter names

The graph addresses inputs by **external port name**; the module is called by its **Python parameter name**. They differ only when a parameter carries a builtin/keyword-avoiding trailing underscore (`list_` → port `list`). `structure.py` records both, and `node.py` re-keys inbound payloads from external name to `param` immediately before `run(**inputs)` — the single translation point. Everything graph-facing (edges, CLI, `contract_port_mappings`, validation) must use external names; only the final module call uses parameter names. Do not introduce a second translation site.

## Input ports are single-source

Multiple upstream edges feeding the same input port on a node is a configuration error, not a merge. The harness rejects this at validation time with an "overloaded input" error.

## Branch-legitimate termination is not a mismatch

A node whose inputs come from different branch arms may see one arm end while another stays live. This is a normal branch outcome, not a desync. Contracts distinguish it via each port's `branch_labels`, assigned by the label-propagation pass in `Graph.from_config`. Do not reintroduce a flat "some ended, some have data" mismatch check that ignores labels — see [harness/branch_labels.md](harness/branch_labels.md).
