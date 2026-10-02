# Regression Summary Processors

**Classes:** `ConsoleRegressionSummaryProcessor`, `FileRegressionSummaryProcessor`, `RegressionSummaryAccumulator` (`graphs/log/regression_summary.py`)

See also:

- [summary-processor.md](summary-processor.md) — the `test`-graph summary processors these extend; event matching, `DESC_BUILDERS`, and `suppress` behave as described there
- [implementation.md](implementation.md) — how logging plugins are written, classified, configured, and finalised
- [docs/graphs/regression.md](../graphs/regression.md) — the `regression` graph, whose `logger` nodes emit the metadata events below

Per-graph logging **processors** that render upstream `rtl_buddy`'s regression results table for the `regression` graph. They collect the same verdict events as the `test`-graph summary processors, plus three metadata events that carry what the table needs and no verdict event has: the builder name, the builder mode, and each suite's config path.

## Architecture

`RegressionSummaryAccumulator` subclasses `SummaryAccumulator` (imported from the sibling `summary.py`). Its `__call__` records the builder, the mode, and an ordered `suite → path` map from the metadata events, then defers to `SummaryAccumulator.__call__`, which captures verdict rows exactly as in the `test` graph. Metadata events are never dropped.

`ConsoleRegressionSummaryProcessor` — prints the table to stdout on `finalise()`, colourised when stdout is a TTY (the same colours as `ConsoleSummaryProcessor`).

`FileRegressionSummaryProcessor` — writes the plain-text table to a file on `finalise()`. A write failure (`OSError`) is silently swallowed.

## Metadata events

| Event | Fields | Emitted by |
|---|---|---|
| `regression_builder` | `builder` | `log-builder` node |
| `regression_builder_mode` | `mode` | `log-builder-mode` node |
| `regression_suite` | `suite`, `path` | `log-suite` node, once per suite |

The event names are fixed module-level constants (`BUILDER_EVENT`, `BUILDER_MODE_EVENT`, `SUITE_EVENT`) and must match the `event:` config of the graph's `logger` nodes.

## Config

The same fields and defaults as [summary-processor.md § Config](summary-processor.md#config): `fail`, `pass`, `skip`, `na`, `suppress`, and `out` on the file processor.

```yaml
logging:
  handlers:
  - path: log/regression_summary.py
    name: FileRegressionSummaryProcessor
    config:
      out: "{graph}/summary.log"
  - path: log/regression_summary.py
    name: ConsoleRegressionSummaryProcessor
```

## End-of-run output

```

Regression Results Summary
Builder: <builder>, Builder Mode: <mode>
<suite path:<35> <test_name:<30> <result:<8> <desc[:50]>
```

- Rows are grouped by suite, in the order the `regression_suite` events arrived; within a suite, rows keep capture order.
- A row's suite is the part of its `key` before the first `/` (the prefix `parse-suite-config` adds under `prefix_suite: true`), matched against the events' `suite` field. A row with no matching suite event, or a key with no `/`, shows `NA` in the suite column and is listed after the grouped rows.
- `None` fields render as `NA`; a missing `regression_builder` or `regression_builder_mode` event renders its header value as `NA`.
- `desc` is truncated to 50 characters.
- If any row is `FAIL`, the failure-count line from [summary-processor.md](summary-processor.md#end-of-run-output) is appended.
- If no rows were captured, `finalise()` is a no-op.
