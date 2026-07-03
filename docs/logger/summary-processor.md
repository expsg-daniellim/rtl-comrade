# `SummaryProcessor`

**Class:** `SummaryProcessor` (`graphs/log/summary.py`)

See also:

- [implementation.md](implementation.md) — how logging plugins are written, classified, configured, and finalised
- [docs/harness/logging.md](../harness/logging.md) — the processor/handler model and `DropEvent`
- [docs/modules/summarise-results.md](../modules/summarise-results.md) — the in-graph node that supersedes this plugin

A per-graph logging **processor** (not a stdlib `logging.Handler` — it is classified as a processor because it is callable and defines `__call__`). It assembles the test-results summary table from log events rather than from an in-graph node: it captures each `test_result` event as it flows through the log pipeline, optionally suppresses it from the rendered output, and prints the accumulated table at end of run.

## Status: dormant

`SummaryProcessor` is **not wired into** `graphs/test.yaml`. It is the log-event-driven alternative to the in-graph [summarise-results](../modules/summarise-results.md) node, which won out: the `test` graph builds its summary as a proper graph node (fed by the [`any`](../contracts/any.md) contract) instead. The plugin is kept as a worked reference for the processor + `finalise()` pattern — a processor that accumulates state across a run in `__call__` and flushes it in `finalise()`.

## Config

```yaml
logging:
  handlers:
  - path: log/summary.py
    name: SummaryProcessor
    config:
      events:   [test_result]
      suppress: [test_result]
```

| Field | Type | Default | Purpose |
|---|---|---|---|
| `events` | `list[str]` | `["test_result"]` | event names to capture into summary rows |
| `suppress` | `list[str]` | `["test_result"]` | captured events to drop from the log stream (must be a subset of `events` to take effect) |

## Behaviour

On each event, `__call__` reads `event_dict["event"]`:

- if the name is in `events`, it appends a row (`test_name`, `key`, `result`, `desc` pulled from the event dict);
- if that name is also in `suppress`, it raises `structlog.exceptions.DropEvent` so the event is removed from the rendered log output (the row is still recorded);
- otherwise the event dict is returned unchanged and continues down the chain.

Capturing a row and suppressing the event are independent: an event in `events` but not `suppress` contributes a row *and* still renders.

## End-of-run output

`finalise()` (called once at run end by `App.cleanup`) prints the accumulated `Test Results Summary` table to stdout — one `test_name / result / desc` line per row, `None` fields shown as `NA`. Verdict tokens are ANSI-colourised when stdout is a TTY (`PASS` green, `FAIL` red, `NA` yellow; `SKIP` left plain, matching upstream `rtl_buddy`) via the module-level `colourise` helper. If no rows were captured, it prints nothing.

Unlike [summarise-results](../modules/summarise-results.md), this plugin only renders — it does not itself log an `ERROR` on failures, so it does not drive the run's exit status.
