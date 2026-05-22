# `keyed_join` / `required_inputs_by_key`

**Class:** `KeyedJoinContract` (`contracts/keyed_join.py`)

[Back to index](index.md)

Groups incoming items by a correlation key extracted from each payload dict and invokes the module when all required ports have delivered a value for the same key. Items may arrive interleaved across ports and are buffered until a complete group is available. `required_inputs_by_key` is an alias for the same class.

## Config

```yaml
contract: keyed_join
contract_config:
  key_field: test_id
```

| Field | Type | Purpose |
|---|---|---|
| `key_field` | `str` | Name of the field within each payload dict used as the correlation key |

Each payload must be a `dict` containing `key_field`. The key type must support `<` comparison (e.g. `int`, `str`) because ties between simultaneously complete keys are broken by minimum value.

## Termination

Ends when any port ends. Buffered items whose key is incomplete at that point are logged as an error.

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
