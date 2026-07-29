# `interpret-sim`

**Class:** `InterpretSimMod` (`modules/rtl_buddy/sim.py`)

[Back to index](index.md)

Splits on the sim outcome. A killed-on-timeout `Proc` (`rc is None`) logs `sim_timeout` at `ERROR` and emits nothing; otherwise the test + proc continue to the post stage for log parsing.

## Inputs

| Port | Type | Meaning |
|---|---|---|
| `test` | `TestConfig` | the run |
| `proc` | `Proc` | finished sim |

## Outputs

`test` + `proc` — forwarded when the sim completed normally. A timed-out sim emits nothing.

## Graph node

`sim-int`, contract `keyed_join` (`key_field: key`).
