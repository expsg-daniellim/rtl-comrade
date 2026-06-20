# Writing Contracts

This document explains how to implement a contract for `rtl-comrade`.

For harness internals behind contract instantiation, see:

- [docs/harness/node.md](../harness/node.md)
- [docs/harness/api.md](../harness/api.md)
- [docs/harness/contract_default.md](../harness/contract_default.md)

For testing contracts in isolation, see [testing.md](testing.md).

## What A Contract Is

A contract is the scheduling policy for a node.

The module defines what work the node performs. The contract defines when the node is allowed to run and which input payloads should be supplied for that invocation.

Examples:

- a zip-style contract waits for one item from each input
- a latest-value contract might cache one input and trigger on another
- a keyed-join contract might wait until all required ports for a given key are present

That means scheduling logic belongs in contracts, not in modules.

## Required Interface

A contract is a plain Python class discovered from a plugin file.

At minimum:

- it must expose `get_inputs()`
- `get_inputs()` may be sync or async
- `get_inputs()` must return either `dict[str, Payload]` or `EndSentinel`

In practice, a useful contract should also accept `ports` in `__init__`.

## How The Harness Instantiates A Contract

`Node` inspects the contract constructor and only injects arguments that the constructor explicitly accepts.

Possible injected arguments are:

- `config`
- `id`
- `ports`

### `config`

If `__init__` accepts `config`, the harness passes `contract_config` from the graph YAML.

If the contract defines a nested `Config` class, that config is deserialized through `serde.from_dict(...)` before construction.

### `id`

If `__init__` accepts `id`, the harness passes:

```python
"<node-id>.contract"
```

This is useful for logging and debugging.

### `ports`

If `__init__` accepts `ports`, the harness passes:

```python
dict[str, ContractPort]
```

This is the normal contract input surface.

In the current implementation, this mapping preserves the module input declaration order. Order-sensitive contracts may rely on that, as the shipped zip-style example does.

For a module with non-definite inputs (a `run(...)` signature using `*args` or `**kwargs`), there is no signature-derived declaration order: the harness builds `ports` from the node's incoming edges instead. A contract paired with such a module should key into `ports` by name and not assume a signature-defined ordering.

If the contract does not accept `ports`, the harness only logs a warning, but such a contract is rarely useful.

## The `ContractPort` API

Contracts do not receive raw queue objects. They receive `ContractPort` adapters.

Each `ContractPort` provides:

- `name`
- `get()`: async blocking read, returns `Payload` or `EndSentinel`
- `try_get()`: non-blocking read, returns `Payload`, `EndSentinel`, or `None`
- `has_ended()`: whether the port has already seen an end sentinel
- `has_default`: whether the corresponding module parameter has a Python default value
- `required`: whether the graph config marks this port required; the built-in default contract awaits a real value and ignores `has_default` for such ports
- `state`: a dict for contract-owned per-port state

Important details:

- `get()` waits until an item is available
- `try_get()` treats an empty queue as normal and returns `None`
- contracts should store per-port state inside `port.state`, not by attaching ad hoc attributes directly to the `ContractPort` object

The built-in default contract uses `port.state` keys such as `persistent` and `last_value`.

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

This is the smallest useful shape:

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

## Logging Guidance

Logging participates in harness failure semantics.

- `DEBUG`, `INFO`, and `WARNING` are normal observability levels
- `ERROR` allows execution to continue but causes a failing exit at the end
- `CRITICAL` exits immediately

For contracts, this usually means:

- use `ERROR` for mismatches or broken runtime assumptions where best-effort continuation is still acceptable
- use `CRITICAL` only for situations that should stop the process immediately
- use normal exceptions only when you intend node execution to escalate through the harness fatal path

In the current codebase, many unexpected exceptions during `get_inputs()` are caught by `Node.run()` and escalated via fatal logging.

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

## Design Advice

- Keep scheduling policy in the contract, not in the module.
- Decide termination behavior early; it is part of the contract's semantics.
- Be conservative around `EndSentinel`.
- Treat `ContractPort` objects as part of the runtime API surface.
- If your contract relies on nontrivial state or matching rules, add or update an example graph/module pair so the behavior stays executable.

## Current Limitations To Keep In Mind

- static validation is only loosely contract-aware
- the harness assumes contracts ultimately return payload dicts keyed by module input name
- contracts that rely on highly dynamic runtime behavior may be valid even when static validation cannot fully prove them
