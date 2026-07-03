# `interpret-sim`

**Class:** `InterpretSimMod` (`modules/rtl_buddy/sim.py`)

[Back to index](index.md)

Splits on the sim outcome. A killed-on-timeout `Proc` (`rc is None`) becomes a `sim_timeout` result; otherwise the test + proc continue to the post stage for log parsing.

## Inputs

| Port | Type | Meaning |
|---|---|---|
| `test` | `TestConfig` | the run |
| `proc` | `Proc` | finished sim |

## Outputs

`timeout` — a `TestResult.sim_timeout` (logged `ERROR`) when `rc is None`; `test` + `proc` — forwarded otherwise.

## Graph node

`sim-int`, contract `keyed_join` (`key_field: key`). The `timeout` port fans into [summarise-results](summarise-results.md) as `sim_timeout`.
