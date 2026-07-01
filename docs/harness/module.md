# `module.py`

Source: [src/rtl_comrade/module.py](../../src/rtl_comrade/module.py)

## Role

This file defines `GraphModule`, a frozen descriptor that wraps a raw module plugin class with the results of all load-time reflection. It is the boundary between plugin loading and node construction.

## See Also

- [README.md](README.md)
- [graph.md](graph.md)
- [node.md](node.md)
- [structure.md](structure.md)
- [port.md](port.md)
- [logging.md](logging.md)

## Main Responsibilities

- inspect the module class constructor to determine which harness-injected parameters (`config`, `id`) it accepts
- construct a `ModuleStructure` from the module's `run(...)` method (and `finalise()` for output ports)
- build the canonical input port template for modules with definite inputs
- expose all derived metadata as a single frozen, reusable object

## Place In The System

`GraphModule.from_module` is called by `Graph.from_config` once per loaded module class. The resulting descriptor is stored in `module_mappings` and shared across all `Node` instances backed by that class. `PreNode.__init__` reads flags from the descriptor rather than re-running reflection, and deep-copies the port template to give each node its own independent queues.

This split means that the cost of `inspect.signature`, `ModuleStructure` analysis, and port construction is paid once per module class per graph invocation, not once per node.

## Key Behaviors

- `GraphModule` is declared `frozen=True, slots=True`; the descriptor is immutable after construction and safe to share across nodes
- `has_config` and `has_id` are derived from the module constructor signature; they control which harness-managed keyword arguments are passed to `Module(**args)` in `PreNode.__init__`
- `defines_config` is true when the module class defines a nested `Config` type; when `has_config` is true but `defines_config` is false, `GraphModule.from_module` logs a `config.mismatch` warning
- `ports` is a fully built `OrderedDict[str, Port]` for modules with definite inputs (no `*args`/`**kwargs` parameters); it is empty for non-definite-input modules — `Graph.from_config` supplies those ports separately from edge definitions. Keyword-only parameters (those after a bare `*`) do not make inputs non-definite; they become ordinary ports
- module-level definiteness (`structure.definite_inputs`) is a property of the `run(...)` signature alone. A node over a non-definite (`**kwargs`) module can still be made definite at the node level by declaring `contract_port_mappings`, which gives the node an explicit finite contract-port surface; see [node.md](node.md) and the [config schema](../harness_configs/graph.md)
- `structure` is a reference to the `ModuleStructure` built during `from_module`; it is shared by all nodes using the same module class

## Caveats

- `ModuleStructure` is mutable (not `frozen`), so the shared `structure` reference is only safe because nothing mutates it at runtime; see [structure.md](structure.md)
- `from_module` logs fatal errors for unavailable constructor signatures and invalid `run(...)` structure; these raise `typer.Exit(1)` before a `GraphModule` is returned, so the caller never receives a partially-constructed descriptor
