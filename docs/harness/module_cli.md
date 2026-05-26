# `module_cli.py`

Source: [src/rtl_comrade/module_cli.py](../../src/rtl_comrade/module_cli.py)

## Role

A virtual module used internally by the harness to bridge CLI arguments into the graph. One `ModuleCLI` instance is created for each distinct `cli` name found in the graph's CLI edges. It is never declared in user-authored graph YAML.

## See Also

- [graph.md](graph.md)
- [config.md](config.md)
- [docs/harness_configs/graph.md](../harness_configs/graph.md)

## Main Responsibilities

- hold a value injected by `Graph.construct_run` before execution begins
- emit that value as its sole output when the graph runs

## Place In The System

`Graph.from_config` creates a `ModuleCLI` node for each CLI edge, then wires it into the graph the same way as any other node. `Graph.construct_run` sets `module.value` on each `ModuleCLI` before `asyncio.gather` is called, making the injected value available at runtime.

## Notable Behaviors

- if `value` is still `None` when `run()` is called, the module logs `empty_cli_arg` at error level and emits `None` downstream
- the node id follows the pattern `cli-<name>` (e.g., `cli-filename`) to avoid collisions with user-defined node ids
- `ModuleCLI` uses a serde inner `Config` class for the `cli` field, matching the standard module config convention

## Caveats

- `ModuleCLI` nodes are internal harness implementation details; they appear in `graph.nodes` at runtime but are not meant to be referenced in graph YAML
