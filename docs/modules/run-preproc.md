# `run-preproc`

**Class:** `RunPreprocMod` (`modules/rtl_buddy/build.py`)

[Back to index](index.md)

If the test declares a preproc script, executes it (with `test_cfg`, `root_cfg`, and `logger` in scope) as a side effect, then forwards the test/model pair; otherwise passes them through untouched.

## Inputs

| Port | Type | Meaning |
|---|---|---|
| `test` | `TestConfig` | the test |
| `model` | `KeyedValue[ModelConfig]` | its resolved model |
| `root_cfg` | `RootConfig` | passed into the script namespace |

## Outputs

`test` + `model` — forwarded after the script runs; `fail` — a `TestResult.prep` if the script is missing/unreadable or raises.

## Failure routing

File-not-found / permission / read errors and script exceptions are caught, logged at `ERROR`, and routed to `fail`. The resolved `ModelConfig` is swapped into `test.model` for the script's benefit and restored before forwarding, so the `test` edge always carries the model *name* string.

## Graph node

`preproc`, contract `keyed_join` (`key_field: key`, `persistent_inputs: [root_cfg]`). The `fail` port fans into [summarise-results](summarise-results.md).
