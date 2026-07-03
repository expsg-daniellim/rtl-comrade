# `expand-runs`

**Class:** `ExpandRunsMod` (`modules/rtl_buddy/sim.py`)

[Back to index](index.md)

Fans one compiled test out into one item per run id, re-keying each so downstream `keyed_join` correlates per run. With the default `run_ids` (`[None]`) it produces a single run with the original key.

## Inputs

| Port | Type | Default | Meaning |
|---|---|---|---|
| `test` | `TestConfig` | — | the compiled test |
| `simv` | `KeyedValue[str]` | — | its sim binary |
| `run_ids` | `list` | `[None]` | run ids to fan out; `None` = a single unsuffixed run |

`run_ids` has no wired source in the `test` graph, so it defaults to `[None]` (one run per test).

## Outputs

Per run id: `test` — a re-keyed copy (`dataclasses.replace(test, key=...)`); `run_id` — `KeyedValue(new_key, run_id)`; `simv` — the sim path under the new key.

## Graph node

`runs`, contract `keyed_join` (`key_field: key`, `persistent_inputs: [run_ids]`).
