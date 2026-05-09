# `structure.py`

Source: [src/rtl_comrade/structure.py](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade/structure.py)

## Role

This file performs static analysis of module `run(...)` methods so the harness can infer:

- input ports from the function signature
- statically known output ports from the function AST

## See Also

- [README.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/README.md)
- [graph.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/graph.md)
- [node.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/node.md)
- [config.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/config.md)

## Main Responsibilities

- inspect `Module.run` signatures
- record parameter names, annotations, and default values
- parse the source of `run(...)`
- walk the AST while avoiding nested function bodies
- collect statically known emitted port names
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
- only top-level `return` and `yield` forms are inspected; nested helper functions are excluded
- dynamic port names reduce what the graph validator can prove
- changes here can silently alter both runtime behavior and config-validation behavior
