# Spec 02: `any` contract (retained, currently unwired)

> **Scope:** this spec builds only the `any` contract — a plain, general-purpose, reusable scheduling contract. It has **no consumer in the `test` graph**: register it for reuse but leave it **unwired**. Wiring it into a graph is out of scope here; do that only if/when another graph needs it.

**References:** [05 — Re-convergence](../05-branching-and-results.md#re-convergence-the-summary-is-a-logging-concern-not-a-graph-node), [07 items 19, 27](../07-ambiguities-and-assumptions.md).

## Before you start

Read `docs/contracts/implementation.md` — the `get_inputs()` interface, the `ContractPort` API (`get`/`try_get`/`has_ended`/`has_default`/`state`), the termination rules around `EndSentinel`, and contract-owned state; `docs/contracts/index.md` and the per-contract files under `contracts/` catalogue the shipped contracts. The `any` contract is a standalone plugin (`contracts/any.py`, tests in `contracts/tests/test_any.py`) with no sibling specs appending to the same file.

## Goal

Implement the **`any` contract** — a general-purpose scheduling contract that fires on any single ready port, one delivery at a time, and propagates `EndSentinel` once all ports have ended. Broadly reusable, and registered as reusable infrastructure even though the `test` graph does not wire it.

A single config field `mapping` carries both modes, switched by type:

- a **`str`** is **n→1**: every input port funnels onto that one output port name (defaults to the harness's `"default"` port when `mapping` is unset).
- a **`dict[str, list[str]]`** is **m→n**: a `map[str] list[str]` of **output port → the input ports that feed it**. Every input port must appear in exactly one group; a port left unmapped is a construction-time fatal (no silent fallback).

At construction each port's output is resolved once into `port.state['output']` — the `str` for the whole fan-in, or the group that names the port — and every delivery reads it back from there.

## Algorithm — `get_inputs()`

1. **Top up pending reads.** For every port that has not ended and has no in-flight task, schedule one: `self.pending[name] = asyncio.ensure_future(port.get())`. Tasks created in an earlier call that were not yet returned stay in `pending` — never cancel them, or their item is lost.
2. **Wait for the first ready port.** While `pending` is non-empty, `await asyncio.wait(self.pending.values(), return_when=FIRST_COMPLETED)`.
3. **Drain the wake-up one at a time.** Scan the pending tasks; for each completed one, pop it from `pending` and read its result. A real payload is returned immediately as `{port.state['output']: val}` — the firing port's output port — leaving any other simultaneously-ready tasks in `pending` for the next call (the no-loss invariant for multi-done wake-ups). An `EndSentinel` is consumed silently and the scan continues to the next ready port.
4. **Terminate.** When `pending` drains to empty (all ports have ended), return `EndSentinel(self.id)`.

Because each call returns exactly one single-key dict, several input ports sharing one output port never collide — their values arrive as separate deliveries under the same key on successive calls.

## Deliverables

### `contracts/any.py` — `AnyContract`

```python
@dataclass
class AnyContract:
    """Fire on any single ready port; end when all ports end.

    Each delivery carries one ready port's value under its output port, resolved once into
    ``port.state['output']``. ``config.mapping`` is either a single port name (n→1: the whole
    fan-in funnels onto it) or an output-port → input-ports map (m→n: every input port must
    be assigned a group, else a construction error).
    """

    @dataclass(frozen=True)
    class Config:
        mapping: str | dict[str, list[str]] = "default"

    id: str
    ports: dict[str, ContractPort]
    config: Config
    pending: dict[str, asyncio.Task] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self):
        if isinstance(self.config.mapping, str):
            for port in self.ports.values():
                port.state['output'] = self.config.mapping
            return
        for output, in_ports in self.config.mapping.items():
            for name in in_ports:
                if name not in self.ports:
                    log.fatal('unknown_input_port', context='harness.contract.init', port=name)
                if 'output' in self.ports[name].state:
                    log.fatal('ambiguous_output_mapping', context='harness.contract.init', port=name)
                self.ports[name].state['output'] = output
        for name, port in self.ports.items():
            if 'output' not in port.state:
                log.fatal('unmapped_input_port', context='harness.contract.init', port=name)

    async def get_inputs(self) -> dict[str, Payload] | EndSentinel:
        for name, port in self.ports.items():
            if not port.has_ended() and name not in self.pending:
                self.pending[name] = asyncio.ensure_future(port.get())

        while self.pending:
            done, _ = await asyncio.wait(self.pending.values(), return_when=asyncio.FIRST_COMPLETED)
            for name, task in list(self.pending.items()):
                if task not in done:
                    continue
                val = task.result()
                del self.pending[name]
                if isinstance(val, EndSentinel):
                    continue
                return {self.ports[name].state['output']: val}

        return EndSentinel(self.id)
```

`mapping` is defaulted (`"default"`), so `contract_config` may be omitted — the n→1 case onto `"default"`. The `str` branch funnels every port onto that name; the `dict` branch assigns each named input its group's output and requires **every** port to end up assigned. Three construction-time `log.fatal`s guard the `dict` branch: `unknown_input_port` (a group names a port that doesn't exist), `ambiguous_output_mapping` (a port already assigned reappears under another output), and `unmapped_input_port` (a real port no group claims). This mirrors `KeyedJoinContract`'s per-port `state` seeding and its `unknown_persistent_ports` validation. `log` is the harness logger (`from rtl_comrade.logging import HarnessLogger`, as in `contracts/keyed_join.py`). The `str | dict` union deserializes unambiguously by shape — a YAML scalar is the n→1 name, a mapping is the m→n groups.

Manifest entry in `contracts/config.yaml`:

```yaml
- file: any.py
  plugins:
  - { name: any, class_name: AnyContract }
```

### `contracts/tests/test_any.py`

Enumerated as `port_inputs → expected_outputs` cases in the [`## Tests`](#tests) section below (driven by `run_contract_scenario`).

## Tests

In `contracts/tests/test_any.py`, driven by `run_contract_scenario(AnyContract, contract_config=…, port_inputs=…, expected_outputs=…)` (the contract-test harness — see `docs/contracts/testing.md`). A 3-port fixture (`a`/`b`/`c`) unless noted; `EndSentinel("src")` terminates a port; `PortTestInput(value, delay=N)` defers delivery to reach blocking-await branches. Cases with no `contract_config` exercise the n→1 default, so every delivery lands under `"default"`.

**Behavioural cases — default n→1** (no `contract_config`; `port_inputs → expected_outputs`):

- `{"a": [1, End], "b": [End], "c": [End]}` → `[{"default": 1}, EndSentinel]` (the lone item funnels onto `"default"`).
- `{"a": [1, End], "b": [2, End], "c": [3, End]}` → three `{"default": val}` deliveries (each value exactly once, none lost) followed by `EndSentinel` (interleaved across ports).
- `{"a": [End], "b": [2, End], "c": [3, End]}` → keeps delivering `{"default": 2}`/`{"default": 3}` then `EndSentinel` (an early `EndSentinel` on one port is consumed silently, others still drain).
- `{"a": [End], "b": [End], "c": [End]}` → `[EndSentinel]` (boundary: all ports already ended → immediate `EndSentinel(self.id)`, no delivery).
- **No-loss / one-at-a-time** — `{"a": [1, End], "b": [2, End]}` (both pre-loaded, ready in the same `asyncio.wait` wake-up) → `[{"default": 1}, {"default": 2}, EndSentinel]`: the first `get_inputs()` returns exactly one dict, the second returns the other without re-awaiting that port (the two deliveries are distinct calls even though they share the `"default"` key).
- **Drainage FIFO** — `{"a": [p1, p2, End], "b": [End], "c": [End]}` → `[{"default": p1}, {"default": p2}, EndSentinel]` (both payloads in FIFO order before the sentinel is consumed).
- **Blocking-await** — a port pre-loaded while a secondary port carries `PortTestInput(9, delay=1)` then `PortTestInput(End, delay=2)` → the deferred `{"default": 9}` is still delivered (exercises the `await asyncio.wait` branch unreachable with fully pre-loaded queues).

**Behavioural cases — configured output:**

- **Named n→1 output** — `contract_config={"mapping": "merged"}`, `{"a": [1, End], "b": [2, End]}` → `[{"merged": 1}, {"merged": 2}, EndSentinel]` (the `str` branch funnels onto a named output instead of `"default"`).
- **m→n grouping** — `contract_config={"mapping": {"x": ["a", "b"], "y": ["c"]}}`, `{"a": [1, End], "b": [2, End], "c": [3, End]}` → the deliveries `{"x": 1}`, `{"x": 2}`, `{"y": 3}` (each once, interleaved) then `EndSentinel`: `a`/`b` group onto `x`, `c` onto `y` (every port covered).

**Construction-time tests** (now that `Config` exists; `run_contract_scenario` asserts the structural load-time rules):

- **Empty / omitted config** loads and behaves as n→1 onto `"default"` (default `mapping="default"`).
- **Unknown input port** — `mapping={"x": ["nope"]}` on the `a`/`b`/`c` fixture → construction-time `log.fatal('unknown_input_port', …)`.
- **Ambiguous mapping** — `mapping={"x": ["a"], "y": ["a"]}` (input `a` claimed by two outputs) → construction-time `log.fatal('ambiguous_output_mapping', …)`.
- **Unmapped input port** — `mapping={"x": ["a", "b"]}` on the `a`/`b`/`c` fixture (input `c` left out) → construction-time `log.fatal('unmapped_input_port', …)`: in the `dict` branch every port must be assigned, with no silent fallback.

**Stress test** (≥13 ports): each port produces 100 payloads under `asyncio.create_task` with randomised `await asyncio.sleep(0)` interleavings, then `EndSentinel` → exactly `13 × 100` payloads delivered, each once, and `get_inputs()` returns `EndSentinel(self.id)` only after the last payload (not flaky across 100 invocations under `pytest -p no:randomly`). Run it both with the n→1 `str` (all `13 × 100` land on `"default"`) and with a `dict` `mapping` partitioning the ports, asserting the per-output-port multisets match the upstream partition.

**Property-based test** (`hypothesis` or equivalent): randomised `(port_count, items_per_port, interleaving_seed, mapping partition)` over ≥100 cases → the multiset of `(output_port, value)` deliveries equals the multiset produced upstream after applying the input→output mapping, and the contract terminates within bounded steps after all ports end.

## Acceptance criteria

- All enumerated `test_any.py` tests pass.
- Stress test is not flaky across 100 invocations under `pytest -p no:randomly`.
- Property-based test runs ≥100 generated cases with no falsifying input.
- `docs/contracts/index.md` promotion is **deferred** until the `any` contract is actually wired into a graph (it is unwired in `test`). When that happens, add a first-class entry listing invariants (mirrored from [05](../05-branching-and-results.md#the-any-contract-retained-currently-unwired)) and its reusability, per [`docs/creating-documentation.md`](../../docs/creating-documentation.md).
- The contract manifest entry `{ name: any, class_name: AnyContract }` in `contracts/config.yaml` validates and the harness resolves `any` → `AnyContract` (even though `graphs/test.yaml` leaves it unwired).

## Constraints

- **Never cancel an in-flight `pending` task.** A task created in call N but not returned must survive in `pending` to call N+1 — cancelling it loses that port's item (the no-loss invariant).
- Return **exactly one** `{output_port: payload}` per `get_inputs()` call (one delivery at a time); leave any other simultaneously-ready tasks in `pending`.
- Deliver each payload under the firing port's output port: `port.state['output']`. A `str` `mapping` funnels every input onto that name (`"default"` when unset) — n→1.
- Resolve each port's `state['output']` once at construction. With a `dict` `mapping`, every input port must be assigned exactly one output — an unknown input port, a port mapped to two outputs, or a real port left unmapped is a `log.fatal` (no silent fallback).
- Consume an `EndSentinel` silently and continue scanning; return `EndSentinel(self.id)` **only** once `pending` is empty (all ports ended). Propagate the sentinel — never synthesise it early or swallow the terminal one (`docs/invariants.md` — EndSentinel).
- Keep the `Config` **fully optional** (every field defaulted, so `contract_config` may be omitted) and the contract free of side-effects.

## Notes

The pending-task lifetime is the subtle part — tasks created in call N that are not returned must remain in `pending` and be honoured in call N+1. Do not cancel them; that loses items.

`AnyContract` **funnels** many input ports onto few outputs: a `str` `mapping` is n→1 (all inputs onto that name, `"default"` unless configured); a `dict` `mapping` is m→n (groups inputs onto several named outputs). The only construction-time validation is the `state['output']` resolution check (unknown input port; an input claimed by two outputs; a real port left unmapped).
