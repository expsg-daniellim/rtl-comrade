# Harness Docs

This folder documents the harness layer in [src/rtl_comrade](../../src/rtl_comrade).

In this repository, "harness" means the runtime framework that:

- loads graph YAML
- discovers and imports plugin classes
- builds nodes and ports
- validates graph structure
- runs the graph under `asyncio`
- handles logging and failure semantics as part of runtime control

The harness is distinct from the modular building blocks:

- [modules](../../modules) provide node-local work
- [contracts](../../contracts) provide input-consumption and scheduling policy

## File Map

- [__main__.md](__main__.md): process entrypoint; delegates entirely to `App`.
- [app.md](app.md): CLI implementation — config discovery, subcommand registration, logging setup, graph execution.
- [graph.md](graph.md): graph construction, wiring, and top-level validation.
- [module.md](module.md): frozen descriptor wrapping a module plugin class with pre-computed reflection results and port templates.
- [module_cli.md](module_cli.md): virtual module that bridges CLI arguments into the graph.
- [node.md](node.md): runtime execution unit that binds modules, contracts, ports, and downstream connections together.
- [structure.md](structure.md): signature and AST analysis for module inputs and emitted output ports.
- [contract_default.md](contract_default.md): built-in default scheduling contract.
- [loader_utils.md](loader_utils.md): shared YAML config loading and dynamic plugin-file import.
- [loader_plugin.md](loader_plugin.md): plugin discovery and class import from configured paths.
- [loader_logger.md](loader_logger.md): per-graph logging-plugin resolution and signature validation.
- [config.md](config.md): serde-backed YAML schema types.
- [config_graph.md](config_graph.md): normalised `GraphConfig` intermediate between YAML and graph construction.
- [api.md](api.md): payload, sentinel, and contract-facing port API types.
- [port.md](port.md): queue-backed input port implementation.
- [validation.md](validation.md): acyclicity and static deadlock checks.
- [logging.md](logging.md): logging setup and failure behavior.

## Suggested Reading Order

If you are new to the harness, read in roughly this order:

1. [__main__.md](__main__.md)
2. [app.md](app.md)
3. [graph.md](graph.md)
4. [config.md](config.md)
5. [config_graph.md](config_graph.md)
6. [loader_utils.md](loader_utils.md), [loader_plugin.md](loader_plugin.md), [loader_logger.md](loader_logger.md)
7. [module.md](module.md)
8. [node.md](node.md)
9. [structure.md](structure.md)
10. [port.md](port.md)
11. [api.md](api.md)
12. [contract_default.md](contract_default.md)
13. [validation.md](validation.md)
14. [logging.md](logging.md)

## Runtime Flow

At a high level:

1. [__main__.py](../../src/rtl_comrade/__main__.py) delegates to [app.py](../../src/rtl_comrade/app.py), which discovers `rtl_comrade_config.yaml`, initializes logging, and registers typer subcommands.
2. At startup, [config_graph.py](../../src/rtl_comrade/config_graph.py) loads each graph YAML via [loader_utils.py](../../src/rtl_comrade/loader_utils.py), deserializes it into a [config.py](../../src/rtl_comrade/config.py) `GraphFileConfig`, and normalises it into a `GraphConfig`. Structural validation (duplicate IDs, invalid edges, cycles) happens here.
3. When the user invokes a subcommand, [graph.py](../../src/rtl_comrade/graph.py)'s `Graph.from_config()` loads module and contract plugin classes, wraps each module class in a [module.py](../../src/rtl_comrade/module.py) `GraphModule` descriptor (which runs [structure.py](../../src/rtl_comrade/structure.py) analysis and builds port templates once per class), creates [node.py](../../src/rtl_comrade/node.py) instances, wires edges, and runs [validation.py](../../src/rtl_comrade/validation.py).
4. Each `Node` deep-copies its port template from the shared `GraphModule` descriptor, creates [port.py](../../src/rtl_comrade/port.py) objects, and exposes [api.py](../../src/rtl_comrade/api.py) `ContractPort`s, including per-port `state` dicts, to the configured contract.
5. The contract, often [contract_default.py](../../src/rtl_comrade/contract_default.py), decides when enough inputs are ready for the module to run.
6. Module outputs are dispatched downstream as `Payload` objects, and graph termination is propagated with `EndSentinel`.

Logging is also part of the harness control plane. `ERROR` is used for non-fatal failures that should still let the graph finish as much work as possible before exiting with an error, while `CRITICAL` is used for immediate termination.

Graph loading is split into two phases. Structural validation (config-level checks that require only the YAML) runs at startup, so a misconfigured graph aborts before the CLI is presented. Plugin-level validation (module existence, port names, deadlock) runs at invocation time when `Graph.from_config` is called.

## Testing

See [docs/testing.md](../testing.md) for the full two-stage procedure, module-to-test-file mapping, and coverage requirements.

## Doc Structure

See [doc-structure.md](doc-structure.md).

## Editing Guidance

- Put harness-wide orchestration changes in `src/rtl_comrade`, not in plugin folders.
- Keep scheduling policy in contracts.
- Keep node-local business logic in modules.
- Be cautious with `EndSentinel`, logging levels, and reflection-heavy code paths; small changes can alter control flow significantly because logging is part of the intended failure model.
