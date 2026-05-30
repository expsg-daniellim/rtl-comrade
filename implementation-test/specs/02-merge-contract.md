# Spec 02: `merge` contract

**Depends on:** spec 00.
**References:** [05 — the `merge` contract](../05-branching-and-results.md).

## Goal

Author the only new framework-level code in the design: a non-correlating fan-in contract
that forwards each item from whichever input port has one, and ends when all input ports
have ended. Underwrites `aggregate-results` (spec 10) and is broadly reusable.

## Deliverables

- `contracts/merge.py` — `MergeContract` per the sketch in [05](../05-branching-and-results.md).
- Manifest entry in `contracts/config.yaml`:
  ```yaml
  - file: merge.py
    plugins:
    - { name: merge, class_name: MergeContract }
  ```
- `contracts/tests/test_merge.py` covering:
  - single item on one port → delivered under that port's name.
  - items interleaved across multiple ports → all delivered, none lost.
  - port end-sentinel on one port while others still active → continue.
  - all ports ended → returns `EndSentinel(self.id)`.
  - **no-loss invariant**: pending `get()` tasks persist across `get_inputs` calls so an
    item arriving on a not-yet-selected port between calls is preserved.

## Acceptance criteria

- All tests pass.
- A throw-away integration test with a 3-input sink and three upstreams producing 10
  items each confirms 30 items are received in some interleaved order with no duplicates
  and no losses.

## Notes

The pending-task lifetime is the subtle part — `asyncio.wait(..., FIRST_COMPLETED)` plus
caching unfinished tasks on `self` is the recommended approach (see [05](../05-branching-and-results.md)
sketch). Do not cancel pending tasks between calls; that would lose items.
