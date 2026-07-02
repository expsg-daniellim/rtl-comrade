# `expand-sweep`

**Class:** `ExpandSweepMod` (`modules/rtl_buddy/setup.py`)

[Back to index](index.md)

If the test declares a sweep script, executes it to expand one test into N keyed variants (each with a `#i`-suffixed key); otherwise passes the test through unchanged. The script sees `test_cfg`, `root_cfg`, and a `logger`, and appends variants to `out_test_cfgs`.

## Inputs

| Port | Type | Meaning |
|---|---|---|
| `test` | `TestConfig` | the test to (maybe) expand |
| `model` | `KeyedValue[ModelConfig]` | its resolved model |
| `root_cfg` | `RootConfig` | passed into the sweep script namespace |

## Outputs

`test` + `model` per variant (or the original pair if no sweep); `fail` — a `TestResult.prep` if the script is missing/unreadable, raises, or produces malformed `out_test_cfgs`.

## Failure routing

Missing/permission/read errors, script exceptions, and malformed output are each caught, logged at `ERROR`, and routed to `fail`. The script runs with the resolved `ModelConfig` temporarily swapped into `test.model`, restored on every exit path.

## Graph node

`sweep`, contract `keyed_join` (`key_field: key`, `persistent_inputs: [root_cfg]`). The `fail` port fans into [summarise-results](summarise-results.md).
