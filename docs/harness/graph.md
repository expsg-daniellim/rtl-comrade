# `graph.py`

Source: [src/rtl_comrade/graph.py](../../src/rtl_comrade/graph.py)

## Role

This file is the top-level harness coordinator. It turns config data into a runnable graph of `Node` objects.

## See Also

- [README.md](README.md)
- [__main__.md](__main__.md)
- [config.md](config.md)
- [loader_plugin.md](loader_plugin.md) — `load_plugins`
- [loader_logger.md](loader_logger.md) — `LoggingConfig.load`
- [module.md](module.md)
- [node.md](node.md)
- [validation.md](validation.md)
- [logging.md](logging.md)

## Main Responsibilities

- load module and contract plugin classes from a `GraphConfig`
- wrap each loaded module class in a `GraphModule` descriptor via `GraphModule.from_module`
- pre-build port mappings for non-definite-input nodes from incoming edge definitions
- instantiate nodes
- create virtual `ModuleCLI` nodes from `GraphConfig.cli_srcs`
- validate edge port names against module structure
- run static deadlock checks before execution
- launch all nodes concurrently

## Key Entry Points

- `Graph.from_config(config, cli_kwargs=None)`: construct the runtime graph from an already-loaded `GraphConfig`; `cli_kwargs` is a dict of resolved CLI kwarg values passed from the `construct_run` closure; node `cli_config` and `cli_contract_config` entries are applied to the static config dicts before each `Node` is constructed
- `Graph.construct_run(config, setup_logging, cleanup)`: static method; returns a closure whose signature matches `config.sig`; when invoked with CLI kwargs, constructs the `Graph` via `from_config` (passing the kwargs for config patching), resolves the graph's custom logging via `config.logging.load` and installs it via `setup_logging(processors, handlers, config.logging.include_default)`, injects data-flow values into CLI nodes, runs the graph, then calls `cleanup()`

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
- each loaded module class is wrapped in a `GraphModule` descriptor exactly once; nodes that share a module class share the same descriptor but each get their own deep-copied port instances
- for modules with non-definite inputs, `Graph.from_config` pre-builds a port mapping from the incoming edges before constructing the node; this is passed as the `ports` override parameter to `Node.__init__`
- node tasks are launched together via `asyncio.gather(...)`; if any node raises `typer.Exit`, it propagates out of the gather immediately
- `GraphConfigSrcCLI` edges are normalised into `GraphConfig.cli_srcs` and `GraphConfig.sig` during `GraphConfig.from_file_config`; the corresponding virtual `ModuleCLI` nodes are created from `cli_srcs` during `Graph.from_config`; each injects one value into one destination port
- node `cli_config` and `cli_contract_config` entries are also normalised into `GraphConfig.sig` during `from_file_config`; at construction time in `Graph.from_config`, their CLI kwarg values are merged into the node's config/contract_config dicts before `Node()` is instantiated, so the module or contract receives them through the normal serde deserialization path
- error-level and critical-level logs emitted during graph assembly intentionally participate in the harness failure model: `ERROR` defers failure until the run ends, while `CRITICAL` aborts immediately

## Validation Philosophy

Graph loading and validation are intentionally strict.

- if the graph shape is invalid, the preferred behavior is to stop before execution
- fatal checks during loading are used to prevent wasting time on a graph that is known to be malformed
- deferred-failure `ERROR` behavior is mainly for runtime work that has already begun, not for configuration that can be rejected up front

## Caveats

- destination input ports are single-source in the current model; wiring multiple upstream edges into the same input is treated as an overloaded input and logged as `overloaded_srcs`
- changing log levels in this file changes harness failure behavior as well as operator-visible output
