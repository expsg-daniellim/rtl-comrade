# Spec 08a: expand-runs (`ExpandRunsMod`)

**Depends on:** spec 03 (run-process), spec 07 (compile cycle).
**References:** [03 — Run expansion section](../03-module-catalog.md). Parent index:
[idx-08 — Sim-cycle modules](../idx-08-sim-cycle.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)`
signature, the allowed output forms (plain return / named-port tuple / generator), the
`finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py`
are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry
below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit
`a69d962`). This module **creates** `modules/rtl_buddy/sim.py` — it is the first spec to write the file,
so establish the shared imports and module-level helpers here. The file then receives further
additions from the rest of the sim-cycle modules (`08b`–`08f`, index
[idx-08](../idx-08-sim-cycle.md)) and the post modules (`09a`–`09c`, index
[idx-09](../idx-09-post.md)); coordinate shared imports and helpers with those specs.

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

## Algorithm

1. For each `run_id` in `run_ids` (default `[None]`), compute the key: `ctx["key"]` unchanged
   when `run_id is None`, else `f"{ctx['key']}#{run_id}"`.
2. Yield `("default", {**ctx, "key": key, "run_id": run_id})` — one fresh `ctx` per run-id.
   `run_ids=[None]` therefore emits a single passthrough. No failure path.

## Deliverables

In `modules/rtl_buddy/sim.py`:

- `ExpandRunsMod` — `(ctx, run_ids:list=[None])` → generator yielding one fresh `ctx`
  per `run_id`, with `ctx["run_id"]` set and key suffixed `#run_id` (when `run_id is not
  None`). For `run_ids=[None]` emits one `ctx` unchanged (key unmodified, `run_id=None`).
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/runner/test_runner.py:82-117` — `run_multiple`'s run-id loop (vs `run` at `:51-80`); dispatch at `rtl_buddy.py:297-299`.

**Manifest** — this module opens the `rtl_buddy/sim.py` block in `modules/config.yaml`
(later appended to by `08b`–`08f`, `09a`–`09c`):

```yaml
- file: rtl_buddy/sim.py
  plugins:
  - { name: expand-runs, class_name: ExpandRunsMod }
```

## Tests

In `modules/tests/test_sim_cycle.py`. Fixtures: a `ctx` fixture. Pure generator — no
`logging_handler` needed.

- `(ctx, run_ids=[None])` (default) → yields a single `("default", ctx)` with key unmodified
  and `run_id=None` (boundary: default passthrough).
- `(ctx, run_ids=[1, 2, 3])` → yields 3 ctxs with keys `key#1`/`key#2`/`key#3` and
  `run_id` set to `1`/`2`/`3` respectively.
- `(ctx, run_ids=[0])` → yields one ctx with key `key#0`, `run_id=0` (boundary: `0` is not
  `None`, so it is suffixed — confirms the `is None` test, not falsiness).
- `(ctx, run_ids=[])` → yields nothing (boundary: empty list).
- Inbound `ctx` is not mutated in place — each yielded dict is a fresh copy (assert the
  original `ctx["key"]`/`run_id` are untouched after iterating).

## Acceptance criteria

- Tests pass.
- Output port `default` exercised: default `[None]` emits a single passthrough `ctx`; an
  explicit multi-id list fans out one `ctx` per run-id with keys suffixed `#run_id`.
- No failure path.
- The `modules/config.yaml` manifest entry `{ name: expand-runs, class_name: ExpandRunsMod }`
  validates and the harness resolves `expand-runs` → `ExpandRunsMod`.

## Constraints

- `run_ids` default `[None]` → a single passthrough (`ctx` unchanged, `run_id=None`); a non-`None`
  `run_id` suffixes the key `#run_id`.
- Yield one fresh `ctx` per `run_id` via the generator; do not mutate the inbound `ctx` in place.
- No failure path. Emit on the string-literal `default` port.
