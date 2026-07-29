# `load-model`

**Class:** `LoadModelMod` (`modules/rtl_buddy/setup.py`)

[Back to index](index.md)

Loads a model from a `models.yaml` file given a model name and resolved file path. Looks up the named entry and builds a `ModelConfig` (filelist + path). Accepts an optional `TestConfig` for log context. Uses module-private serde types `ModelConfigFileItem`/`ModelConfigFile`.

## Inputs

| Port | Type | Meaning |
|---|---|---|
| `model_name` | `str` | the model entry to look up |
| `model_path` | `Path` | resolved path to the `models.yaml` file |
| `test` | `TestConfig \| None` | optional; supplies `key` and `test_name` for log context (default `None`) |

## Outputs

`model` — bare `ModelConfig`. A failed load emits nothing. The `keyed_join` contract with `unwrap: true` strips the `KeyedValue` envelope on input and rewraps the output.

## Failure routing

Each of missing file, directory, permission, bad UTF-8, malformed YAML, and missing model entry is caught and logged at `ERROR` (distinct event per cause) — the test is reported failed but the rest of the suite continues. When `test` is `None`, `key` falls back to `model_name` and `test_name` is omitted.

## Graph node

`load-model`, contract `keyed_join` (`key_field: key`, `unwrap: true`).
