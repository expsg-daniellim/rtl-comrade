# `resolve-model-ref`

**Class:** `ResolveModelRefMod` (`modules/rtl_buddy/setup.py`)

[Back to index](index.md)

Projects a model name and resolved model-file path from a `TestConfig`, emitting them as keyed values for a downstream loader. Separates the "what to load" concern from the loading itself.

## Inputs

| Port | Type | Meaning |
|---|---|---|
| `test` | `TestConfig` | the test whose model reference to resolve |

## Outputs

`model_name` — `KeyedValue(test.key, test.model)`; `model_path` — `KeyedValue(test.key, test.suite_dir / test.model_path)`. The input `test` is not re-emitted; the graph wires it directly from upstream.

## Graph node

`model-ref`, contract `default`.
