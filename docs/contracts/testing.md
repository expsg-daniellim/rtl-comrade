# Testing Contracts

For implementation details, see [implementation.md](implementation.md).

`rtl_comrade.testing` provides `run_contract_scenario()` for testing contract scheduling logic in isolation — no graph, no module, no runtime required.

It covers the **input** end only: it drives `get_inputs()` and asserts what comes back. There is no equivalent harness for `process_outputs()` — an output contract is tested by calling the method directly, since it takes its port name and value as plain arguments and needs no queue setup.

```python
from rtl_comrade.api import EndSentinel
from rtl_comrade.testing import run_contract_scenario, PortMeta, PortTestInput
```

## Basic usage

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

It also reproduces the harness's port read window: ports are enabled immediately before each `get_inputs()` call and disabled immediately after, exactly as `Node.run` does. A contract that stashes a `ContractPort` and reads it after its call returned raises `IllegalGetAccessError` under test just as it would in a real graph, so that bug is caught here rather than at runtime. See [../harness/port.md](../harness/port.md).

## `port_inputs`

Maps each port name to a list of values to feed that port in order. Each item may be:

- A raw Python value — auto-wrapped as `Payload(source="test", n=<index>, payload=val)` and delivered immediately (before `get_inputs()` is called)
- A `Payload` or `EndSentinel` instance — passed through unchanged, delivered immediately
- A `PortTestInput(value, delay=N)` — wraps any of the above with a delivery delay

## Asynchronous item delivery with `PortTestInput`

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

## `expected_outputs`

One entry per `get_inputs()` call.

| Entry type | Assertion |
|---|---|
| `dict[str, Any]` | Each key's `.payload` equals the given value; `source`/`n` are ignored |
| `EndSentinel` (class or instance) | Result must be an `EndSentinel` |

## Ports with defaults

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

`PortMeta` also accepts `branch_labels` (a `frozenset`, default empty) to set the control-dependence labels the harness would assign during graph construction — ports given equal `branch_labels` are co-fated. Use this to test branch-aware contracts (`branch_aware_join`, and the partition-aware error paths of `keyed_join` / `zip` / `unit`): give two ports the same labels to make them co-fated arms, or leave a port's labels empty to mark it an unconditional participant. See [branch_labels.md](../harness/branch_labels.md).

`PortMeta` also accepts `required=True` to mark a port required, matching a destination marked `required: true` in the graph config. The built-in default contract then awaits a real value on that port even when `has_default=True`, so the key is never omitted. Pair it with `PortTestInput(value, delay=N)` to assert the contract blocks rather than falling back to the default:

```python
await run_contract_scenario(
    MyContract,
    port_inputs={"a": [1], "b": [PortTestInput(99, delay=1)]},
    expected_outputs=[{"a": 1, "b": 99}],
    port_meta={"b": PortMeta(has_default=True, required=True)},
    config=MyContract.Config(),
)
```

## Optional kwargs

| Kwarg | Default | Purpose |
|---|---|---|
| `config` | `None` | Passed to `__init__` only when the contract declares `config` |
| `contract_id` | `"test.contract"` | The `id` string passed to the contract |
| `timeout` | `5.0` | Maximum seconds to wait for each `get_inputs()` call; applies per-step when deferred items are present |

## Validation

`run_contract_scenario` asserts the same structural rules the harness enforces:

- the contract exposes `get_inputs` (mirrors the input-role check in `contract.py`)
- `__init__` is inspectable (mirrors the `contract.py` instantiation guard)
- `__init__` declares `ports` (mirrors the `contract.py` no-ports warning, promoted to an assertion)

These fire as `AssertionError` before any `get_inputs()` calls, so a mis-wired contract class fails at test collection time rather than silently at runtime.

The scenario harness is input-side, so these assertions describe an input contract. A class intended only as an `output_contract` legitimately has no `get_inputs` and no `ports` parameter and will fail them — test it by calling `process_outputs` directly instead.

## Coverage Target

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
- If your contract calls `log.fatal` / `log.critical` for invariant violations, include a test with `pytest.raises(typer.Exit)`.

**State edge cases**

Cover every distinct state a port can be in at call time — no-last-value persistent port, a default port whose upstream has ended (key is omitted from the result), a port that transitions from live to ended mid-sequence.

**Output processing**

If your contract implements `process_outputs`, call it directly — it takes a port name and a value and needs no ports or queues. Cover every branch that varies by `port` name, and the sync/async form you declared. If the method depends on state written during `get_inputs()`, note that `run_contract_scenario` constructs the contract internally, so a test needing both ends usually builds the contract by hand and calls `get_inputs()` itself.
