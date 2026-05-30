# Spec 19: SuiteResultAccumulate

## What this covers

Implement `SuiteResultAccumulate` in `modules/rtl_buddy_compat/results.py`. This is the fan-in node that receives result rows one at a time from all nine branches and assembles the final `SuiteResultSummary`. It uses the `fan_in` contract from spec 01.

## Prerequisites

Specs 00 and 01 (artefacts + `FanInContract`) must be complete.

## Before you start

Read:
- `rtl_buddy/src/rtl_buddy/rtl_buddy.py:L192-L199` — final summary iteration
- `rtl_buddy/src/rtl_buddy/rtl_buddy.py:L237-L289` — result row construction across all branches
- `docs/contract-implementation.md` — how `fan_in` delivers items one at a time

The `fan_in` contract delivers one `TestResultRow` per `run()` invocation via a synthetic `item` port. Rows arrive in undefined order (one per upstream emission). The module accumulates into `self.rows` and emits the final sorted summary from `finalise()`, which the harness calls once all input streams have ended.

## File: `modules/rtl_buddy_compat/results.py`

Create this file. Spec 20 will add `SummaryRender` to it.

### `SuiteResultAccumulate`

```
contract: fan_in
inputs (9 named ports in graph, multiplexed by contract into single "item" port):
  post_default_result
  post_uvm_result
  compile_fail_result
  seed_fail_result
  timeout_result
  early_stop_pre_result
  early_stop_comp_result
  early_stop_sim_result
  skip_result
outputs: default → SuiteResultSummary  (emitted from finalise())
```

```python
from dataclasses import dataclass, field
from .artefacts import TestResultRow, SuiteResultSummary


@dataclass
class SuiteResultAccumulate:
    rows: list[TestResultRow] = field(default_factory=list, init=False)

    def run(self, item: TestResultRow) -> None:
        self.rows.append(item)

    def finalise(self) -> SuiteResultSummary:
        self.rows.sort(key=lambda r: (
            r.key.suite_path,
            r.key.expanded_index,
            r.key.run_id if r.key.run_id is not None else -1,
        ))
        return SuiteResultSummary(rows=self.rows)
```

`run()` returns `None` — no per-row output. `finalise()` is called by the harness after all nine input streams have ended; its return value is emitted on the `default` port.

Compatibility: `rtl_buddy.py:L192-L199, L237-L289`.

## Register in `modules/rtl_buddy_compat/config.yaml`

Append to `files`:

```yaml
- file: results.py
  plugins:
  - name: suite_result_accumulate
    class_name: SuiteResultAccumulate
```

Spec 20 will add `SummaryRender` to this entry.

## Tests

Write `modules/rtl_buddy_compat/tests/test_suite_result_accumulate.py`.

Test `run()` and `finalise()` directly with plain Python objects (no contract machinery needed).

- Call `run()` multiple times with rows from different ports → `finalise()` returns `SuiteResultSummary` containing all rows
- No `run()` calls → `finalise()` returns `SuiteResultSummary(rows=[])`
- Mix of rows with different `expanded_index` values → output is sorted by `expanded_index`
- Rows with `run_id=None` sort before rows with `run_id=0`
- 3 calls to `run()` → `finalise()` returns 3 rows

## Constraints

- `run()` must return `None`; no per-row output is emitted.
- Sort order must be deterministic: `suite_path` primary, `expanded_index` secondary, `run_id` tertiary (`None` sorts as `-1`).
- `finalise()` is not called from `run()` — the harness calls it separately after all streams end.
