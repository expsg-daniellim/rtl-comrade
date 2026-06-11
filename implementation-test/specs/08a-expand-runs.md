# Spec 08a: expand-runs (`ExpandRunsMod`)

**Depends on:** spec 03 (run-process), spec 07 (compile cycle).
**References:** [03 — Run expansion section](../03-module-catalog.md). Parent index:
[08 — Sim-cycle modules](08-sim-cycle-modules.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)`
signature, the allowed output forms (plain return / named-port tuple / generator), the
`finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py`
are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry
below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit
`a69d962`). This module appends to `modules/rtl_test/sim.py`, shared with the sim-cycle modules
(`08a`–`08f`, index [08](08-sim-cycle-modules.md)) and the post modules (`09a`–`09c`, index
[09](09-post-modules.md)); coordinate shared imports and helpers with those specs.

## Goal

Fan out a compiled `ctx` into one `ctx` per run-id at the head of the simulate leg.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry —
the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract:          default
persistent_inputs: [run_ids]
inputs:            ctx, run_ids:list = [None]
outputs:           default → ctx   (one per run-id; key suffixed #run_id when not None)
```

```python
class ExpandRunsMod:
    def run(self, ctx, run_ids:list = [None]):
        for run_id in run_ids:
            key = ctx["key"] if run_id is None else f"{ctx['key']}#{run_id}"
            yield ("default", { **ctx, "key": key, "run_id": run_id })
```

## Deliverables

In `modules/rtl_test/sim.py`:

- `ExpandRunsMod` — `(ctx, run_ids:list=[None])` → generator yielding one fresh `ctx`
  per `run_id`, with `ctx["run_id"]` set and key suffixed `#run_id` (when `run_id is not
  None`). For `run_ids=[None]` emits one `ctx` unchanged (key unmodified, `run_id=None`).
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/runner/test_runner.py:82-117` — `run_multiple`'s run-id loop (vs `run` at `:51-80`); dispatch at `rtl_buddy.py:297-299`.

**Manifest** — this module opens the `rtl_test/sim.py` block in `modules/config.yaml`
(later appended to by `08b`–`08f`, `09a`–`09c`):

```yaml
- file: rtl_test/sim.py
  plugins:
  - { name: expand-runs, class_name: ExpandRunsMod }
```

## Tests

In `modules/tests/test_sim_cycle.py`:

- `expand-runs` defaults `[None]` → single passthrough (key unmodified, `run_id=None`).
- Explicit `[1,2,3]` → 3 ctxs with correct keys (suffixed `#run_id`).

## Acceptance criteria

- Tests pass.
- Default `[None]` and an explicit multi-id list both fan out with correctly-stamped keys.
