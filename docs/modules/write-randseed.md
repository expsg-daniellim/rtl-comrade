# `write-randseed`

**Class:** `WriteRandseedMod` (`modules/rtl_buddy/sim.py`)

[Back to index](index.md)

Persists the run's seed to its `.randseed` file (for later replay), appending `HierInstanceSeed.txt` from the working directory when the sim used `hier_inst_seed`. Emits a `RandSeedDone` ordering token so [link-latest](link-latest.md) cannot run before the seed file exists.

## Inputs

| Port | Type | Meaning |
|---|---|---|
| `randseed` | `RandSeed` | seed + output path + argv |
| `proc` | `Proc` | the finished sim — joined only as a completion gate (`rc` unread) |
| `work_dir` | `Path` | where the sim dropped `HierInstanceSeed.txt` |

## Outputs

`randseed_done` — a `RandSeedDone(key)` emitted unconditionally so the ordering edge never dangles.

## Failure routing

A write failure (including a missing `HierInstanceSeed.txt`) is `log.error` (`randseed_write_failed`); the `randseed_done` token is still emitted so [link-latest](link-latest.md) proceeds.

## Graph node

`randseed`, contract `keyed_join` (`key_field: key`, `persistent_inputs: [work_dir]`).
