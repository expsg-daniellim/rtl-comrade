# Testing Contracts

For implementation details, see [implementation.md](implementation.md).

`rtl_comrade.testing` provides `run_contract_scenario()` for testing contract scheduling logic in isolation — no graph, no module, no runtime required.

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

## Optional kwargs

| Kwarg | Default | Purpose |
|---|---|---|
| `config` | `None` | Passed to `__init__` only when the contract declares `config` |
| `contract_id` | `"test.contract"` | The `id` string passed to the contract |
| `timeout` | `5.0` | Maximum seconds to wait for each `get_inputs()` call; applies per-step when deferred items are present |

## Validation

`run_contract_scenario` asserts the same structural rules the harness enforces:

- the contract exposes `get_inputs` (mirrors `graph.py` load-time check)
- `__init__` is inspectable (mirrors `node.py` instantiation guard)
- `__init__` declares `ports` (mirrors `node.py` no-ports warning, promoted to an assertion)

These fire as `AssertionError` before any `get_inputs()` calls, so a mis-wired contract class fails at test collection time rather than silently at runtime.

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
- If your contract calls `log.fatal` / `log.critical` for invariant violations, include a test with `pytest.raises(SystemExit)`.

**State edge cases**

Cover every distinct state a port can be in at call time — no-last-value persistent port, a default port whose upstream has ended (key is omitted from the result), a port that transitions from live to ended mid-sequence.
