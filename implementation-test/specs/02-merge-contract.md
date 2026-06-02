# Spec 02: `merge` contract

**Depends on:** harness change that lets contracts declare input ports independently of
the module's `run()` signature — see Prerequisite below.
**References:** [05 — the `merge` contract](../05-branching-and-results.md),
[07 item 19](../07-ambiguities-and-assumptions.md).

## Prerequisite

This contract has two port surfaces:

- **Module-side**: the module's `run()` parameter list defines the output ports the
  contract delivers under.
- **Contract-side**: `MergeContract.Config.fan_in` declares the input ports the contract
  consumes from. These do **not** appear on the module's `run()` signature.

The current harness (`src/rtl_comrade/node.py:122`) builds the node's port set strictly
from the module's `run()` parameters and gives the contract `ContractPort` adapters over
exactly that set. Realising this contract therefore depends on a harness change that
lets contract Config introduce input ports the module does not declare. The harness
change is owned outside this plan; the spec below is written against the post-change
harness. Do not implement this contract until the harness change has landed.

## Goal

Author the only new framework-level code in the design: a non-correlating M-N fan-in
contract that forwards each item from whichever **contract-side** input port has one to
its mapped **module-side** output port (the port name the module's `run()` receives the
payload under), and ends when all input ports have ended. Underwrites `aggregate-results`
(spec 10) and is broadly reusable for any "collect alternatives, deliver under one (or a
few) names" pattern.

## Deliverables

- `contracts/merge.py` — `MergeContract` per the sketch in [05](../05-branching-and-results.md),
  including the nested `Config` dataclass:
  ```python
  @dataclass(frozen=True)
  class Config:
      fan_in: dict[str, list[str]] | str
      release_lock: str | None = None
  ```
  - **Dict form** (`fan_in: {output_port: [input_ports...]}`): explicit M-N. Each entry's
    key is a module-side output port (must be a `run()` parameter on the consuming
    module); each value lists the contract-declared input ports that deliver under it.
  - **String form** (`fan_in: "out"`): N-1 shorthand — every contract-declared input port
    fans into the single module-side output port `out`. The precise interaction with the
    harness's mechanism for declaring contract input ports is owned by that harness
    change (the contract needs some way to enumerate its declared inputs when the str
    form is used).
- Manifest entry in `contracts/config.yaml`:
  ```yaml
  - file: merge.py
    plugins:
    - { name: merge, class_name: MergeContract }
  ```
- `contracts/tests/test_merge.py` covering, at minimum, the invariants in
  [05 — Invariants and termination](../05-branching-and-results.md#invariants-and-termination):

  **Behavioural tests** (a 3-input → 1-output `fan_in: "out"` fixture unless noted):

  - single item on one input → delivered under the configured output name.
  - items interleaved across multiple inputs → all delivered, none lost; every delivery
    arrives under the output port name (not the source input name).
  - input end-sentinel on one port while others still active → continue.
  - all inputs ended → returns `EndSentinel(self.id)`.
  - **no-loss invariant**: pending `get()` tasks persist across `get_inputs` calls so an
    item arriving on a not-yet-selected port between calls is preserved.
  - **multi-done-per-wake**: arrange two inputs to be ready in the same `asyncio.wait`
    wake-up; first call returns one, second call must return the other without recreating
    the task or re-awaiting the port.
  - **drainage order**: an input queued with `[payload, payload, EndSentinel]` delivers
    both payloads (in FIFO order) before its `EndSentinel` is consumed.
  - **non-correlating**: two inputs sharing one output each emitting a payload with the
    same upstream key → both are delivered under the output name (merge does not dedupe;
    the violation is upstream's responsibility).
  - **explicit M-N**: with `fan_in: {a: [in1, in2], b: [in3, in4]}`, items on `in1`/`in2`
    arrive under `a`; items on `in3`/`in4` arrive under `b`. Every output is exercised.
  - **output is never consulted as an input**: with `fan_in: "out"`, an item arriving on
    a port named `out` (if anyone could deliver one — which they can't, because the output
    port has no edges) must not be polled; verify by inspecting that no `get()` is ever
    issued against the output port's `ContractPort`.

  **Construction-time validation tests** (each must trigger `log.fatal`):

  - `fan_in: "out"` where `out` is not a module-side parameter → `merge_output_not_module_port`.
  - `fan_in: {a: [in_missing]}` where `in_missing` is not a contract-declared input →
    `merge_input_not_declared`.
  - `fan_in: {a: [b], b: [c]}` where `b` is both an output and an input →
    `merge_input_is_also_output`.
  - `fan_in: {a: [in1], b: [in1]}` (input listed in two output lists) →
    `merge_input_duplicate`.
  - `fan_in: {a: [in1]}` with a third declared, non-output input port `in2` left out of
    every value list → `merge_input_unmapped`.

- **Stress test** (one test, ≥13 mock input ports + 1 output port to match `agg`'s real
  surface): each input produces 100 payloads under `asyncio.create_task` with randomised
  `await asyncio.sleep(0)` interleavings, then emits `EndSentinel`. Assertions:
  - exactly `13 × 100` payloads delivered, each exactly once;
  - every delivered payload's dict key equals the configured output port name;
  - `get_inputs()` returns `EndSentinel(self.id)` after the last payload and not before.
- **Property-based test** (`hypothesis` or equivalent): randomised `(input_count,
  output_count, mapping_seed, items_per_input, interleaving_seed)` tuples constrained so
  every input maps to exactly one output. For each generated case, assert:
  - the multiset of delivered payloads equals the multiset produced upstream;
  - each delivery is keyed by an output port name (never an input port name);
  - the contract terminates within bounded steps after all inputs end;
  - no `RuntimeError` from premature `release_lock` paths (cases without a configured
    `release_lock` only — the lock-coupled cases live in TODO #30's interim-shim tests).

## Acceptance criteria

- All enumerated tests pass.
- The stress test runs deterministically under `pytest -p no:randomly` and is not flaky
  across 100 invocations.
- The property-based test runs at least 100 generated cases per session (`max_examples=100`
  or higher) with no falsifying input.
- Promotion to first-class: add an entry to `docs/contracts/index.md` linking the contract
  source, listing its invariants (mirrored from
  [05](../05-branching-and-results.md#invariants-and-termination)), documenting both the
  string and dict forms of `Config.fan_in`, and noting reusability beyond
  `aggregate-results`. Per
  [`docs/creating-documentation.md`](../../docs/creating-documentation.md). The optional
  `release_lock` field is documented in this entry but flagged as an interim hook tracked
  by TODO #30 in [`implementation-test-todos.md`](../../implementation-test-todos.md), not
  as part of the contract's first-class surface.

## Notes

The pending-task lifetime is the subtle part — `asyncio.wait(..., FIRST_COMPLETED)` plus
caching unfinished tasks on `self` is the recommended approach (see [05](../05-branching-and-results.md)
sketch). Do not cancel pending tasks between calls; that would lose items.

The M-N design preserves the contract's "non-correlating" property: the input port a
payload came from is never surfaced to the module — only the mapped output port name.
That decouples module signatures from upstream topology: adding a new input port extends
`Config.fan_in`'s input list, not the module's `run()` signature.
