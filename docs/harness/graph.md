# `graph.py`

Source: [src/rtl_comrade/graph.py](../../src/rtl_comrade/graph.py)

## Role

This file is the top-level harness coordinator. It turns config data into a runnable graph of `Node` objects.

## See Also

- [README.md](README.md)
- [__main__.md](__main__.md)
- [config.md](config.md)
- [loader.md](loader.md)
- [node.md](node.md)
- [validation.md](validation.md)
- [logging.md](logging.md)

## Main Responsibilities

- load module and contract plugin classes from a `GraphConfig`
- instantiate nodes
- create virtual `ModuleCLI` nodes from `GraphConfig.cli_srcs`
- validate edge port names against module structure
- run static deadlock checks before execution
- launch all nodes concurrently

## Key Entry Points

- `Graph.from_config(config)`: construct the runtime graph from an already-loaded `GraphConfig`
- `Graph.construct_run(config, cleanup)`: static method; returns a closure whose signature matches `config.sig`; when invoked with CLI kwargs, constructs the `Graph` via `from_config`, injects values into CLI nodes, runs the graph, then calls `cleanup()`

## Place In The System

If `__main__.py` is the process bootstrap, `graph.py` is the harness assembly layer. It bridges config, plugin loading, node construction, and validation into one runnable object.

It is also the main fail-fast boundary of the harness. This is where obviously bad graphs should be rejected before any runtime work begins.

## Notable Behaviors

- structural config checks (duplicate node ids, invalid dst node, unused edge sources, cycles) are performed in `GraphConfig.from_file_config` before `Graph.from_config` is reached; see [config_graph.md](config_graph.md)
- `Graph.from_config` handles only checks that require loaded plugin classes: invalid module/contract names, invalid port names, overloaded inputs, and static deadlock
- missing modules or contracts are treated as fatal configuration errors
- source port names are checked against statically inferred emits when `ModuleStructure` can prove them
- duplicate incoming connections to the same destination input are rejected
- static deadlock checks run before execution starts
- node tasks are launched together via `asyncio.gather(...)`
- `GraphConfigSrcCLI` edges are normalised into `GraphConfig.cli_srcs` and `GraphConfig.sig` during `GraphConfig.from_file_config`; the corresponding virtual `ModuleCLI` nodes are created from `cli_srcs` during `Graph.from_config`; each injects one value into one destination port
- error-level and critical-level logs emitted during graph assembly intentionally participate in the harness failure model: `ERROR` defers failure until the run ends, while `CRITICAL` aborts immediately

## Validation Philosophy

Graph loading and validation are intentionally strict.

- if the graph shape is invalid, the preferred behavior is to stop before execution
- fatal checks during loading are used to prevent wasting time on a graph that is known to be malformed
- deferred-failure `ERROR` behavior is mainly for runtime work that has already begun, not for configuration that can be rejected up front

## Caveats

- destination input ports are single-source in the current model; wiring multiple upstream edges into the same input is treated as an overloaded input and logged as `overloaded_srcs`
- changing log levels in this file changes harness failure behavior as well as operator-visible output
