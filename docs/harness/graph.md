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
- [contract.md](contract.md) — `ContractDefinitions.from_node_config`, which owns contract resolution
- [validation.md](validation.md)
- [logging.md](logging.md)

## Main Responsibilities

- load module and contract plugin classes from a `GraphConfig`
- wrap each loaded module class in a `GraphModule` descriptor via `GraphModule.from_module`
- resolve each node's contract fields into a `ContractDefinitions` via [contract.py](contract.md), reporting resolution failures per node
- pre-build port mappings for non-definite-input nodes from incoming edge definitions
- instantiate nodes
- create virtual `ModuleCLI` nodes from `GraphConfig.cli_srcs`
- validate edge port names against module structure
- run static deadlock checks before execution
- launch all nodes concurrently

## Key Entry Points

- `Graph.from_config(config, cli_kwargs=None)`: construct the runtime graph from an already-loaded `GraphConfig`; `cli_kwargs` is a dict of resolved CLI kwarg values passed from the `construct_run` closure; node `cli_config`, `cli_contract_config`, `cli_input_contract_config`, and `cli_output_contract_config` entries are applied to their corresponding static config dicts before each `Node` is constructed
- `Graph.construct_run(config, setup_logging, cleanup)`: static method; returns a closure whose signature matches `config.sig`; when invoked with CLI kwargs, constructs the `Graph` via `from_config` (passing the kwargs for config patching), resolves the graph's custom logging via `config.logging.load` and installs it via `setup_logging(processors, handlers, config.logging.include_default)`, injects data-flow values into CLI nodes, runs the graph, then calls `cleanup()`

## Place In The System

If `__main__.py` is the process bootstrap, `graph.py` is the harness assembly layer. It bridges config, plugin loading, node construction, and validation into one runnable object.

It is also the main fail-fast boundary of the harness. This is where obviously bad graphs should be rejected before any runtime work begins.

## Notable Behaviors

- structural config checks (duplicate node ids, invalid dst node, unused edge sources, cycles) are performed in `GraphConfig.from_file_config` before `Graph.from_config` is reached; see [config_graph.md](config_graph.md)
- `Graph.from_config` handles only checks that require loaded plugin classes: invalid module/contract names, contract interface checks, invalid port names, overloaded inputs, and static deadlock
- missing modules or contracts are treated as fatal configuration errors
- contract resolution is delegated to `ContractDefinitions.from_node_config`, which raises rather than logs; `from_config` catches each failure type, logs it against the node index and id (`invalid_contract`, `missing_contract_function`, `missing_contract_parameter`, `invalid_contract_parameter_type`), and continues to the next node so one bad node does not mask the rest
- contract interface checks are **per-node and per-role**: an input-side contract needs `get_inputs`, an output contract needs `process_outputs`. There is no longer a load-time screen requiring every loaded contract class to expose `get_inputs`, so a contract plugin usable only on the output end can be loaded without a stub
- a node setting `contract`, `input_contract`, and `output_contract` all at once leaves `contract` unreachable; this warns `obsolete_contract` and is otherwise harmless
- source port names are checked against statically inferred emits when `ModuleStructure` can prove them
- several incoming connections to one destination input are accepted only when their sources are mutually-exclusive branch arms, and rejected as `overloaded_srcs` otherwise
- static deadlock checks run before execution starts
- each loaded module class is wrapped in a `GraphModule` descriptor exactly once; nodes that share a module class share the same descriptor but each get their own deep-copied port instances
- for modules with non-definite inputs, `Graph.from_config` pre-builds a port mapping from the incoming edges before constructing the `PreNode`; this is passed as the `ports` override
- for nodes declaring `contract_port_mappings`, `Graph.from_config` builds the node's input surface from the declared contract ports instead of the module signature, passes it as the `ports` override, and constructs the node with `definite_inputs_override=True`. A contract port's `has_default` is true only when every module parameter it forwards to has a Python default. When the module is definite, every forwarded-to target must name a real `run(...)` parameter — an unknown target is fatal (`invalid_mapping_target`); over a `**kwargs` module that check is skipped. A contract port mapping to an empty target list forwards to nothing, so it cannot inherit a default and stays first-run-required
- edge destination-port validation and the `non_definite_inputs` warning read the node-level `Node.definite_inputs`, so a `contract_port_mappings` node rejects edges to undeclared contract ports even over a `**kwargs` module
- `from_config` runs in five phases: build a `PreNode` per config node (module + input ports + resolved `ContractDefinitions`); wire and validate edges into `node_dsts`, per-source-node lists of id-space `Connection`s (`self_port`/`other_node`/`other_port`), recording each destination port's incoming edge count as its `Port.source_n`; static deadlock screening over `(prenodes, node_dsts)`; an inline topological pass over `(prenodes, node_dsts)` to compute each input port's control-dependence labels (each output inherits the union of its node's gating input labels plus a `(node_id, arm)` term when it belongs to a branch arm, and each input intersects the labels of its incoming edges), which is also where a multi-source port's sources are checked for mutual exclusivity; then materialise each node's runtime dispatch map (source output port → destination `Port`s, resolved from the `Connection`s) and `Node.from_prenode` couples each `PreNode` with that map and its labels into the immutable runtime `Node`. See [branch_labels.md](branch_labels.md) and [node.md](node.md)
- node tasks are launched together via `asyncio.gather(...)`; if any node raises `typer.Exit`, it propagates out of the gather immediately
- `GraphConfigSrcCLI` edges are normalised into `GraphConfig.cli_srcs` and `GraphConfig.sig` during `GraphConfig.from_file_config`; the corresponding virtual `ModuleCLI` nodes are created from `cli_srcs` during `Graph.from_config`; each injects one value into one destination port
- the four node CLI config blocks (`cli_config`, `cli_contract_config`, `cli_input_contract_config`, `cli_output_contract_config`) are also normalised into `GraphConfig.sig` during `from_file_config`; at construction time in `Graph.from_config`, their CLI kwarg values are merged into the matching config dict before the `PreNode` is built (module config) and before `Node.from_prenode` (all three contract configs), so the module or contract receives them through the normal serde deserialization path
- error-level and critical-level logs emitted during graph assembly intentionally participate in the harness failure model: `ERROR` defers failure until the run ends, while `CRITICAL` aborts immediately

## Validation Philosophy

Graph loading and validation are intentionally strict.

- if the graph shape is invalid, the preferred behavior is to stop before execution
- fatal checks during loading are used to prevent wasting time on a graph that is known to be malformed
- deferred-failure `ERROR` behavior is mainly for runtime work that has already begun, not for configuration that can be rejected up front

## Caveats

- a destination input port fed by several edges is an alternation, not a merge: the harness proves at most one source can carry data, and rejects the wiring as `overloaded_srcs` when it cannot. Nothing interleaves two live streams into one port
- changing log levels in this file changes harness failure behavior as well as operator-visible output
