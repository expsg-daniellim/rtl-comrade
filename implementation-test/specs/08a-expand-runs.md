# Spec 08a: expand-runs (`ExpandRunsMod`)

**Depends on:** spec 03 (run-process), spec 07 (compile cycle).
**References:** [03 — Run expansion section](../03-module-catalog.md). Parent index:
[08 — Sim-cycle modules](08-sim-cycle-modules.md).

## Goal

Fan out a compiled `ctx` into one `ctx` per run-id at the head of the simulate leg.

## Deliverables

In `modules/rtl_test/sim.py`:

- `ExpandRunsMod` — `(ctx, run_ids:list=[None])` → generator yielding one fresh `ctx`
  per `run_id`, with `ctx["run_id"]` set and key suffixed `#run_id` (when `run_id is not
  None`). For `run_ids=[None]` emits one `ctx` unchanged (key unmodified, `run_id=None`).
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/runner/test_runner.py:82-117` — `run_multiple`'s run-id loop (vs `run` at `:51-80`); dispatch at `rtl_buddy.py:297-299`.

Manifest entries per [06](../06-graph-yaml.md).

## Tests

In `modules/tests/test_sim_cycle.py`:

- `expand-runs` defaults `[None]` → single passthrough (key unmodified, `run_id=None`).
- Explicit `[1,2,3]` → 3 ctxs with correct keys (suffixed `#run_id`).

## Acceptance criteria

- Tests pass.
- Default `[None]` and an explicit multi-id list both fan out with correctly-stamped keys.
