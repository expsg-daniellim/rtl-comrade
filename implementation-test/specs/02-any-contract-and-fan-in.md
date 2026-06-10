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

## Goal

Implement the **`any` contract** — a general-purpose scheduling contract that fires on any
single ready port, one delivery at a time, and propagates `EndSentinel` once all ports have
ended. Broadly reusable; it was originally built for the (now-removed) `fan-in-results` relay
and replaced the earlier `MergeContract` design, without requiring any harness change. It is
kept here as reusable infrastructure even though the `test` graph no longer wires it.

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
the `SummaryHandler` logging plugin ([spec 10](10-control-aggregate-modules.md)). The
remainder of this deliverable is retained only as the historical design for `any`'s original
consumer.

### `contracts/tests/test_any.py`

**Behavioural tests** (a 3-port fixture unless noted):

- single item on one port → delivered under that port's name.
- items interleaved across multiple ports → all delivered, none lost.
- `EndSentinel` on one port while others still active → continue delivering from the rest.
- all ports ended → returns `EndSentinel(self.id)`.
- **no-loss invariant**: two ports ready in the same `asyncio.wait` wake-up — first call
  returns one, second call returns the other without re-awaiting the port.
- **drainage order**: a port queued with `[payload, payload, EndSentinel]` delivers both
  payloads in FIFO order before its sentinel is consumed.
- **one-at-a-time**: each `get_inputs()` call returns exactly one `{name: payload}` dict,
  never two.

**Construction-time / misconfiguration tests**: none required — `AnyContract` is a plain
contract with no `Config` and no `fan_in` mapping to validate.

**Stress test** (≥13 ports): each port produces 100 payloads under
`asyncio.create_task` with randomised `await asyncio.sleep(0)` interleavings, then emits
`EndSentinel`. Assertions:
- exactly `13 × 100` payloads delivered, each exactly once;
- `get_inputs()` returns `EndSentinel(self.id)` after the last payload and not before.

**Property-based test** (`hypothesis` or equivalent): randomised `(port_count,
items_per_port, interleaving_seed)` tuples. For each generated case, assert:
- the multiset of delivered payloads equals the multiset produced upstream;
- the contract terminates within bounded steps after all ports end.

### ~~`modules/tests/test_fan_in.py`~~ (removed by TODO #15)

Not built — `FanInResultsMod` is removed.

## Acceptance criteria

- All enumerated `test_any.py` tests pass.
- Stress test is not flaky across 100 invocations under `pytest -p no:randomly`.
- Property-based test runs ≥100 generated cases with no falsifying input.
- `docs/contracts/index.md` promotion is **deferred** until the `any` contract is actually
  wired into a graph (it is unwired in `test` per TODO #15). When that happens, add a
  first-class entry listing invariants (mirrored from
  [05](../05-branching-and-results.md#the-any-contract-retained-currently-unwired)) and its
  reusability, per [`docs/creating-documentation.md`](../../docs/creating-documentation.md).

## Notes

The pending-task lifetime is the subtle part — tasks created in call N that are not
returned must remain in `_pending` and be honoured in call N+1. Do not cancel them; that
loses items.

`AnyContract` surfaces the port name to the module (in the `{name: val}` dict). Its original
consumer `fan-in-results` discarded the name; other potential consumers can use it. This is
simpler than `MergeContract`'s `fan_in` mapping and requires no construction-time validation.
