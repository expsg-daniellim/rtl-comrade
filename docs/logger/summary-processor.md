# Summary Processors

**Classes:** `ConsoleSummaryProcessor`, `FileSummaryProcessor`, `SummaryAccumulator` (`graphs/log/summary.py`)

See also:

- [implementation.md](implementation.md) — how logging plugins are written, classified, configured, and finalised
- [docs/harness/logging.md](../harness/logging.md) — the processor/handler model and `DropEvent`

Per-graph logging **processors** that assemble the test-results summary table from diagnostic log events. Each module in the `test` graph already emits a named event on every failure, pass, skip, or early-stop path; the processors match those events by name, accumulate one row per test, and render the table at end of run via `finalise()`.

## Architecture

`SummaryAccumulator` is the shared base: it holds the `events` mapping (event name → result category) and a `rows` list. Its `__call__` checks each event's name against the mapping; on a match it derives a human-readable description via the `DESC_BUILDERS` dict, appends a row, and optionally suppresses the event (raises `DropEvent`) if the event name is in the `suppress` set. Capturing a row and suppressing the event are independent: an event in `events` but not `suppress` contributes a row *and* still renders.

`ConsoleSummaryProcessor` — prints the colourised table to stdout on `finalise()` (ANSI colours when stdout is a TTY; `PASS` green, `FAIL` red, `NA` yellow; `SKIP` left plain, matching upstream `rtl_buddy`).

`FileSummaryProcessor` — writes the plain-text (no ANSI) table to a file on `finalise()`. A write failure (`OSError`) is silently swallowed.

## Config

Both processors share the same config shape:

```yaml
logging:
  handlers:
  - path: log/summary.py
    name: ConsoleSummaryProcessor
    config:
      suppress: [compile_failed]   # optional: suppress matched events from console output
  - path: log/summary.py
    name: FileSummaryProcessor
    config:
      out: "{graph}/summary.log"
```

| Field | Type | Default | Purpose |
|---|---|---|---|
| `fail` | `list[str]` | 31 known fail events | event names categorised as FAIL |
| `pass` | `list[str]` | `["parse_log_passed", "parse_uvm_passed"]` | event names categorised as PASS |
| `skip` | `list[str]` | `["test_skipped"]` | event names categorised as SKIP |
| `na` | `list[str]` | `["test_stopped_early", "parse_log_unknown"]` | event names categorised as NA |
| `suppress` | `list[str]` | `[]` | matched events to drop from the log stream (must be a subset of the above to take effect) |
| `out` | `Path` | `summary.log` | (FileSummaryProcessor only) output file; `{graph}` prefix resolved relative to the graph file directory |

The defaults cover every diagnostic event the `test` graph's modules emit; override only to add custom events or suppress specific ones.

## End-of-run output

`finalise()` renders the accumulated table: one `test_name / result / desc` line per row, `None` fields shown as `NA`. If any rows have result `FAIL`, a failure count line is appended. If no rows were captured, `finalise()` is a no-op.

The processors do not themselves log an `ERROR` — each module's `log.error` already drives the run's exit status via `handler.failure`.

## DESC_BUILDERS

Module-level dict mapping event names to functions that derive a human-readable description from the event dict's natural fields. No fields are added to events for the summary's benefit; the builder reads what the module already emits.
