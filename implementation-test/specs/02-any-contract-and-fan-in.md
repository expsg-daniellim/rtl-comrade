# Spec 02: `any` contract (retained, currently unwired)

> **Scope reduced by TODO #15 (item 27).** The `fan-in-results` module this spec used to
> build is **removed** — terminal re-convergence is no longer a graph node; the summary is a
> logging plugin (see [spec 10](10-control-aggregate-modules.md)). The `any` contract below is
> **retained** as a plain, general-purpose, reusable contract, but it has **no consumer in the
> `test` graph** and wiring it is not part of building the `test` graph. Build it only if/when
> another graph needs it. (It briefly also hosted the interim parallel-safety shim's
> `release_lock` hook; that shim was removed entirely by TODO #30 in favour of per-tag artefact
> naming, so the hook is gone.) The `FanInResultsMod` deliverable and `test_fan_in.py` below
> are struck through.

**Depends on:** harness non-definite-inputs support (already landed: `graph.py:95-97`
populates ports from edges when `run()` uses `**kwargs`).
**References:** [05 — Re-convergence](../05-branching-and-results.md#re-convergence-the-summary-is-a-logging-concern-not-a-graph-node),
[07 items 19, 27](../07-ambiguities-and-assumptions.md).

## Before you start

Read `docs/contracts/implementation.md` — the `get_inputs()` interface, the `ContractPort` API
(`get`/`try_get`/`has_ended`/`has_default`/`state`), the termination rules around
`EndSentinel`, and contract-owned state; `docs/contracts/index.md` and the per-contract files
under `contracts/` catalogue the shipped contracts. The `any` contract is a standalone plugin
(`contracts/any.py`, tests in `contracts/tests/test_any.py`) with no sibling specs appending to
the same file.

## Goal

Implement the **`any` contract** — a general-purpose scheduling contract that fires on any
single ready port, one delivery at a time, and propagates `EndSentinel` once all ports have
ended. Broadly reusable; it was originally built for the (now-removed) `fan-in-results` relay
and replaced the earlier `MergeContract` design, without requiring any harness change. It is
kept here as reusable infrastructure even though the `test` graph no longer wires it.

## Algorithm — `get_inputs()`

1. **Top up pending reads.** For every port that has not ended and has no in-flight task,
   schedule one: `self._pending[name] = asyncio.ensure_future(port.get())`. Tasks created in an
   earlier call that were not yet returned stay in `_pending` — never cancel them, or their item
   is lost.
2. **Wait for the first ready port.** While `_pending` is non-empty,
   `await asyncio.wait(self._pending.values(), return_when=FIRST_COMPLETED)`.
3. **Drain the wake-up one at a time.** Scan the pending tasks; for each completed one, pop it
   from `_pending` and read its result. A real payload is returned immediately as `{name: val}`
   (delivered under the port's own name), leaving any other simultaneously-ready tasks in
   `_pending` for the next call (the no-loss invariant for multi-done wake-ups). An `EndSentinel`
   is consumed silently and the scan continues to the next ready port.
4. **Terminate.** When `_pending` drains to empty (all ports have ended), return
   `EndSentinel(self.id)`.

## Deliverables

### `contracts/any.py` — `AnyContract`

```python
@dataclass
class AnyContract:
    """Fire on any single ready port; end when all ports end."""

    id: str
    ports: dict[str, ContractPort]
    _pending: dict[str, asyncio.Task] = field(default_factory=dict, init=False, repr=False)

    async def get_inputs(self) -> dict[str, Payload] | EndSentinel:
        for name, port in self.ports.items():
            if not port.has_ended() and name not in self._pending:
                self._pending[name] = asyncio.ensure_future(port.get())

        while self._pending:
            done, _ = await asyncio.wait(self._pending.values(), return_when=asyncio.FIRST_COMPLETED)
            for name, task in list(self._pending.items()):
                if task not in done:
                    continue
                val = task.result()
                del self._pending[name]
                if isinstance(val, EndSentinel):
                    continue
                return {name: val}   # delivered under the port's own name

        return EndSentinel(self.id)
```

`AnyContract` is a **plain** contract with no `Config` and no side-effects. (An earlier draft
carried a `release_lock: str | None` field as an interim hook for the parallel-safety shim;
the shim was removed entirely by TODO #30 in favour of per-tag artefact naming, so the field —
and the `contracts/serial.py` `_LOCKS` registry it used — are gone.)

Manifest entry in `contracts/config.yaml`:

```yaml
- file: any.py
  plugins:
  - { name: any, class_name: AnyContract }
```

### ~~`modules/rtl_test/control.py` — `FanInResultsMod`~~ (removed by TODO #15)

The relay module is **not built**. Terminal ports are unwired and the summary is rendered by
the `SummaryProcessor` logging plugin ([spec 10](10-control-aggregate-modules.md)). The
remainder of this deliverable is retained only as the historical design for `any`'s original
consumer.

### `contracts/tests/test_any.py`

Enumerated as `port_inputs → expected_outputs` cases in the [`## Tests`](#tests) section
below (driven by `run_contract_scenario`).

### ~~`modules/tests/test_fan_in.py`~~ (removed by TODO #15)

Not built — `FanInResultsMod` is removed.

## Tests

In `contracts/tests/test_any.py`, driven by `run_contract_scenario(AnyContract,
port_inputs=…, expected_outputs=…)` (the contract-test harness — see
`docs/contracts/testing.md`). A 3-port fixture (`a`/`b`/`c`) unless noted; `EndSentinel("src")`
terminates a port; `PortTestInput(value, delay=N)` defers delivery to reach blocking-await
branches.

**Behavioural cases** (`port_inputs → expected_outputs`):

- `{"a": [1, End], "b": [End], "c": [End]}` → `[{"a": 1}, EndSentinel]` (a single item is
  delivered under its own port name).
- `{"a": [1, End], "b": [2, End], "c": [3, End]}` → the three `{name: val}` deliveries (each
  exactly once, none lost) followed by `EndSentinel` (interleaved across ports).
- `{"a": [End], "b": [2, End], "c": [3, End]}` → keeps delivering `{"b": 2}`/`{"c": 3}` then
  `EndSentinel` (an early `EndSentinel` on one port is consumed silently, others still drain).
- `{"a": [End], "b": [End], "c": [End]}` → `[EndSentinel]` (boundary: all ports already ended →
  immediate `EndSentinel(self.id)`, no delivery).
- **No-loss / one-at-a-time** — `{"a": [1, End], "b": [2, End]}` (both pre-loaded, ready in the
  same `asyncio.wait` wake-up) → `[{"a": 1}, {"b": 2}, EndSentinel]`: the first `get_inputs()`
  returns exactly one dict, the second returns the other without re-awaiting that port.
- **Drainage FIFO** — `{"a": [p1, p2, End], "b": [End], "c": [End]}` → `[{"a": p1}, {"a": p2},
  EndSentinel]` (both payloads in FIFO order before the sentinel is consumed).
- **Blocking-await** — a required port pre-loaded while a secondary port carries
  `PortTestInput(9, delay=1)` then `PortTestInput(End, delay=2)` → the deferred `{name: 9}` is
  still delivered (exercises the `await asyncio.wait` branch unreachable with fully pre-loaded
  queues).

**Construction-time tests:** none required — `AnyContract` is plain (no `Config`, no `fan_in`
mapping to validate; `run_contract_scenario` still asserts the structural load-time rules).

**Stress test** (≥13 ports): each port produces 100 payloads under `asyncio.create_task` with
randomised `await asyncio.sleep(0)` interleavings, then `EndSentinel` → exactly `13 × 100`
payloads delivered, each once, and `get_inputs()` returns `EndSentinel(self.id)` only after the
last payload (not flaky across 100 invocations under `pytest -p no:randomly`).

**Property-based test** (`hypothesis` or equivalent): randomised `(port_count, items_per_port,
interleaving_seed)` over ≥100 cases → the multiset of delivered payloads equals the multiset
produced upstream, and the contract terminates within bounded steps after all ports end.

## Acceptance criteria

- All enumerated `test_any.py` tests pass.
- Stress test is not flaky across 100 invocations under `pytest -p no:randomly`.
- Property-based test runs ≥100 generated cases with no falsifying input.
- `docs/contracts/index.md` promotion is **deferred** until the `any` contract is actually
  wired into a graph (it is unwired in `test` per TODO #15). When that happens, add a
  first-class entry listing invariants (mirrored from
  [05](../05-branching-and-results.md#the-any-contract-retained-currently-unwired)) and its
  reusability, per [`docs/creating-documentation.md`](../../docs/creating-documentation.md).
- The contract manifest entry `{ name: any, class_name: AnyContract }` in `contracts/config.yaml`
  validates and the harness resolves `any` → `AnyContract` (even though `graphs/test.yaml`
  leaves it unwired per TODO #15).

## Constraints

- **Never cancel an in-flight `_pending` task.** A task created in call N but not returned must
  survive in `_pending` to call N+1 — cancelling it loses that port's item (the no-loss
  invariant).
- Return **exactly one** `{name: payload}` per `get_inputs()` call (one delivery at a time);
  leave any other simultaneously-ready tasks in `_pending`.
- Deliver each payload under the **port's own name**, not a fixed key.
- Consume an `EndSentinel` silently and continue scanning; return `EndSentinel(self.id)` **only**
  once `_pending` is empty (all ports ended). Propagate the sentinel — never synthesise it early
  or swallow the terminal one (`docs/invariants.md` — EndSentinel).
- Keep it a **plain** contract: no `Config`, no side-effects. Do **not** reintroduce the removed
  `release_lock` field or any `_LOCKS` registry (TODO #30 removed the shim).

## Notes

The pending-task lifetime is the subtle part — tasks created in call N that are not
returned must remain in `_pending` and be honoured in call N+1. Do not cancel them; that
loses items.

`AnyContract` surfaces the port name to the module (in the `{name: val}` dict). Its original
consumer `fan-in-results` discarded the name; other potential consumers can use it. This is
simpler than `MergeContract`'s `fan_in` mapping and requires no construction-time validation.
