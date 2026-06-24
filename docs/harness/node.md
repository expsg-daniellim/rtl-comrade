# `node.py`

Source: [src/rtl_comrade/node.py](../../src/rtl_comrade/node.py)

## Role

This file defines the runtime execution unit of the harness. A `Node` binds together:

- one module plugin instance
- one contract plugin instance
- one input-port set
- zero or more downstream connections

## See Also

- [README.md](README.md)
- [graph.md](graph.md)
- [module.md](module.md)
- [structure.md](structure.md)
- [port.md](port.md)
- [api.md](api.md)
- [contract_default.md](contract_default.md)
- [logging.md](logging.md)

## Main Responsibilities

- instantiate module and contract classes using pre-validated metadata from a `GraphModule` descriptor
- deserialize module and contract configs when `Config` types are provided
- deep-copy port templates from `GraphModule` to give each node instance independent queues
- expose contract-facing `ContractPort` adapters
- accept inbound payloads and sentinels
- run the contract/module loop
- dispatch outputs downstream
- call `module.finalise()` if present after the loop exits
- propagate `EndSentinel` when the node stops

## Instantiation Model

`Node` takes a pre-validated [GraphModule](module.md) descriptor rather than a raw module class. All module-side reflection (constructor inspection, `ModuleStructure` analysis, port template construction) is done once by `GraphModule.from_module` before any `Node` is created. `Node.__init__` reads the pre-computed metadata from the descriptor instead of re-running reflection.

### Module instantiation

`Node.__init__` uses the `has_config`, `has_id`, and `defines_config` flags from the `GraphModule` descriptor to decide what to pass to the module class constructor.

- If `has_config` is true, the node passes the graph node's `config`.
- If `defines_config` is true, that config is deserialized through `serde.from_dict(...)` before being passed in. After deserialization, any `Path`-typed field that is not absolute and whose first path component is `{graph}` is replaced with `relative_path / <remaining components>`, where `relative_path` is the directory of the graph YAML file. This allows module configs to reference files relative to the graph file using the `{graph}` prefix.
- If `has_id` is true, the node passes `<node-id>.module`.
- If neither flag is set, the module is instantiated with no harness-injected arguments.

### Port construction

`Node.__init__` deep-copies the port template from `GraphModule.ports` to give each node instance its own independent queues, unless `Graph.from_config` passes an explicit `ports` surface — in which case that surface *replaces* the module template outright (it is not merged onto it).

- for modules with definite inputs and no `contract_port_mappings`, no `ports` override is given; the node's surface is the deep-copy of `GraphModule.ports`, a fully built `OrderedDict` keyed by parameter name with `has_default` set from the function signature. Keyword-only parameters do not change this; they are treated as ordinary definite inputs
- for modules with non-definite inputs (`*args` or `**kwargs` in `run(...)`), `GraphModule.ports` is empty; `Graph.from_config` builds the surface from the actual incoming edges and passes it as the `ports` override
- for nodes declaring `contract_port_mappings`, `Graph.from_config` builds the contract-port surface (keyed by contract port name, `has_default` true only when every forwarded-to module parameter has a default) and passes it as the `ports` override, replacing the module signature surface

`Node.definite_inputs` records whether the node's input surface is a known finite set. It defaults to the module's own `structure.definite_inputs`, but `Graph.from_config` passes `definite_inputs_override=True` for a `contract_port_mappings` node so it validates strictly even over a `**kwargs` module. Edge destination validation and the `non_definite_inputs` warning key off this node-level value, not the shared module property.

After the ports are assembled, `Node.__init__` resolves the `required_ports` parameter: `Graph.from_config` collects every destination-port reference whose edge sets `required: true` for this node, and the node resolves each (by name or 1-based index, via `get_canonical_port`) into the canonical-name set `Node.required_ports`. The flag stays off the transport-level `Port`: required-ness is wiring policy expressed in port *names*, held on the node alongside `dsts`. That set drives two consumers — the `ContractPort` adapters built just below (`required = name in self.required_ports`), and `validate_no_static_deadlock`, which reads `node.required_ports` during static validation. Unresolvable references are skipped here; the later edge validation reports them.

The raw `Port` objects are harness-owned runtime queues. Contracts do not receive them directly.

### Contract instantiation

`Node.__init__` inspects the contract constructor separately with `inspect.signature(...)`.

- If contract `__init__` accepts `config`, the node passes `contract_config`.
- If the contract defines a nested `Config` type, `contract_config` is deserialized through `serde.from_dict(...)` first. After deserialization, any `Path`-typed field that is not absolute and whose first path component is `{graph}` is replaced with `relative_path / <remaining components>`, the same as module configs above.
- If contract `__init__` accepts `id`, the node passes `<node-id>.contract`.
- If contract `__init__` accepts `ports`, the node passes a mapping of [ContractPort](api.md) adapters built from the underlying `Port`s.

Each `ContractPort` exposes:

- blocking `get()`
- non-blocking `try_get()`
- `has_ended()`
- `has_default` — whether the corresponding module parameter carries a Python default
- `required` — whether the graph config marks this port required; the default contract awaits a real value and ignores `has_default` for such ports
- a `state` dict for contract-owned per-port bookkeeping

This is the main boundary between harness-owned transport and contract-owned scheduling policy.

### Why the staging matters

The ordering is important:

1. `GraphModule.from_module` inspects the module constructor and `run(...)` to define the node's input surface and build a reusable port template
2. `Node.__init__` deep-copies that template so each node has independent queues
3. `Node.__init__` inspects the contract constructor to decide how ports are exposed to scheduling logic

That means a change to a module's `run(...)` signature can indirectly change contract-visible inputs even if the contract code itself is untouched. The analysis in step 1 is shared across all nodes backed by the same module class.

## Place In The System

`Node` is where the abstract graph becomes live runtime behavior. `graph.py` builds nodes; `node.py` is where work actually happens.

## Execution Model

Each node repeatedly:

1. asks its contract for the next input bundle
2. stops if the contract returns `EndSentinel`
3. unwraps `Payload.payload` into module keyword arguments
4. runs the module, supporting sync, async, generator, and async-generator forms
5. normalizes outputs through `process_result(...)`
6. forwards results to every matching downstream connection; if the emitted port matches no connection (and the node has at least one wired destination), it logs `no_destination` at INFO and the value is dropped

After the loop exits:

7. if `module.finalise` exists and is callable, the node calls it (sync or async) with no arguments, with structlog context bound as `harness.node.module`
8. the node sends `EndSentinel(self.id)` to every downstream edge

`finalise` exceptions are treated as fatal — same path as unhandled exceptions in `run(...)`. It supports the same output dispatch as `run(...)`: plain return, named-port tuple, sync generator, async return, and async generator — all normalized through `process_result(...)`.

## Key Behaviors

- module `__init__` may receive `config` and/or `id`
- contract `__init__` may receive `config`, `id`, and/or `ports`
- destination ports can be resolved by name or by 1-based position
- output tuples must be exactly `(port_name, value)`
- `None` is treated as "emit nothing"
- emitting on a port with no matching downstream connection is **not** an error: the node logs `no_destination` at INFO and drops the value. This fires only when the node has at least one wired destination (`len(self.dsts) > 0`); a node with no wired destinations at all emits nothing and logs nothing. This is the runtime path for deliberately unwired terminal/output ports — it is a `node.py` runtime emission, not a `validation.py` static check
- non-`rtl_comrade` exceptions caught during contract reflection, config deserialization, construction, and runtime execution are logged with `exc_info=e`; module-side reflection exceptions are handled by `GraphModule.from_module` before `Node` is involved
- error-level and critical-level logs during node execution intentionally participate in the harness failure model: `ERROR` allows best-effort continued execution, while `CRITICAL` aborts immediately
- `module.finalise` is detected with `hasattr` + `callable`; a non-callable attribute named `finalise` is silently ignored
- `EndSentinel` is only propagated after `finalise` completes — if `finalise` raises fatally, downstream nodes do not receive a sentinel and will block indefinitely

## Caveats

- output sequence numbers currently start at `0`
- this file is a sensitive seam because it combines reflection, async execution, contracts, ports, and termination semantics
- module constructor signatures are inspected once by `GraphModule.from_module` and cached in the descriptor; contract constructor signatures are still inspected per-node in `Node.__init__`
- `typer.Exit` raised inside module or contract code during construction or execution propagates up through `Node` rather than being caught and re-logged; the `except typer.Exit: raise` guards ensure it bypasses the generic `except Exception` handlers
