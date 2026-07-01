# `structure.py`

Source: [src/rtl_comrade/structure.py](../../src/rtl_comrade/structure.py)

## Role

This file performs static analysis of module methods so the harness can infer:

- input ports from the `run(...)` signature
- statically known output ports from the `run(...)` and `finalise()` ASTs
- the branch-arm partition of those output ports (which ports are conditional alternatives)

## See Also

- [branch_labels.md](branch_labels.md) — how arms feed control-dependence propagation

- [README.md](README.md)
- [graph.md](graph.md)
- [node.md](node.md)
- [config.md](config.md)

## Main Responsibilities

- inspect `Module.run` signatures
- record parameter names, annotations, and whether each parameter has a default
- parse the source of `run(...)` and, when present and callable, `finalise()`
- walk each AST while avoiding nested function bodies
- collect statically known emitted port names from both methods
- detect whether the output-port set is definite or only partial

## Place In The System

This is the harness reflection layer for modules. `node.py` depends on it to construct ports, and `graph.py` depends on it to validate source-port references.

## What Counts As An Emit

- a non-`None` non-tuple return/yield implies the `"default"` port
- a tuple return/yield with a static string first element contributes that named port
- a tuple with a non-string constant port name is rejected
- a tuple with a dynamic first element is allowed, but weakens validation by setting `definite_emits = False`

## Arm Determination

`ModuleStructure.arms` partitions the statically-named output ports by their guarding branch-path: ports emitted in mutually-exclusive `if`/`else` or `match` arms land in distinct arms, a loop body forms one conditional arm, each emit inside a `try` region is its own optional arm, and ports emitted unconditionally or under several distinct guards belong to no arm. Nested scopes (`def`/`class`) are excluded, as before.

`resolve_arms` reconciles the AST arms with an optional module `output_groups` declaration (a group→ports mapping where a `REST` member list means "all remaining outputs"). The matrix:

| `definite_emits` | `output_groups` | result |
|---|---|---|
| yes | no | AST arms |
| yes | yes | AST arms, cross-checked against the declaration (fatal on mismatch) |
| no | yes | declaration fills the dynamic ports; must agree with the AST on the named ports (fatal on mismatch) |
| no | no | undeterminable — warn, and treat all outputs as one shared arm |

The resolved arms are consumed by the propagation pass in [graph.md](graph.md). See [branch_labels.md](branch_labels.md).

## Caveats

- the analysis is intentionally conservative
- `finalise()` emits are folded into the same `emits`/`definite_emits` as `run(...)`; it is analysed only when present and callable, mirroring the runtime detection in `node.py`
- only top-level `return` and `yield` forms are inspected; nested helper functions are excluded
- dynamic port names reduce what the graph validator can prove
- non-`rtl_comrade` failures during signature inspection, source retrieval, or AST parsing are logged with `exc_info=e` so tracebacks remain available
- changes here can silently alter both runtime behavior and config-validation behavior
