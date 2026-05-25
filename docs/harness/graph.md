# `graph.py`

Source: [src/rtl_comrade/graph.py](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade/graph.py)

## Role

This file is the top-level harness coordinator. It turns config data into a runnable graph of `Node` objects.

## See Also

- [README.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/README.md)
- [__main__.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/__main__.md)
- [config.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/config.md)
- [loader.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/loader.md)
- [node.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/node.md)
- [validation.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/validation.md)
- [logging.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/logging.md)

## Main Responsibilities

- load `GraphConfig` from YAML
- load module and contract plugin classes
- instantiate nodes
- resolve and validate edges
- create virtual `ModuleCLI` nodes for CLI-sourced edges and build a matching `inspect.Signature`
- run pre-execution graph validation
- launch all nodes concurrently

## Key Entry Points

- `Graph.from_file(path)`: load a graph config file and build a `Graph`
- `Graph.from_config(config)`: construct the runtime graph from already-loaded config
- `Graph.construct_run(cleanup)`: return a callable whose signature matches `Graph.sig`; when called with the CLI kwargs it injects values into the CLI nodes, runs the graph, then calls `cleanup()`

## Place In The System

If `__main__.py` is the process bootstrap, `graph.py` is the harness assembly layer. It bridges config, plugin loading, node construction, and validation into one runnable object.

It is also the main fail-fast boundary of the harness. This is where obviously bad graphs should be rejected before any runtime work begins.

## Notable Behaviors

- missing modules or contracts are treated as fatal configuration errors
- source port names are checked against statically inferred emits when `ModuleStructure` can prove them
- duplicate incoming connections to the same destination input are rejected
- static deadlock checks run before execution starts
- node tasks are launched together via `asyncio.gather(...)`
- CLI edges are converted into virtual `ModuleCLI` nodes during `from_config`; each injects one value into one destination port
- a blank or non-identifier `cli` name causes a fatal error during construction
- error-level and critical-level logs emitted during graph assembly intentionally participate in the harness failure model: `ERROR` defers failure until the run ends, while `CRITICAL` aborts immediately

## Validation Philosophy

Graph loading and validation are intentionally strict.

- if the graph shape is invalid, the preferred behavior is to stop before execution
- fatal checks during loading are used to prevent wasting time on a graph that is known to be malformed
- deferred-failure `ERROR` behavior is mainly for runtime work that has already begun, not for configuration that can be rejected up front

## Caveats

- destination input ports are single-source in the current model; wiring multiple upstream edges into the same input is treated as an overloaded input and logged as `overloaded_srcs`
- changing log levels in this file changes harness failure behavior as well as operator-visible output
