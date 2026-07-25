# Writing Contracts

This document explains how to implement a contract for `rtl-comrade`.

For harness internals behind contract instantiation, see:

- [docs/harness/contract.md](../harness/contract.md) — resolution, role checks, and construction
- [docs/harness/node.md](../harness/node.md)
- [docs/harness/api.md](../harness/api.md)
- [docs/harness/port.md](../harness/port.md) — the port read window
- [docs/harness/contract_default.md](../harness/contract_default.md)

For testing contracts in isolation, see [testing.md](testing.md).

## What A Contract Is

A contract is the policy wrapped around a module — on both ends.

The module defines what work the node performs. The contract defines when the node is allowed to run and which input payloads are supplied for that invocation (`get_inputs`), and it may also transform each value the module emits before it travels downstream (`process_outputs`).

Examples on the input end:

- a zip-style contract waits for one item from each input
- a latest-value contract might cache one input and trigger on another
- a keyed-join contract might wait until all required ports for a given key are present

Examples on the output end:

- attaching a correlation key that a downstream keyed-join contract will match on
- normalising or re-wrapping emitted values so a module stays ignorant of the graph's payload conventions
- recording per-port emission state that the same node's input contract reads on its next call

That means coordination logic belongs in contracts, not in modules — inbound and outbound alike.

## The Three Contract Slots

A node declares up to three contracts in its graph config:

| Field | Serves |
|---|---|
| `contract` | both ends, except where overridden; defaults to the built-in `default` |
| `input_contract` | the input end, overriding `contract` |
| `output_contract` | the output end, overriding `contract` |

Output processing is opt-in. A node with only `contract: zip` does none, because `zip` defines no `process_outputs` — values go straight downstream untouched. To get output processing, either name an `output_contract` or give the general contract a `process_outputs` method.

Each slot has its own config dict (`contract_config`, `input_contract_config`, `output_contract_config`) and its own CLI config block. See [docs/harness_configs/graph.md](../harness_configs/graph.md).

## Required Interface

A contract is a plain Python class discovered from a plugin file. What it must expose depends on the slot it is used in, and the harness checks per node rather than at load time — a class used only as an `output_contract` never needs `get_inputs`.

**As `contract` or `input_contract`:**

- it must expose `get_inputs()`
- `get_inputs()` may be sync or async
- `get_inputs()` must return either `dict[str, Payload]` or `EndSentinel`

**As `output_contract`:**

- it must expose `process_outputs(port, value)`
- `process_outputs` may be sync or async
- `port` must be annotated `str` or left unannotated; both parameters must be declared by those names

A general `contract` may define `process_outputs` as well, in which case it serves both ends and is held to both signatures. In practice, a useful input-side contract should also accept `ports` in `__init__`.

## How The Harness Instantiates A Contract

[contract.py](../harness/contract.md) inspects each contract constructor and only injects arguments that the constructor explicitly accepts. This applies identically to all three slots.

Possible injected arguments are:

- `config`
- `id`
- `ports`

### `config`

If `__init__` accepts `config`, the harness passes the config dict belonging to that slot — `contract_config`, `input_contract_config`, or `output_contract_config` — from the graph YAML.

If the contract defines a nested `Config` class, that config is deserialized through `serde.from_dict(...)` before construction. A `Config` field declared as `Path` (rather than `str`) supports the `{graph}` prefix as its first path component, which the harness resolves to the graph file's directory at construction time, the same as module and logger configs (see [graph.md](../harness_configs/graph.md)).

### `id`

If `__init__` accepts `id`, the harness passes:

```python
"<node-id>.contract"
```

This is useful for logging and debugging. All of a node's contracts receive the same `id`, so an input and an output contract on one node log under the same name.

### `ports`

If `__init__` accepts `ports`, the harness passes:

```python
dict[str, ContractPort]
```

This is the normal contract input surface.

In the current implementation, this mapping preserves the module input declaration order. Order-sensitive contracts may rely on that, as the shipped zip-style example does.

For a module with non-definite inputs (a `run(...)` signature using `*args` or `**kwargs`), there is no signature-derived declaration order: the harness builds `ports` from the node's incoming edges instead. A contract paired with such a module should key into `ports` by name and not assume a signature-defined ordering.

If an input-side contract does not accept `ports`, the harness logs a warning, but such a contract is rarely useful. An output contract that omits `ports` is normal and is not warned about — `process_outputs` receives its value as an argument.

The node builds this mapping **once** and hands the same objects to every contract it has. A node's input and output contracts therefore share their `ContractPort`s and the `state` dicts on them, which is how an output contract communicates with the input contract on the same node. It also means two contracts writing the same `state` key on the same port will clobber each other.

## The `ContractPort` API

Contracts do not receive raw queue objects. They receive `ContractPort` adapters.

Each `ContractPort` provides:

- `name`
- `get()`: async blocking read, returns `Payload` or `EndSentinel`
- `try_get()`: non-blocking read, returns `Payload`, `EndSentinel`, or `None`
- `has_ended()`: whether the port has already seen an end sentinel
- `has_default`: whether the corresponding module parameter has a Python default value
- `required`: whether the graph config marks this port required; the built-in default contract awaits a real value and ignores `has_default` for such ports
- `branch_labels`: control-dependence labels assigned during graph construction — the branch arms whose non-selection can end this port's stream. Ports with equal `branch_labels` are co-fated; the built-in default contract only treats a data/end split between co-fated ports as a mismatch. See [docs/harness/branch_labels.md](../harness/branch_labels.md)
- `state`: a dict for contract-owned per-port state

Important details:

- `get()` waits until an item is available
- `try_get()` treats an empty queue as normal and returns `None`
- both reads are legal **only inside a `get_inputs()` call** — see below
- contracts should store per-port state inside `port.state`, not by attaching ad hoc attributes directly to the `ContractPort` object

The built-in default contract uses `port.state` keys such as `persistent` and `last_value`.

### The read window

A port is readable only for the duration of the `get_inputs()` call the harness is currently making. The node enables reads immediately before calling `get_inputs()` and disables them immediately after. Calling `get()` or `try_get()` at any other moment raises `IllegalGetAccessError`, which the harness treats as fatal.

Two consequences to write around:

- **Do not stash a port and read it later.** Capturing a `ContractPort` during one `get_inputs()` and awaiting it from a background task, a callback, or a later call is rejected. Read everything an invocation needs before returning.
- **An output contract cannot read inputs.** `process_outputs` runs outside the window, so it can use `port.name`, `port.has_ended()`, `port.branch_labels`, and `port.state`, but not `get()` or `try_get()`. To pass information from the input end to the output end, write it into `port.state` (or onto the contract's own `self`) during `get_inputs()`.

This is a guard against a real failure mode: a deferred read that resolves during the module's execution would silently consume a payload the *next* invocation was owed, desyncing the stream in a way that surfaces far from its cause.

## What `get_inputs()` Should Return

On each node iteration, the harness calls `contract.get_inputs()`.

The contract must return one of two things:

### A dict of input payloads

The normal return type is:

```python
dict[str, Payload]
```

The harness unwraps the payload objects and calls the module with:

```python
module.run(**{name: payload.payload for name, payload in inputs.items()})
```

The contract is responsible for selecting which ports to include. **Ports whose key is absent from the returned dict are not passed as keyword arguments at all**, so Python's own default value for that parameter activates naturally. A contract should omit a port from the dict only when `has_default` is `True` for that port.

### `EndSentinel`

If the contract returns `EndSentinel`, the node stops running and propagates an end sentinel to all downstream edges.

Use this when the contract has determined that the node can no longer make progress and should terminate cleanly.

## What `process_outputs()` Should Return

The output contract is called once per value the module emits, after the harness has resolved which port the value belongs to:

```python
def process_outputs(self, port: str, value: Any) -> Any:
```

It returns the value that actually travels downstream. Returning `value` unchanged is a no-op pass-through.

Things to know:

- **The port is read-only.** Only the return value is used, so a contract transforms payloads; it cannot reroute them to a different port or suppress them. A value returned as `None` is still dispatched as `None`, not dropped.
- **It runs before destination lookup**, so it also sees values emitted on ports with no wired downstream edge (those are logged `no_destination` and dropped afterwards).
- **It sees `finalise()` output too.** Values emitted by `module.finalise()` go through the same path as values from `run()`.
- **It is not called for `EndSentinel`.** Termination propagates directly to downstream ports without passing through the contract.
- It may be sync or async; the harness awaits it when it is a coroutine function.

`port` is the resolved external port name — `"default"` when the module emitted a bare value rather than a `(port, value)` tuple.

## Termination Rules

Contracts should be explicit about how they handle upstream end conditions.

Typical choices are:

- end when any required port ends
- end when all ports end
- end when a trigger port ends
- end when a group/join condition can no longer be satisfied

Be deliberate here. Contract termination is part of graph liveness behavior.

Two useful examples in the current codebase:

- [src/rtl_comrade/contract_default.py](../../src/rtl_comrade/contract_default.py): ends when any required input ends
- [contracts/zip.py](../../contracts/zip.py): zip-style behavior; if any port ends, the node ends, and mismatched endings are logged as an error

## Minimal Contract Template

This is the smallest useful shape for an input contract:

```python
from dataclasses import dataclass
from rtl_comrade.api import Payload, EndSentinel, ContractPort

@dataclass
class MyContract:
    id: str
    ports: dict[str, ContractPort]

    async def get_inputs(self) -> dict[str, Payload] | EndSentinel:
        a = await self.ports["a"].get()
        b = await self.ports["b"].get()

        if isinstance(a, EndSentinel) or isinstance(b, EndSentinel):
            return EndSentinel(self.id)

        return {"a": a, "b": b}
```

## Contract Serving Both Ends

One class may fill both roles: define `get_inputs` and `process_outputs` on it and name it as the node's `contract`. The two methods share `self` and the same `ContractPort` objects, so the input end can leave a note for the output end — but remember that `process_outputs` runs outside the read window, so state saved on `self` or in `port.state` is reachable there while `get()` and `try_get()` are not.

## Contract With Config

If you need contract configuration, define a nested `Config` type and accept `config` in `__init__`.

```python
from dataclasses import dataclass
from serde import serde, field
from rtl_comrade.api import Payload, EndSentinel, ContractPort

@dataclass
class TriggerOnContract:
    id: str
    ports: dict[str, ContractPort]
    trigger_port: str

    @serde
    class Config:
        trigger_port: str = "trigger"

    def __init__(self, id: str, config: Config, ports: dict[str, ContractPort]):
        self.id = id
        self.ports = ports
        self.trigger_port = config.trigger_port

    async def get_inputs(self) -> dict[str, Payload] | EndSentinel:
        trigger = await self.ports[self.trigger_port].get()
        if isinstance(trigger, EndSentinel):
            return EndSentinel(self.id)

        return {self.trigger_port: trigger}
```

## Using Default Values

If a module input has a Python default value in its `run(...)` signature, `has_default` on the corresponding `ContractPort` is `True`.

The contract signals that a default-valued port should use its Python default by **leaving that port's key out of the returned dict**. The harness then calls `module.run()` without that keyword argument, and Python's own default mechanism applies.

A destination port may be marked `required: true` in the graph config (see [graph.md](../harness_configs/graph.md)). The built-in default contract sets `is_special()` to `False` for such ports, so it always awaits a real value and never falls back to the default, even when `has_default` is `True`. A custom contract reads `ContractPort.required` to honor the same intent.

The built-in default contract shows the intended pattern.

### Actual precedence in `DefaultContract`

The built-in default contract uses this precedence order when assembling one invocation:

1. required ports — block until a real value arrives
2. special ports with a queued payload — consume it eagerly via `try_get()`
3. persistent ports with a cached last value — reuse it
4. default-valued ports with nothing queued — omit the key; Python default activates

That ordering matters if you are trying to implement a contract with similar persistent/default behavior.

## Using Contract-Owned State

Contracts are free to keep their own state across invocations.

Common patterns include:

- latest-value caches
- per-key join maps
- seen/end tracking
- persistent-input markers

You can store state:

- on `self`
- in individual `ContractPort.state` dicts

Prefer `self` for most policy state. Use `port.state` when the state is conceptually owned by that port.

In the current codebase, `DefaultContract` stores persistent-input state in each port's `state` dict, so contracts are already expected to be comfortable with port-local mutable state when it fits the policy.

When a node has separate input and output contracts, `self` is private to each but `port.state` is shared between them — it is the only channel the two have. Pick keys defensively if you expect your contract to be paired with an unknown counterpart; a collision silently overwrites.

## Logging Guidance

Logging participates in harness failure semantics.

- `DEBUG`, `INFO`, and `WARNING` are normal observability levels
- `ERROR` allows execution to continue but causes a failing exit at the end
- `CRITICAL` exits immediately

For contracts, this usually means:

- use `ERROR` for mismatches or broken runtime assumptions where best-effort continuation is still acceptable
- use `CRITICAL` only for situations that should stop the process immediately
- use normal exceptions only when you intend node execution to escalate through the harness fatal path

In the current codebase, many unexpected exceptions during `get_inputs()` are caught by `Node.run()` and escalated via fatal logging. `process_outputs()` is guarded the same way by `Node.process_result()`: `typer.Exit` propagates, `IllegalGetAccessError` is reported as `illegal_get_access`, and anything else is fatal with `exc_info`.

The two shipped contracts illustrate a useful split:

- [contracts/zip.py](../../contracts/zip.py) uses `ERROR` for a runtime mismatch in stream endings, then returns `EndSentinel`
- [src/rtl_comrade/contract_default.py](../../src/rtl_comrade/contract_default.py) uses fatal logging for broken invariants such as invalid persistent-port configuration

## Manifest Registration

To expose a contract plugin by name, add it to a plugin file and register it in a manifest.

Current example:

- [contracts/zip.py](../../contracts/zip.py)
- [contracts/config.yaml](../../contracts/config.yaml)

Example manifest entry:

```yaml
files:
- file: zip.py
  plugins:
  - name: zip
    class_name: ZipContract
```

The graph can then refer to that contract by its exported name:

```yaml
nodes:
- id: add
  module: add
  contract: zip
```

The same registry serves all three slots, so an exported name can be used as `contract`, `input_contract`, or `output_contract` — the harness only checks it has the method that slot requires.

## Design Advice

- Keep scheduling policy in the contract, not in the module.
- Decide termination behavior early; it is part of the contract's semantics.
- Be conservative around `EndSentinel`.
- Treat `ContractPort` objects as part of the runtime API surface.
- Prefer a single-role class unless the two ends genuinely share state. A separate `output_contract` composes with any input contract; one class doing both is only reusable as a pair.
- Keep `process_outputs` cheap and total. It sits on the dispatch path for every emitted value, and it has no way to signal "skip this one".
- If your contract relies on nontrivial state or matching rules, add or update an example graph/module pair so the behavior stays executable.

## Current Limitations To Keep In Mind

- static validation is only loosely contract-aware
- the harness assumes contracts ultimately return payload dicts keyed by module input name
- contracts that rely on highly dynamic runtime behavior may be valid even when static validation cannot fully prove them
- `process_outputs` can transform a value but cannot change its port, suppress it, or emit more than one value in its place
- output-side behaviour is invisible to static validation: emitted port names are still checked against the module's inferred emits, so a contract that changes a value's shape can break a downstream module without any load-time warning
- `run_contract_scenario` exercises `get_inputs()` only; output contracts have no dedicated test harness (see [testing.md](testing.md))
