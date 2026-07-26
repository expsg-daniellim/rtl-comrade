# Global Invariants

These apply across the entire harness. Violating any of them produces deadlocks, silent data loss, or incorrect failure semantics.

## `EndSentinel`

`EndSentinel` is the graph's termination signal. Every node that consumes inputs must propagate it downstream after stopping. Wrong behavior here either deadlocks the graph (node never stops) or prematurely terminates it (sentinel fires too early).

One sentinel is sent per incoming edge, so a port fed by several edges ends only once it has seen one from every one of them. `Port` counts them against `source_n`; a port that ended on the first would drop everything its other sources had yet to send.

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

## Input ports are readable only during `get_inputs()`

`Node.run` enables reads on every input port immediately before calling the input contract and disables them immediately after. Outside that window `Port.get()` and `Port.try_get()` raise `IllegalGetAccessError` without touching the queue, and the node treats it as fatal.

The window exists because a deferred read is silent data loss: a `ContractPort` captured during one `get_inputs()` and awaited later — from a background task, or from an output contract's `process_outputs` — would consume a payload the *next* invocation was owed, desyncing the stream far from the code that caused it. An output contract can read `port.state`, `has_ended()`, and `branch_labels`, but never the queue. Do not widen the window to "while the node is running"; that reintroduces exactly the race it rules out. See [harness/port.md](harness/port.md).

## Input ports take several edges only as alternatives

Multiple upstream edges may feed one input port only when their sources are mutually exclusive — proven by `branch_labels`, some arm of a common origin ruling out every pair at once. That is an alternation, not a merge: at most one source ever carries data. Anything else is a configuration error, rejected at validation time with `overloaded_srcs`. Exclusivity comes from `if`/`else` and `match`-case siblings that the AST can prove, or from an `output_groups` declaration; distinct arms are not enough, since two independent `if`s produce two arms that both fire — see [harness/branch_labels.md](harness/branch_labels.md).

## Branch-legitimate termination is not a mismatch

A node whose inputs come from different branch arms may see one arm end while another stays live. This is a normal branch outcome, not a desync. Contracts distinguish it via each port's `branch_labels`, assigned by the label-propagation pass in `Graph.from_config`. Do not reintroduce a flat "some ended, some have data" mismatch check that ignores labels — see [harness/branch_labels.md](harness/branch_labels.md).
