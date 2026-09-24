# `derive-randtest-runs`

**Class:** `DeriveRandtestRunsMod` (`modules/rtl_buddy/setup.py`)

[Back to index](index.md)

Collapses the `randtest` CLI pair `rnd_cnt` / `rnd_rpt` into the run-id list and seed mode the simulation pipeline needs. A non-negative `rnd_rpt` replays that single run; otherwise it produces `rnd_cnt` fresh-seed runs numbered from 1.

## Inputs

| Port | Type | Default | Meaning |
|---|---|---|---|
| `rnd_cnt` | `int` | `2` | number of random iterations (positional `RND_CNT`) |
| `rnd_rpt` | `int` | `-1` | `-r/--rnd-rpt`: run id to replay; any negative value means absent (CLI edges cannot carry `None`), so `0` is a valid replay index |

## Outputs

Each fires once per invocation.

- `run_ids` — `[rnd_rpt]` when replaying, else `[1, 2, ..., rnd_cnt]`.
- `seed_mode` — `SeedMode.REPLAY` when replaying, else `SeedMode.NEW`.

## Failure routing

`rnd_cnt < 1` without a replay index → `log.fatal("invalid_rnd_cnt")`.

## Graph node

`derive-runs`, contract `unit`. `run_ids` feeds [expand-runs](expand-runs.md); `seed_mode` feeds [resolve-seed](resolve-seed.md).
