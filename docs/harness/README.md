# Harness Docs

This folder documents the harness layer in [src/rtl_comrade](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade).

In this repository, "harness" means the runtime framework that:

- loads graph YAML
- discovers and imports plugin classes
- builds nodes and ports
- validates graph structure
- runs the graph under `asyncio`
- handles logging and failure semantics as part of runtime control

The harness is distinct from the modular building blocks:

- [modules](/Users/daniellim/Documents/random/rtl-comrade/modules) provide node-local work
- [contracts](/Users/daniellim/Documents/random/rtl-comrade/contracts) provide input-consumption and scheduling policy

## File Map

- [__main__.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/__main__.md): barebones CLI entrypoint and process startup.
- [graph.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/graph.md): graph construction, wiring, and top-level validation.
- [node.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/node.md): runtime execution unit that binds modules, contracts, ports, and downstream connections together.
- [structure.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/structure.md): signature and AST analysis for module inputs and emitted output ports.
- [contract_default.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/contract_default.md): built-in default scheduling contract.
- [loader.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/loader.md): YAML loading and plugin discovery/import.
- [config.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/config.md): graph config schema.
- [api.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/api.md): payload, sentinel, and contract-facing port API types.
- [port.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/port.md): queue-backed input port implementation.
- [validation.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/validation.md): acyclicity and static deadlock checks.
- [logging.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/logging.md): logging setup and failure behavior.

## Suggested Reading Order

If you are new to the harness, read in roughly this order:

1. [__main__.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/__main__.md)
2. [graph.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/graph.md)
3. [config.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/config.md)
4. [loader.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/loader.md)
5. [node.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/node.md)
6. [structure.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/structure.md)
7. [port.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/port.md)
8. [api.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/api.md)
9. [contract_default.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/contract_default.md)
10. [validation.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/validation.md)
11. [logging.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/logging.md)

## Runtime Flow

At a high level:

1. [__main__.py](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade/__main__.py) initializes logging and selects a graph file.
2. [graph.py](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade/graph.py) loads [config.py](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade/config.py) data from YAML via [loader.py](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade/loader.py).
3. `Graph.from_config()` loads module and contract plugin classes, creates [node.py](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade/node.py) instances, wires edges, and runs [validation.py](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade/validation.py).
4. Each `Node` analyzes its module through [structure.py](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade/structure.py), creates [port.py](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade/port.py) objects, and exposes [api.py](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade/api.py) `ContractPort`s to the configured contract.
5. The contract, often [contract_default.py](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade/contract_default.py), decides when enough inputs are ready for the module to run.
6. Module outputs are dispatched downstream as `Payload` objects, and graph termination is propagated with `EndSentinel`.

Logging is also part of the harness control plane. `ERROR` is used for non-fatal failures that should still let the graph finish as much work as possible before exiting with an error, while `CRITICAL` is used for immediate termination.

Before execution begins, the harness also deliberately front-loads graph loading and validation failures. Invalid graph structure is treated as something to reject early, not something to muddle through at runtime.

## Editing Guidance

- Put harness-wide orchestration changes in `src/rtl_comrade`, not in plugin folders.
- Keep scheduling policy in contracts.
- Keep node-local business logic in modules.
- Be cautious with `EndSentinel`, logging levels, and reflection-heavy code paths; small changes can alter control flow significantly because logging is part of the intended failure model.
