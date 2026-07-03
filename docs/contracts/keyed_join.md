# `keyed_join` / `required_inputs_by_key`

**Class:** `KeyedJoinContract` (`contracts/keyed_join.py`)

[Back to index](index.md)

Groups incoming items by a correlation key and invokes the module when all required ports have delivered a value for the same key. The key is read from the field named by `key_field` (default `"key"`): a payload's `key_field` attribute when present, otherwise its `key_field` dict entry, so the contract works on any object exposing that attribute as well as on plain dicts. Items may arrive interleaved across ports and are buffered until a complete group is available. `required_inputs_by_key` is an alias for the same class.

## Config

```yaml
contract: keyed_join
contract_config:
  key_field: test_id
```

| Field | Type | Purpose |
|---|---|---|
| `key_field` | `str` | Name of the field — an object attribute or a dict entry — used as the correlation key. Optional; defaults to `"key"` |
| `persistent_inputs` | `list[str]` | Input-port names whose latest value is cached and replayed on every keyed assembly. Optional; omit if no persistent ports are needed |

Each keyed payload must either expose `key_field` as an attribute or be a `dict` containing `key_field`. The attribute takes precedence when both are present. The key type must support `<` comparison (e.g. `int`, `str`) because ties between simultaneously complete keys are broken by minimum value.

## Persistent inputs

A port named in `persistent_inputs` is a singleton side-channel: its latest value is cached and replayed on every keyed assembly, mirroring `persistent_inputs` on the [`default`](default.md) contract. This lets a `keyed_join` node receive runtime-computed config singletons alongside its keyed streams.

- A persistent input does **not** need to carry a key (a `key_field` attribute or dict entry). Key completeness is decided by the keyed (non-persistent) ports only.
- If a persistent payload **does** carry a key, its value is additionally cached per key. A keyed assembly for key `K` then prefers the value cached for `K`, falling back to the most-recent value when none was cached for `K`. Keyless persistents always use the most-recent value.
- The first keyed assembly **blocks** until every persistent port that cannot fall back to a module default has delivered at least one value (first-run-required, matching `default`). Whether a port can default is read from `ContractPort.has_default`, gated by `required`, exactly as `DefaultContract` does.
- A persistent port whose module parameter **has a default** (and is not marked `required`) never blocks the first assembly: until it delivers a real value its key is omitted so the module's Python default applies, mirroring `default`. Once it delivers, its value is cached and replayed. Such a port ending without ever delivering is **not** an error — its default simply applies.
- A persistent port that **cannot** default ending before ever delivering is logged as an error and omitted from the assembly.
- A persistent port ending neither terminates the join nor participates in key completeness — termination is driven by the keyed ports.

```yaml
contract: keyed_join
contract_config:
  key_field: test_id
  persistent_inputs: [builder_cfg, logs_dir]
```

## Termination

Ends when all keyed ports have ended. The module fires only for keys every keyed port delivered; an incomplete key is dropped, never folded into a partial invocation. Branch awareness affects only error reporting: of the keys still incomplete at termination, one is logged as an error only when a control-dependence partition (keyed ports sharing the same `branch_labels`) holds it on some co-fated ports but not all; a key a whole partition never received is dropped silently. Persistent ports do not drive termination. See [branch_labels.md](../harness/branch_labels.md). To instead omit a not-taken arm's ports and invoke the module with whichever arms delivered, use [branch\_aware\_join](branch_aware_join.md).

## Example use cases

**Joining results from two independent processing pipelines.** A test harness runs each test through a linter and a type-checker in parallel. Results from both arrive keyed by `test_id` in arbitrary order. `keyed_join` assembles each test's complete report before the aggregator module runs.

```yaml
nodes:
  - id: aggregate_results
    module: build_test_report
    contract: keyed_join
    contract_config:
      key_field: test_id
```

Linter port delivers `{"test_id": 42, "lint_ok": true}`. Type-checker port delivers `{"test_id": 42, "type_ok": false}`. The module is invoked once with both, keyed on `42`.

**Enriching records from two heterogeneous sources.** A customer record arrives from one API and an order history arrives from another, both carrying `customer_id`. `keyed_join` ensures the module always sees both together.
