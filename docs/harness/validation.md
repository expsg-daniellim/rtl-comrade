# `validation.py`

Source: [src/rtl_comrade/validation.py](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade/validation.py)

## Role

This file provides the harness’s static graph checks before execution begins.

## See Also

- [README.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/README.md)
- [graph.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/graph.md)
- [config.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/config.md)
- [contract_default.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/contract_default.md)

## Main Responsibilities

- detect cycles in the configured graph
- detect some deadlock-prone graph shapes before runtime
- return structured validation results for graph assembly

## Main Functions

- `validate_acyclic(config)`: DFS-based cycle check over node ids
- `validate_no_static_deadlock(graph)`: conservative first-run reachability and input-satisfaction checks

## Place In The System

This is the harness validation layer used by `graph.py` before node tasks are launched.

Its purpose is to reject obviously bad graphs before runtime, not to recover from them after execution has already started.

## Static Deadlock Checks

The current implementation checks:

- every non-default input port has some incoming edge
- at least one node is source-capable
- every node is reachable from some source-capable node

## Validation Philosophy

This layer is intentionally front-loaded and conservative.

- structural graph problems should be found before execution
- a graph that is known to be invalid should not be allowed to start
- the harness prefers fail-fast validation here rather than best-effort runtime recovery later

## Caveats

- the analysis is conservative and not deeply contract-aware
- the implementation is better understood as "obvious structural deadlock screening" than as a complete proof of runtime liveness
