# `structure.py`

Source: [src/rtl_comrade/structure.py](../../src/rtl_comrade/structure.py)

## Role

This file performs static analysis of module methods so the harness can infer:

- input ports from the `run(...)` signature
- statically known output ports from the `run(...)` and `finalise()` ASTs

## See Also

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

## Caveats

- the analysis is intentionally conservative
- `finalise()` emits are folded into the same `emits`/`definite_emits` as `run(...)`; it is analysed only when present and callable, mirroring the runtime detection in `node.py`
- only top-level `return` and `yield` forms are inspected; nested helper functions are excluded
- dynamic port names reduce what the graph validator can prove
- non-`rtl_comrade` failures during signature inspection, source retrieval, or AST parsing are logged with `exc_info=e` so tracebacks remain available
- changes here can silently alter both runtime behavior and config-validation behavior
