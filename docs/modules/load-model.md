# `load-model`

**Class:** `LoadModelMod` (`modules/rtl_buddy/setup.py`)

[Back to index](index.md)

Loads the test's RTL model from its `models.yaml`, looking up the entry named by `test.model` and building a `ModelConfig` (filelist + path). Emits split `test`/`model` edges on success; routes to `fail` on any load problem. Uses module-private serde types `ModelConfigFileItem`/`ModelConfigFile`.

## Inputs

| Port | Type | Meaning |
|---|---|---|
| `test` | `TestConfig` | the test whose model to load |

## Outputs

`test` — the (unchanged) test; `model` — `KeyedValue(test.key, ModelConfig)`. A failed load emits nothing.

## Failure routing

Each of missing file, directory, permission, bad UTF-8, malformed YAML, and missing model entry is caught and logged at `ERROR` (distinct event per cause) — the test is reported failed but the rest of the suite continues.

## Graph node

`load-model`, contract `default`.
