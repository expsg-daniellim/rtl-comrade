# `derive-seed-mode`

**Class:** `DeriveSeedModeMod` (`modules/rtl_buddy/setup.py`)

[Back to index](index.md)

Maps the two mutually-exclusive CLI flags to a `SeedMode` enum.

## Inputs

| Port | Type | Default | Meaning |
|---|---|---|---|
| `rnd_new` | `bool` | `False` | `--rnd-new`: fresh random seed |
| `rnd_last` | `bool` | `False` | `--rnd-last`: replay the last seed |

## Outputs

`default` — `SeedMode.NEW`, `SeedMode.REPLAY`, or `SeedMode.DEFAULT` (`rnd_new` wins if both are set).

## Graph node

`seed-mode`, contract `unit`. Consumed by [resolve-seed](resolve-seed.md).
