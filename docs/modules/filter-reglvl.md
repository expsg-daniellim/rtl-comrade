# `filter-reglvl`

**Class:** `FilterRegLvlMod` (`modules/rtl_buddy/setup.py`)

[Back to index](index.md)

Drops tests outside the requested register-level window, routing them to a `skip` result instead of down the main line.

## Inputs

| Port | Type | Default | Meaning |
|---|---|---|---|
| `test` | `TestConfig` | — | candidate test |
| `builder_cfg` | `RtlBuilderConfig` | — | selects which reglvl applies |
| `reg_level` | `int \| None` | `None` | upper bound (end level); `None` disables |
| `start_level` | `int \| None` | `None` | lower bound (start level); `None` disables |

`reg_level`/`start_level` have no wired source in the `test` graph, so they default to `None` (no filtering); `builder_cfg` is a persistent input from [resolve-builder](resolve-builder.md).

## Outputs

`test` — the test, if within range; `skip` — a `TestResult.skip` describing why it was excluded.

## Graph node

`filter`, contract `default` (`persistent_inputs: [builder_cfg, reg_level, start_level]`). The `skip` port fans into [summarise-results](summarise-results.md).
