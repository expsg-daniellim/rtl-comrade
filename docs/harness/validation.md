# `validation.py`

Source: [src/rtl_comrade/validation.py](../../src/rtl_comrade/validation.py)

## Role

This file provides the harness’s static graph checks before execution begins.

## See Also

- [README.md](README.md)
- [config_graph.md](config_graph.md) — calls `validate_acyclic`
- [graph.md](graph.md) — calls `validate_no_static_deadlock`
- [config.md](config.md)
- [contract_default.md](contract_default.md)

## Main Responsibilities

- detect cycles in the configured graph
- detect some deadlock-prone graph shapes before runtime
- return structured validation results for graph assembly

## Main Functions

- `validate_acyclic(nodes, edges)`: DFS-based cycle check over node ids; takes raw node and edge lists so it is independent of any higher-level config type
- `validate_no_static_deadlock(graph)`: conservative first-run reachability and input-satisfaction checks

## Place In The System

This module provides two functions called at different points in the loading pipeline:

- `validate_acyclic` is called from `GraphConfig.from_file_config` in [config_graph.py](../../src/rtl_comrade/config_graph.py), before any plugin classes are loaded
- `validate_no_static_deadlock` is called from `Graph.from_config` in [graph.py](../../src/rtl_comrade/graph.py), after nodes have been instantiated and edges wired

Both functions share the same purpose: reject obviously bad graphs before execution starts, not recover from them after work has begun.

## Static Deadlock Checks

The current implementation checks:

- every first-run-required input port has some incoming edge
- at least one node is source-capable
- every node is reachable from some source-capable node

An input is first-run-required when it has no Python default **or** its destination is marked `required: true` in the graph config. A required port blocks at runtime even when it carries a default, so it is not satisfiable locally: a node whose only inputs are required (or default-less) is not source-capable.

## Validation Philosophy

This layer is intentionally front-loaded and conservative.

- structural graph problems should be found before execution
- a graph that is known to be invalid should not be allowed to start
- the harness prefers fail-fast validation here rather than best-effort runtime recovery later

## Caveats

- the analysis is conservative and not deeply contract-aware
- the implementation is better understood as "obvious structural deadlock screening" than as a complete proof of runtime liveness
