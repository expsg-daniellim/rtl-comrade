# Spec 08a: expand-runs (`ExpandRunsMod`)

**Depends on:** spec 03 (run-process), spec 07 (compile cycle).
**References:** [03 — Run expansion section](../03-module-catalog.md). Parent index: [idx-08 — Sim-cycle modules](../idx-08-sim-cycle.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)` signature, the allowed output forms (plain return / named-port tuple / generator), the `finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py` are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit `a69d962`). This module **creates** `modules/rtl_buddy/sim.py` — it is the first spec to write the file, so establish the shared imports and module-level helpers here. The file then receives further additions from the rest of the sim-cycle modules (`08b`–`08f`, index [idx-08](../idx-08-sim-cycle.md)) and the post modules (`09a`–`09c`, index [idx-09](../idx-09-post.md)); coordinate shared imports and helpers with those specs.

## Goal

Fan out the per-test edges (`test` + `simv`) into one set per run-id at the head of the simulate leg — `run_id` is born here.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry — the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract:          keyed_join
contract_config:   key_field: key
persistent_inputs: [run_ids]
inputs:            test, simv, run_ids:list = [None]   (test+simv joined at the test-level key)
outputs:           test   → {key, value}   (×N, key re-suffixed #run_id when not None)
                   run_id → {key, value}   (×N — born here)
                   simv   → {key, value}   (×N — rebroadcast across the fan-out)
```

```python
class ExpandRunsMod:
    def run(self, test, simv, run_ids:list = [None]):
        for run_id in run_ids:
            nk = test["key"] if run_id is None else f"{test['key']}#{run_id}"   # per-test key → per-run key
            yield ("test",   { "key": nk, "value": test["value"] })
            yield ("run_id", { "key": nk, "value": run_id })                    # run_id born here
            yield ("simv",   { "key": nk, "value": simv["value"] })             # rebroadcast per run
```

## Algorithm

1. `keyed_join` joins `test` + `simv` at the **test-level** key (e.g. `mytest`). For each `run_id` in `run_ids` (persistent, default `[None]`), compute the **run-level** key `nk`: `test["key"]` unchanged when `run_id is None`, else `f"{test['key']}#{run_id}"`.
2. Re-emit all three edges at `nk`: `("test", {"key": nk, "value": test["value"]})`, `("run_id", {"key": nk, "value": run_id})` (run_id is **born here**), `("simv", {"key": nk, "value": simv["value"]})` (rebroadcast so each run carries the per-test compile result). `run_ids=[None]` therefore emits a single passthrough per edge with the key unchanged. No failure path.

## Deliverables

In `modules/rtl_buddy/sim.py`:

- `ExpandRunsMod` — `(test, simv, run_ids:list=[None])`, `keyed_join` over `test` + `simv` (joined at the test-level key) with `run_ids` as a `persistent_input` → generator that, per `run_id`, re-emits `test`/`run_id`/`simv` at the run-level key `f"{test['key']}#{run_id}"` (key unchanged when `run_id is None`). `run_id` is born here; `simv` is rebroadcast across the fan-out. For `run_ids=[None]` emits one passthrough per edge (key unmodified, `run_id` value `None`).
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/runner/test_runner.py:82-117` — `run_multiple`'s run-id loop (vs `run` at `:51-80`); dispatch at `rtl_buddy.py:297-299`.

- **`run_suffix(run_id)` — shared module-level helper.** This spec creates `sim.py` and owns the canonical definition (consumed by `resolve-seed` [08b], `build-sim-cmd` [08c] as `run_suffix(run_id["value"])`; `write-randseed` [08d] receives the pre-composed paths and does not call it). It mirrors the run-id suffixing in rtl_buddy's `_get_log_path`:

  ```python
  # modules/rtl_buddy/sim.py  (module-level helper)
  def run_suffix(run_id) -> str:
      return "" if run_id is None else f"_{run_id:04d}"   # run-id zero-padded to four digits
  ```

  Returns `""` when `run_id is None` (single run), else `f"_{run_id:04d}"` — e.g. run-id 3 → `_0003`. The `is None` test (not falsiness) keeps run-id `0` suffixed. Callers pass the `run_id` edge's value (`run_suffix(run_id["value"])`) and join the result onto the test-name stem they compose under `logs_dir`.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:82-86` — `VlogSim._get_log_path`'s `if run_id is not None: log_path += f"_{run_id:04d}"`.

**Manifest** — this module opens the `rtl_buddy/sim.py` block in `modules/config.yaml` (later appended to by `08b`–`08f`, `09a`–`09c`):

```yaml
- file: rtl_buddy/sim.py
  plugins:
  - { name: expand-runs, class_name: ExpandRunsMod }
```

## Tests

In `modules/tests/test_sim_cycle.py`. Fixtures: `test` and `simv` edge dicts (`{key, value}`) at a shared test-level key. Pure generator — no `logging_handler` needed. Drive `run(test, simv, run_ids=…)` directly — the `keyed_join` is the contract's concern.

- `(test, simv, run_ids=[None])` (default) → yields one `("test", …)`, `("run_id", {"value": None})`, `("simv", …)`, each with the key unmodified (boundary: default passthrough).
- `(test, simv, run_ids=[1, 2, 3])` → yields the three edges ×3, with keys `key#1`/`key#2`/`key#3` and `run_id` values `1`/`2`/`3`; each run's `test`/`simv` carry the same `value` as the inputs (rebroadcast).
- `(test, simv, run_ids=[0])` → keys `key#0`, `run_id` value `0` (boundary: `0` is not `None`, so it is suffixed — confirms the `is None` test, not falsiness).
- `(test, simv, run_ids=[])` → yields nothing (boundary: empty list).
- Inbound `test`/`simv` are not mutated in place — each yielded dict is a fresh `{key, value}` (assert the originals' `key`/`value` are untouched after iterating).

## Acceptance criteria

- Tests pass.
- All three output ports (`test`, `run_id`, `simv`) exercised: default `[None]` emits one passthrough triple at the unchanged key; an explicit multi-id list fans out the triple once per run-id with keys suffixed `#run_id`.
- No failure path.
- The `modules/config.yaml` manifest entry `{ name: expand-runs, class_name: ExpandRunsMod }` validates and the harness resolves `expand-runs` → `ExpandRunsMod`.

## Constraints

- `run_ids` default `[None]` → a single passthrough per edge (key unchanged, `run_id` value `None`); a non-`None` `run_id` suffixes the key `#run_id`.
- Yield fresh `{key, value}` edges per `run_id` via the generator; do not mutate the inbound `test`/`simv` in place.
- No failure path. `keyed_join` over `test` + `simv` (key_field `key`), `run_ids` persistent; emit on string-literal `test`/`run_id`/`simv` ports.
