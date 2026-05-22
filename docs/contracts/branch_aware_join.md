# `branch_aware_join`

**Class:** `BranchAwareJoinContract` (`contracts/branch_aware_join.py`)

[Back to index](index.md)

Joins inputs by correlation key like `keyed_join`, but accounts for control-flow branches that intentionally skip some ports. A port carrying `BranchSkip(key=k)` is treated as satisfied for key `k` and omitted from the dict passed to the module. This allows fan-in after `if/else` routing nodes where only one branch executes per item.

## Config

```yaml
contract: branch_aware_join
contract_config:
  key_field: request_id
```

| Field | Type | Purpose |
|---|---|---|
| `key_field` | `str` | Field within each real-data payload dict used as the correlation key |

## Sentinel

`BranchSkip` is imported from `contracts.sentinels`. Emit it as a payload value on a port that was bypassed for a given key.

```python
from contracts.sentinels import BranchSkip

async def run(self, items, key):
    if condition:
        yield ("branch_a", result)
        yield ("branch_b", BranchSkip(key=key))
    else:
        yield ("branch_a", BranchSkip(key=key))
        yield ("branch_b", result)
```

The `key` argument to `BranchSkip` must match the value that would be found at `payload[key_field]` on real data items so the contract can correlate them.

## Termination

Ends when any port ends.

## Module side: defaulted parameters

Because skipped ports are absent from the dict passed to the module, any port that may be skipped must have a default value in the module's `run(...)` signature. The harness will not inject a value for an absent port.

```python
def run(self, branch_a=None, branch_b=None, **kwargs):
    result = branch_a or branch_b
    ...
```

## Example use cases

**Fan-in after if/else routing.** A router node inspects each record's `type` field and sends it down one of two processing branches. Both branches feed a final aggregator. The router emits `BranchSkip` on whichever branch was not taken so the aggregator knows both branches are accounted for and can fire.

```yaml
nodes:
  - id: aggregator
    module: merge_results
    contract: branch_aware_join
    contract_config:
      key_field: request_id
```

For `request_id=7`, branch A delivers `{"request_id": 7, "result": "ok"}` while branch B delivers `BranchSkip(key=7)`. The module receives `{"branch_a": <payload>}` — branch B is absent, so the module's `branch_b=None` default applies.

**Optional enrichment step.** An enrichment node runs only for records that meet a relevance threshold. A bypass path emits `BranchSkip` for records that do not. The downstream joiner uses `branch_aware_join` so both paths converge without requiring the enrichment node to emit dummy outputs.
