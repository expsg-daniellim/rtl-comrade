# Writing Contracts

This document explains how to implement a contract for `rtl-comrade`.

For harness internals behind contract instantiation, see:

- [docs/harness/node.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/node.md)
- [docs/harness/api.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/api.md)
- [docs/harness/contract_default.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/contract_default.md)

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

If the contract does not accept `ports`, the harness only logs a warning, but such a contract is rarely useful.

## The `ContractPort` API

Contracts do not receive raw queue objects. They receive `ContractPort` adapters.

Each `ContractPort` provides:

- `name`
- `get()`: async blocking read, returns `Payload` or `EndSentinel`
- `try_get()`: non-blocking read, returns `Payload`, `EndSentinel`, or `None`
- `has_ended()`: whether the port has already seen an end sentinel
- `has_default`: whether the corresponding module parameter has a Python default value
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

- [src/rtl_comrade/contract_default.py](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade/contract_default.py): ends when any required input ends
- [contracts/contracts.py](/Users/daniellim/Documents/random/rtl-comrade/contracts/contracts.py): zip-style behavior; if any port ends, the node ends, and mismatched endings are logged as an error

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

- [contracts/contracts.py](/Users/daniellim/Documents/random/rtl-comrade/contracts/contracts.py) uses `ERROR` for a runtime mismatch in stream endings, then returns `EndSentinel`
- [src/rtl_comrade/contract_default.py](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade/contract_default.py) uses fatal logging for broken invariants such as invalid persistent-port configuration

## Manifest Registration

To expose a contract plugin by name, add it to a plugin file and register it in a manifest.

Current example:

- [contracts/contracts.py](/Users/daniellim/Documents/random/rtl-comrade/contracts/contracts.py)
- [contracts/config.yaml](/Users/daniellim/Documents/random/rtl-comrade/contracts/config.yaml)

Example manifest entry:

```yaml
files:
- file: contracts.py
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

## Testing Contracts

`rtl_comrade.testing` provides `run_contract_scenario()` for testing contract scheduling logic in isolation — no graph, no module, no runtime required.

```python
from rtl_comrade.api import EndSentinel
from rtl_comrade.testing import run_contract_scenario, PortMeta, PortTestInput
```

### Basic usage

```python
await run_contract_scenario(
    MyContract,
    port_inputs={
        "a": [1, 2, EndSentinel("src")],
        "b": [10, 20, EndSentinel("src")],
    },
    expected_outputs=[
        {"a": 1, "b": 10},
        {"a": 2, "b": 20},
        EndSentinel,
    ],
    config=MyContract.Config(),
)
```

The harness creates one `Port` per key in `port_inputs`, enqueues items according to their delay, instantiates the contract, then calls `get_inputs()` once per entry in `expected_outputs` and asserts the result matches.

### `port_inputs`

Maps each port name to a list of values to feed that port in order. Each item may be:

- A raw Python value — auto-wrapped as `Payload(source="test", n=<index>, payload=val)` and delivered immediately (before `get_inputs()` is called)
- A `Payload` or `EndSentinel` instance — passed through unchanged, delivered immediately
- A `PortTestInput(value, delay=N)` — wraps any of the above with a delivery delay

### Asynchronous item delivery with `PortTestInput`

By default all items are pre-enqueued before `get_inputs()` runs. Wrapping an item in `PortTestInput` with `delay=N` (N ≥ 1) delivers it after N `asyncio.sleep(0)` yields while the contract is already running. This lets tests exercise blocking-await paths that are unreachable when queues are fully pre-loaded.

```python
await run_contract_scenario(
    KeyedJoinContract,
    port_inputs={
        "a": [{"id": 1}, EndSentinel("src")],          # pre-enqueued
        "b": [PortTestInput({"id": 1}, delay=1),        # delivered after 1 yield
              PortTestInput(EndSentinel("src"), delay=2)],
    },
    expected_outputs=[{"a": {"id": 1}, "b": {"id": 1}}, EndSentinel],
    config=KeyedJoinContract.Config(key_field="id"),
)
```

When any deferred items exist the harness runs the assertion loop and the feeder concurrently via `asyncio.gather`. Items at the same `delay` level are delivered together in a single tick.

### `expected_outputs`

One entry per `get_inputs()` call.

| Entry type | Assertion |
|---|---|
| `dict[str, Any]` | Each key's `.payload` equals the given value; `source`/`n` are ignored |
| `EndSentinel` (class or instance) | Result must be an `EndSentinel` |

### Ports with defaults

Use `port_meta` to mark individual ports as `has_default=True`, matching what the harness derives from the module signature:

```python
await run_contract_scenario(
    MyContract,
    port_inputs={"a": [1, EndSentinel("src")], "b": []},
    expected_outputs=[{"a": 1}, EndSentinel],
    port_meta={"b": PortMeta(has_default=True)},
    config=MyContract.Config(),
)
```

When a default-valued port has nothing queued the contract omits its key from the returned dict, so `"b"` does not appear in `expected_outputs` for that step. Ports not listed in `port_meta` default to `has_default=False`.

### Optional kwargs

| Kwarg | Default | Purpose |
|---|---|---|
| `config` | `None` | Passed to `__init__` only when the contract declares `config` |
| `contract_id` | `"test.contract"` | The `id` string passed to the contract |
| `timeout` | `5.0` | Maximum seconds to wait for each `get_inputs()` call; applies per-step when deferred items are present |

### Validation

`run_contract_scenario` asserts the same structural rules the harness enforces:

- the contract exposes `get_inputs` (mirrors `graph.py` load-time check)
- `__init__` is inspectable (mirrors `node.py` instantiation guard)
- `__init__` declares `ports` (mirrors `node.py` no-ports warning, promoted to an assertion)

These fire as `AssertionError` before any `get_inputs()` calls, so a mis-wired contract class fails at test collection time rather than silently at runtime.

### Coverage Target

Run coverage against a single contract file:

```bash
uv run pytest contracts/tests/test_mycontract.py --cov=contracts/mycontract.py --cov-report=term-missing
```

The missing-lines report shows exactly which branches remain uncovered. Aim for 100% on every contract file before merging.

Key branches to cover:

**Normal paths**

- At least one call that returns a full `dict` of payloads (one per required port).
- Each distinct scheduling variant if your contract has multiple modes (e.g., persistent-value reuse vs. fresh read).

**Termination paths**

- Every `EndSentinel` return. If your contract ends on any port ending, test both the first-port-ends and last-port-ends cases. If it ends only when all ports end, test both partial-end and full-end.

**Blocking-await paths**

Pre-loading all items before `get_inputs()` is called means queues are never empty during a call — `await port.get()` returns immediately and `try_get()` never returns `None`. To reach these branches:

- Use `PortTestInput(value, delay=N)` (N ≥ 1) so the item arrives after the contract has already started waiting.
- Use `try_get()` → `None` paths by leaving a port queue empty at the point the contract drains it; a `delay=1` on a secondary port while a required port is pre-loaded is the usual pattern.

**Error and mismatch paths**

- If your contract logs `ERROR` (e.g., mismatched stream endings), include a test that triggers it and asserts `logging_handler.failure is True` after the scenario.
- If your contract calls `log.fatal` / `log.critical` for invariant violations, include a test with `pytest.raises(SystemExit)`.

**State edge cases**

Cover every distinct state a port can be in at call time — no-last-value persistent port, a default port whose upstream has ended (key is omitted from the result), a port that transitions from live to ended mid-sequence.

## Design Advice

- Keep scheduling policy in the contract, not in the module.
- Decide termination behavior early; it is part of the contract’s semantics.
- Be conservative around `EndSentinel`.
- Treat `ContractPort` objects as part of the runtime API surface.
- If your contract relies on nontrivial state or matching rules, add or update an example graph/module pair so the behavior stays executable.

## Current Limitations To Keep In Mind

- static validation is only loosely contract-aware
- the harness assumes contracts ultimately return payload dicts keyed by module input name
- contracts that rely on highly dynamic runtime behavior may be valid even when static validation cannot fully prove them

If you want, I can also add a companion `docs/module-implementation.md` so the repository has symmetric authoring guides for both plugin types.
