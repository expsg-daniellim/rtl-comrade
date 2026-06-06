# Spec 02: `any` contract and `fan-in-results` module

**Depends on:** harness non-definite-inputs support (already landed: `graph.py:95-97`
populates ports from edges when `run()` uses `**kwargs`).
**References:** [05 — Re-convergence](../05-branching-and-results.md#re-convergence-the-fan-in-module-and-any-contract),
[07 item 19](../07-ambiguities-and-assumptions.md).

## Goal

Implement two tightly paired pieces:

1. **`any` contract** — a general-purpose scheduling contract that fires on any single
   ready port, one delivery at a time, and propagates `EndSentinel` once all ports have
   ended. Broadly reusable beyond `fan-in-results`.
2. **`fan-in-results` module** — a thin relay module that accepts the 13 terminal-result
   branches as `**kwargs` edge-derived ports and normalises each delivery to the single
   `result` output expected by `aggregate-results`.

Together they replace the earlier `MergeContract` design, without requiring any harness
change.

## Deliverables

### `contracts/any.py` — `AnyContract`

```python
@dataclass
class AnyContract:
    """Fire on any single ready port; end when all ports end."""

    @dataclass(frozen=True)
    class Config:
        release_lock: str | None = None

    id: str
    ports: dict[str, ContractPort]
    config: Config
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
                if self.config.release_lock is not None:
                    _get_lock(self.config.release_lock).release()
                return {name: val}   # delivered under the port's own name

        return EndSentinel(self.id)
```

The `_get_lock` registry and `SerialAcquireContract` live in `contracts/serial.py` (per
TODO #3); `AnyContract` imports `_get_lock` from there so both contracts share the same
`_LOCKS` dict at runtime. The `release_lock` field is an **interim hook** for the
parallel-safety shim (TODO #30) — not part of the contract's first-class surface.

Manifest entry in `contracts/config.yaml`:

```yaml
- file: any.py
  plugins:
  - { name: any, class_name: AnyContract }
```

### `modules/rtl_test/control.py` — `FanInResultsMod`

```python
class FanInResultsMod:
    def run(self, **inputs):
        _, payload = next(iter(inputs.items()))
        return ("result", payload)
```

The module's `**inputs` parameter makes it non-definite; the harness populates its ports
from the 13 incoming graph edges at load time (`graph.py:95-97`). Each call receives
exactly one `{port_name: payload}` entry (guaranteed by `any` contract's one-at-a-time
delivery). The port name is discarded — provenance is already encoded in the payload type
(`CompileFailResults`, `SimTimeoutResults`, etc.).

Manifest entry in `modules/config.yaml` (append to `rtl_test/control.py` plugin list):

```yaml
- { name: fan-in-results, class_name: FanInResultsMod }
```

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

**Construction-time / misconfiguration tests**: none required — `AnyContract` has no
`fan_in` mapping to validate. The only configured field is `release_lock`; its
misconfiguration (no matching acquire) surfaces at runtime as `RuntimeError` from
`asyncio.Lock.release()`, covered by the pairing-arithmetic tests in TODO #30.

**Stress test** (≥13 ports): each port produces 100 payloads under
`asyncio.create_task` with randomised `await asyncio.sleep(0)` interleavings, then emits
`EndSentinel`. Assertions:
- exactly `13 × 100` payloads delivered, each exactly once;
- `get_inputs()` returns `EndSentinel(self.id)` after the last payload and not before.

**Property-based test** (`hypothesis` or equivalent): randomised `(port_count,
items_per_port, interleaving_seed)` tuples. For each generated case, assert:
- the multiset of delivered payloads equals the multiset produced upstream;
- the contract terminates within bounded steps after all ports end.

### `modules/tests/test_fan_in.py`

- single input → forwarded as `result`.
- payload identity preserved (same object reference or equal value).
- module does not branch on port name (parametrised across port names).

## Acceptance criteria

- All enumerated tests pass.
- Stress test is not flaky across 100 invocations under `pytest -p no:randomly`.
- Property-based test runs ≥100 generated cases with no falsifying input.
- `any` contract promoted to `docs/contracts/index.md` as a first-class shipped contract:
  entry lists invariants (mirrored from
  [05](../05-branching-and-results.md#re-convergence-the-fan-in-module-and-any-contract)),
  notes the optional `release_lock` field as an interim hook per TODO #30, and states
  reusability beyond `fan-in-results`. Per
  [`docs/creating-documentation.md`](../../docs/creating-documentation.md).

## Notes

The pending-task lifetime is the subtle part — tasks created in call N that are not
returned must remain in `_pending` and be honoured in call N+1. Do not cancel them; that
loses items.

`AnyContract` surfaces the port name to the module (in the `{name: val}` dict). For
`fan-in-results` the port name is discarded; for other potential consumers it is available.
This is simpler than `MergeContract`'s `fan_in` mapping and requires no construction-time
validation.
