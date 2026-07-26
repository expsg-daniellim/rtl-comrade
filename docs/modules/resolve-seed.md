# `resolve-seed`

**Class:** `ResolveSeedMod` (`modules/rtl_buddy/sim.py`)

[Back to index](index.md)

Determines the RNG seed for a run according to `SeedMode`: `NEW` → fresh random, `DEFAULT` → the builder's configured seed, `REPLAY` → read back the seed written by the previous run.

## Inputs

| Port | Type | Meaning |
|---|---|---|
| `test` | `TestConfig` | the run |
| `run_id` | `int \| None` | run id (for the replay filename suffix) |
| `simv` | `str` | forwarded sim path |
| `seed_mode` | `SeedMode` | from [derive-seed-mode](derive-seed-mode.md) |
| `builder_cfg` | `RtlBuilderConfig` | supplies the default seed |
| `logs_dir` | `Path` | where `.randseed` files live |

## Outputs

`test` + `run_id` + `simv` forwarded, plus `seed` — the resolved `int`; `fail` — a `TestResult.prep` if a replay seed file is missing/malformed/unreadable.

## Failure routing

In `REPLAY` mode a missing, non-integer, or unreadable `.randseed` file is caught, logged at `ERROR`, and routed to `fail`.

## Graph node

`seed`, contract `keyed_join` (`key_field: key`, `persistent_inputs: [seed_mode, builder_cfg, logs_dir]`, `unwrap: true`, `ignore: [test, fail]`). The `run_id`, `simv` and `seed` edges ride the wire as `KeyedValue`s; the contract unwraps them on the way in and keys everything the module emits back to the run on the way out, so the module never handles the key. The `fail` port fans into [summarise-results](summarise-results.md).
