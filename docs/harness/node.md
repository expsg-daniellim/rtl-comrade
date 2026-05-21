# `node.py`

Source: [src/rtl_comrade/node.py](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade/node.py)

## Role

This file defines the runtime execution unit of the harness. A `Node` binds together:

- one module plugin instance
- one contract plugin instance
- one input-port set
- zero or more downstream connections

## See Also

- [README.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/README.md)
- [graph.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/graph.md)
- [structure.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/structure.md)
- [port.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/port.md)
- [api.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/api.md)
- [contract_default.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/contract_default.md)
- [logging.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/logging.md)

## Main Responsibilities

- instantiate module and contract classes
- deserialize module and contract configs when `Config` types are provided
- infer module input and output structure
- create queue-backed input ports
- expose contract-facing `ContractPort` adapters
- accept inbound payloads and sentinels
- run the contract/module loop
- dispatch outputs downstream
- call `module.finalise()` if present after the loop exits
- propagate `EndSentinel` when the node stops

## Instantiation Model

`Node` is not a thin wrapper around prebuilt objects. It performs a staged construction process that mixes reflection, optional config deserialization, and runtime adapter creation.

### Module instantiation

When a node is created, it first inspects the module class constructor with `inspect.signature(...)`.

- If module `__init__` accepts `config`, the node passes the graph node's `config`.
- If the module defines a nested `Config` type, that config is deserialized through `serde.from_dict(...)` before being passed in.
- If module `__init__` accepts `id`, the node passes `<node-id>.module`.
- If neither `config` nor `id` is accepted, the module is instantiated with no harness-injected arguments.

The node then constructs [ModuleStructure](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/structure.md) from `Module.run(...)` and uses that inferred signature to create its input ports.

### Port construction

After module structure analysis:

- one [Port](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/port.md) is created for each inferred `run(...)` parameter
- default values from the module signature become default-valued ports
- input port order is preserved through an `OrderedDict`

The raw `Port` objects are harness-owned runtime queues. Contracts do not receive them directly.

### Contract instantiation

The node then inspects the contract constructor separately.

- If contract `__init__` accepts `config`, the node passes `contract_config`.
- If the contract defines a nested `Config` type, `contract_config` is deserialized through `serde.from_dict(...)` first.
- If contract `__init__` accepts `id`, the node passes `<node-id>.contract`.
- If contract `__init__` accepts `ports`, the node passes a mapping of [ContractPort](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/api.md) adapters built from the underlying `Port`s.

Each `ContractPort` exposes:

- blocking `get()`
- non-blocking `try_get()`
- `has_ended()`
- default metadata
- a `state` dict for contract-owned per-port bookkeeping

This is the main boundary between harness-owned transport and contract-owned scheduling policy.

### Why the staging matters

The ordering is important:

1. module constructor inspection decides how node config enters the module
2. module `run(...)` analysis defines the node's input surface
3. ports are created from that inferred input surface
4. contract constructor inspection decides how those ports are exposed to scheduling logic

That means a change to a module's `run(...)` signature can indirectly change contract-visible inputs even if the contract code itself is untouched.

## Place In The System

`Node` is where the abstract graph becomes live runtime behavior. `graph.py` builds nodes; `node.py` is where work actually happens.

## Execution Model

Each node repeatedly:

1. asks its contract for the next input bundle
2. stops if the contract returns `EndSentinel`
3. unwraps `Payload.payload` into module keyword arguments
4. runs the module, supporting sync, async, generator, and async-generator forms
5. normalizes outputs through `process_result(...)`
6. forwards results to every matching downstream connection

After the loop exits:

7. if `module.finalise` exists and is callable, the node calls it (sync or async) with no arguments, with structlog context bound as `harness.node.module`
8. the node sends `EndSentinel(self.id)` to every downstream edge

`finalise` exceptions are treated as fatal — same path as unhandled exceptions in `run(...)`. It supports the same output dispatch as `run(...)`: plain return, named-port tuple, sync generator, async return, and async generator — all normalized through `process_result(...)`.

## Important Details

- module `__init__` may receive `config` and/or `id`
- contract `__init__` may receive `config`, `id`, and/or `ports`
- destination ports can be resolved by name or by 1-based position
- output tuples must be exactly `(port_name, value)`
- `None` is treated as "emit nothing"
- non-`rtl_comrade` exceptions caught during module/contract reflection, config deserialization, construction, and runtime execution are logged with `exc_info=e`
- error-level and critical-level logs during node execution intentionally participate in the harness failure model: `ERROR` allows best-effort continued execution, while `CRITICAL` aborts immediately
- `module.finalise` is detected with `hasattr` + `callable`; a non-callable attribute named `finalise` is silently ignored
- `EndSentinel` is only propagated after `finalise` completes — if `finalise` raises fatally, downstream nodes do not receive a sentinel and will block indefinitely

## Caveats

- output sequence numbers currently start at `0`
- this file is a sensitive seam because it combines reflection, async execution, contracts, ports, and termination semantics
- constructor signatures are part of the plugin API surface because `Node` injects `config`, `id`, and `ports` only when those parameters are explicitly accepted
