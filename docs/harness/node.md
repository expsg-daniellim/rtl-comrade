# `node.py`

Source: [src/rtl_comrade/node.py](../../src/rtl_comrade/node.py)

## Role

This file defines the runtime execution unit of the harness and the construction-time value it is built from:

- `PreNode` — a node under construction: a module instance, its input ports, and the resolved `ContractDefinitions`, minus the node's outgoing edges. Enough to validate edges and propagate labels.
- `Node` — the immutable runtime unit, produced by `Node.from_prenode`, binding one module instance, its constructed contracts, one input-port set, and its outgoing dispatch map (`dsts`, source output port name → destination `Port`s).
- `Connection` — one outgoing edge in id space, `(self_port, other_node, other_port)`. A construction-time value: it carries node identity so deadlock validation and label propagation work over ids, and it names the destination port so the runtime dispatch map can be materialised from it. It does not enter the runtime `Node`.

## See Also

- [README.md](README.md)
- [graph.md](graph.md)
- [module.md](module.md)
- [structure.md](structure.md)
- [port.md](port.md)
- [api.md](api.md)
- [contract.md](contract.md) — contract resolution and construction
- [contract_default.md](contract_default.md)
- [branch_labels.md](branch_labels.md)
- [logging.md](logging.md)

## Main Responsibilities

- `PreNode`: instantiate the module from a pre-validated `GraphModule` descriptor, deep-copy port templates so each node has independent queues, resolve `required_ports`, and retain the resolved `ContractDefinitions`
- `Node.from_prenode`: construct the node's contracts from the now-labelled ports, coupling the `PreNode` with its edge information into an immutable `Node`
- run the contract/module loop, opening and closing the port read window around each `get_inputs()` call
- pass each module output through the output contract, then dispatch by enqueuing directly onto destination `Port`s
- call `module.finalise()` if present after the loop exits
- propagate `EndSentinel` when the node stops

## Two-Phase Construction

`Node.__init__` no longer exists as the single builder. Construction is split so a contract is built only after its ports' control-dependence labels are known (labels need edges and propagation, which need ports to already exist). See [graph.md](graph.md) for the five-phase assembly.

### `PreNode` — module and ports

`PreNode` takes a pre-validated [GraphModule](module.md) descriptor rather than a raw module class. All module-side reflection is done once by `GraphModule.from_module` before any `PreNode` is created.

- **Module instantiation** uses the descriptor's `has_config`, `has_id`, and `defines_config` flags to decide what to pass to the module constructor: `config` when `has_config`; that config deserialized through `serde.from_dict(...)` when `defines_config`; `<node-id>.module` when `has_id`. After deserialization, a non-absolute `Path` field whose first component is `{graph}` is rewritten to `relative_path / <remaining>`.
- **Ports** are the deep-copy of `GraphModule.ports` (independent queues per node), unless `Graph.from_config` supplies an explicit `ports` surface — for non-definite-input modules (built from incoming edges) or `contract_port_mappings` nodes — in which case that surface replaces the template outright.
- `PreNode.definite_inputs` records whether the input surface is a known finite set (the module's `structure.definite_inputs`, or forced true for a `contract_port_mappings` node).
- `required_ports` is resolved from the graph config's `required: true` destination references (by name or 1-based index, via `get_canonical_port`) into a canonical-name set. Required-ness is wiring policy expressed in port names; it stays off the transport-level `Port`.
- `get_canonical_port` lives on `PreNode` — it is used during edge wiring and `required_ports` resolution, both construction-time concerns.

The contract recipe is stored on the `PreNode` as a resolved `ContractDefinitions` (see [contract.md](contract.md)), alongside `relative_path`, for use when the `Node` is built.

### `Node.from_prenode` — contracts and coupling

`Node.from_prenode(pre, dsts, input_labels)` delegates construction to `pre.contract_definitions.construct(...)`, which builds the [ContractPort](api.md) adapters from the `PreNode`'s `Port`s — with `branch_labels` **injected from `input_labels`** so each contract owns its ports with their labels already set — and instantiates every contract the node defines against that one shared mapping. The per-contract constructor injection (`config`, `id`, `ports`) lives in `contract.py`.

It returns an immutable `Node` carrying the module, structure, ports, the three contract slots, `required_ports`, and `dsts` (plus a parallel `dst_counts`). `dsts` is a `dict[str, list[Port]]` — destination `Port`s grouped by the source output port that feeds them — materialised in `graph.py` from the id-space `Connection`s. The `Port` objects are shared from the `PreNode` into the `Node` — not re-copied — so a downstream node's `dsts` entry is the exact `Port` that node reads from.

Each `ContractPort` exposes `get()`, `try_get()`, `has_ended()`, `has_default`, `required`, `branch_labels`, and a `state` dict. This is the boundary between harness-owned transport and contract-owned policy.

### The three contract slots

`Node` carries `contract`, `input_contract`, and `output_contract`. A contract wraps both ends of the module, and each end resolves independently at call time:

- **input end** (`run`): `input_contract` if set, else `contract`. Always present — `contract` falls back to `DefaultContract`.
- **output end** (`process_result`): `output_contract` if set, else `contract` but only when `contract` defines a callable `process_outputs`. Otherwise there is no output processing and values go straight to dispatch.

See [contract.md](contract.md) for how the slots are resolved and validated.

## Place In The System

`Node` is where the abstract graph becomes live runtime behavior. `graph.py` builds `PreNode`s, wires edges, propagates labels, then builds `Node`s; `node.py` is where work actually happens.

## Execution Model

Each node repeatedly:

1. enables reads on every input port, asks its input contract for the next input bundle, then disables reads again
2. stops if the contract returns `EndSentinel`
3. unwraps `Payload.payload` into module keyword arguments, re-keying each from its external port name to the port's `param` (the literal `run(...)` parameter name) so builtin/keyword-avoiding trailing underscores are restored
4. runs the module, supporting sync, async, generator, and async-generator forms
5. normalizes outputs through `process_result(...)`, which resolves `(port, value)` and then passes the value through the output contract's `process_outputs(port, value)` if the node has one, sending the returned value onward
6. for each destination `Port` under the emitted port name in `dsts`, enqueues a `Payload` directly onto its queue; if the emitted port matches no destination (and the node has at least one wired destination), it logs `no_destination` at INFO and drops the value

After the loop exits:

7. if `module.finalise` exists and is callable, the node calls it (sync or async) with no arguments
8. the node enqueues `EndSentinel(self.id)` onto every destination `Port`

`finalise` exceptions are fatal, same as unhandled exceptions in `run(...)`, and it supports the same output dispatch forms.

## Port Read Window

Input ports are readable only for the duration of a `get_inputs()` call. `Node.run` sets `get_enabled = True` on every port immediately before invoking the input contract and clears it immediately after; outside that window `Port.get()` and `Port.try_get()` raise `IllegalGetAccessError`, which the node treats as fatal (`illegal_get_access`). See [port.md](port.md).

This makes two mistakes fail loudly instead of silently corrupting the stream: an output contract reading the input queues during `process_outputs`, and an input contract stashing a `ContractPort` and reading it after its call returned — which would steal a payload from the next invocation.

The window is set on the `Port` objects, which the `ContractPort` adapters close over, so it applies to every contract on the node regardless of which slot it occupies.

## Output Contract Pass

`process_result` resolves the emitted `(port, value)` first, then applies the output contract if the node has one. `process_outputs(port, value)` is awaited when it is a coroutine function and called directly otherwise, and its return value replaces `value` for dispatch.

- the contract sees the resolved port name but **cannot change it** — only the value is taken from the return, so an output contract transforms payloads, it does not reroute them
- it runs before the `dsts` lookup, so it also sees values emitted on ports with no wired destination
- outputs from `module.finalise()` go through the same `process_result` path, so they are processed too
- `IllegalGetAccessError` out of `process_outputs` is fatal (`illegal_get_access`); `typer.Exit` propagates; anything else is fatal with `exc_info`

## Dispatch Model

Dispatch targets `Port`s, not nodes. The runtime `Node` holds `dsts`, a `dict[str, list[Port]]` keyed by source output port name; `process_result` looks up the emitted port and enqueues onto each destination `Port`'s queue directly — there is no `accept` method and no downstream-node reference. The per-destination sequence counter is `dst_counts`, a `dict[str, list[int]]` parallel to `dsts` (one counter per destination in each port's list); `Payload.n` reads the counter before incrementing, so sequence numbers start at `0`. Node **identity** is a construction-time concern (validation, propagation) carried on the id-space `Connection`, and never enters the runtime dispatch map.

## Key Behaviors

- module `__init__` may receive `config` and/or `id`; contract `__init__` may receive `config`, `id`, and/or `ports` (injected by [contract.py](contract.md))
- a node with no output contract and a general contract lacking `process_outputs` skips the output pass entirely — output processing is opt-in
- destination ports are resolved by name or 1-based position during wiring (`PreNode.get_canonical_port`)
- output tuples must be exactly `(port_name, value)`; `None` means "emit nothing"
- emitting on a port with no matching downstream connection is **not** an error: `no_destination` at INFO, value dropped. This fires only when the node has at least one wired destination
- non-`rtl_comrade` exceptions during contract reflection, config deserialization, construction, and runtime execution are logged with `exc_info=e`; module-side reflection exceptions are handled by `GraphModule.from_module`
- `ERROR` allows best-effort continuation, `CRITICAL` aborts immediately
- `module.finalise` is detected with `hasattr` + `callable`; a non-callable `finalise` attribute is silently ignored
- `EndSentinel` is only propagated after `finalise` completes — if `finalise` raises fatally, downstream nodes do not receive a sentinel and will block indefinitely

## Caveats

- the `Node` is immutable: its structure (ports, contracts, dsts) is fixed at construction; only `dst_counts` entries mutate at runtime, and the `Port.get_enabled` flag and queues carry runtime traffic
- module constructor signatures are inspected once by `GraphModule.from_module`; contract constructor signatures are inspected per-node, per-slot, in `ContractDefinition.construct`
- a node's input and output contracts share one `ContractPort` mapping and therefore one set of per-port `state` dicts; that is the intended channel between them, but it also means colliding `state` keys clobber each other
- `typer.Exit` raised inside module or contract code during construction or execution propagates up rather than being caught and re-logged; the `except typer.Exit: raise` guards ensure it bypasses the generic `except Exception` handlers
- this file is a sensitive seam because it combines reflection, async execution, contracts, ports, and termination semantics
