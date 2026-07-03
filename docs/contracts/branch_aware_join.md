# `branch_aware_join`

**Class:** `BranchAwareJoinContract` (`contracts/branch_aware_join.py`)

[Back to index](index.md)

See also:

- [docs/module-implementation/implementation.md](../module-implementation/implementation.md) — variadic inputs and their effect on port validation
- [docs/harness/branch_labels.md](../harness/branch_labels.md) — how `branch_labels` are determined and propagated

Joins inputs by correlation key like `keyed_join`, but uses each port's `branch_labels` to exclude ports whose branch arm was not selected for a given key. This allows fan-in after `if/else` routing nodes where only one branch executes per item, without the upstream branches emitting any placeholder value.

## Config

```yaml
contract: branch_aware_join
contract_config:
  key_field: request_id
```

| Field | Type | Purpose |
|---|---|---|
| `key_field` | `str` | Name of the field — an object attribute or a dict entry — used as the correlation key |

The key is read from `key_field` as an attribute when present, otherwise as a dict entry, matching `keyed_join`.

## Branch awareness

Each port carries `branch_labels` assigned by the label-propagation pass in `Graph.from_config` (see [branch_labels.md](../harness/branch_labels.md)). The contract reads them to decide, per key, which ports must participate:

- Two ports that are alternative **arms** of the same origin (equal origin id in their labels, differing arm) are mutually exclusive per key. When a key arrives on one arm, its co-arm siblings are **excluded** from that key's assembly, so the join fires without them and their module parameters fall back to their Python defaults.
- A port with **no** branch labels is an unconditional participant: it is awaited until it delivers the key or ends.
- A port that **ends** is excluded from any key it has not already delivered.

A key is complete once every port is present, ended, or excluded by a selected co-arm sibling. The join then emits the dict of ports that participated in that key.

If two co-arm siblings both hold the same key — one origin having selected two arms for it — a `conflicting_arms` error is logged (`contract`, `origin`, `key`), which marks the run as failed.

## Termination

Ends only once **every** port has ended.

## Module side: defaulted parameters

Because a port excluded from a key does not appear in the dict passed to the module, any port that may be excluded (belongs to a branch arm) must have a default value in the module's `run(...)` signature. The harness will not inject a value for an absent port.

```python
def run(self, branch_a=None, branch_b=None, **kwargs):
    result = branch_a or branch_b
    ...
```

Note that the `**kwargs` above makes this module non-definite-input: its ports come from the incoming edges rather than the signature, and the harness emits a `non_definite_inputs` warning for the node. Drop `**kwargs` if you want the named ports validated statically.

## Example use cases

**Fan-in after if/else routing.** A router node inspects each record's `type` field and sends it down one of two processing branches. Both branches feed a final aggregator. The router is a branch origin, so `branch_a` and `branch_b` are co-arm siblings; whichever arm was not taken for a given `request_id` is excluded from that key's assembly.

```yaml
nodes:
  - id: aggregator
    module: merge_results
    contract: branch_aware_join
    contract_config:
      key_field: request_id
```

For `request_id=7`, branch A delivers `{"request_id": 7, "result": "ok"}` and branch B delivers nothing for that key. The module receives `{"branch_a": <payload>}` — branch B is excluded, so the module's `branch_b=None` default applies.

**Optional enrichment step.** An enrichment node runs only for records that meet a relevance threshold. For records below it the enrichment port simply produces nothing. The downstream joiner uses `branch_aware_join` so both paths converge without the enrichment node emitting placeholder outputs.
