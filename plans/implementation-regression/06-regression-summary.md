# Spec 06: regression-summary (`ConsoleRegressionSummaryProcessor`, `FileRegressionSummaryProcessor`)

**Depends on:** [05](05-regression-graph.md) — this spec edits `graphs/regression.yaml`.
**References:** [00-overview](00-overview.md#summary-aggregation); `rtl_buddy/src/rtl_buddy/rtl_buddy.py:421-431` — `do_rtl_regression` summary rendering; `graphs/log/summary.py` — the `test`-graph summary processors this reuses; `modules/funcs.py` — `LoggerMod` (`logger`), the generic value-to-log-event module.

## Before you start

Read `docs/logger/implementation.md`, `docs/logger/summary-processor.md`, `graphs/log/summary.py`, `docs/harness_configs/graph.md`, and `LoggerMod` in `modules/funcs.py`.

## Goal

Render rtl_buddy's regression summary table instead of the `test` table the regression graph inherits from `test.yaml`. The table needs three things no existing event carries — the builder name, the builder mode, and each suite's config path — so three `logger` nodes in `regression.yaml` emit them as info events, and a new pair of logging processors in a separate file collects those alongside the verdict events. `graphs/log/summary.py` is not modified.

## Output format

rtl_buddy's layout (`rtl_buddy.py:421-431`):

```

Regression Results Summary
Builder: <builder>, Builder Mode: <mode>
<suite path:<35> <test_name:<30> <result:<8> <desc[:50]>
...
```

- Rows are grouped by suite, in the order the suites' `regression_suite` events arrived; within a suite, rows keep capture order.
- The suite column is the `path` from the matching `regression_suite` event. A row is matched by its key's suite prefix (the part of `key` before the first `/`) against the event's `suite` field. A row with no matching suite event, or a key with no `/`, shows `NA` in the suite column.
- `None` fields render as `NA`, as in `summary.py`. A missing `regression_builder` or `regression_builder_mode` event renders its header value as `NA`.
- `desc` is truncated to 50 characters, as rtl_buddy does.
- The failure-count line `summary.py` appends when any row is `FAIL` is kept, so both graphs report failures the same way.
- No rows captured → `finalise()` is a no-op, as in `summary.py`.

## Events

| Event | Fields | Emitted by |
|---|---|---|
| `regression_builder` | `builder` | `log-builder` node |
| `regression_builder_mode` | `mode` | `log-builder-mode` node |
| `regression_suite` | `suite`, `path` | `log-suite` node, once per suite |
| verdict events | `test_name`, `key`, event-specific fields | existing modules — the same event→result mapping and `DESC_BUILDERS` as `summary.py` |

The three event names are fixed module-level constants in the plugin, matching the `event:` config on the `logger` nodes below.

## Plugin

`graphs/log/regression_summary.py`, a new file beside `summary.py`:

- Import `SummaryAccumulator`, `build_events`, `FAIL_EVENTS`, `colourise` from the sibling `summary` module (`from summary import ...`). The logging loader keeps a plugin file's directory on `sys.path` for sibling imports (`src/rtl_comrade/loader_logger.py`).
- A shared accumulator subclasses `SummaryAccumulator`: its `__call__` records `builder`, `mode`, and the ordered `suite → path` map from the three events above, then defers to `SummaryAccumulator.__call__` for verdict rows. It renders the table above.
- `ConsoleRegressionSummaryProcessor` and `FileRegressionSummaryProcessor` mirror `ConsoleSummaryProcessor` and `FileSummaryProcessor`: the same `Config` fields and defaults (`fail`, `pass`, `skip`, `na`, `suppress`, plus `out` on the file processor), colourised stdout on a TTY for the console processor, and a plain-text file with `OSError` swallowed for the file processor.
- Processor signatures must pass the loader's strict validation (`docs/logger/implementation.md` § Signature validation).

## Graph changes

In `graphs/regression.yaml`.

### Nodes

Add, in the file's block style (as `log-filelist` in `graphs/filelist.yaml`):

```yaml
- id: log-builder
  module:
    name: logger
    config:
      level: info
      event: regression_builder
      mapping: { builder: name }
  contract: default
- id: log-builder-mode
  module:
    name: logger
    config:
      level: info
      event: regression_builder_mode
      mapping: mode
  contract: default
- id: log-suite
  module:
    name: logger
    config:
      level: info
      event: regression_suite
      mapping: { suite: path.parent.name, path: path }
  contract: default
```

`suite: path.parent.name` is the same leaf-directory name `parse-suite-config` stamps into the key with `prefix_suite: true`, so rows and suite events match on it.

### Edges

```yaml
- { src: { node: resolve-builder }, dst: { node: log-builder, port: value } }
- { src: { cli: builder_mode, type: str, default: "reg", flags: ["--builder-mode", "-M"] }, dst: { node: log-builder-mode, port: value } }
- { src: { node: parse-suite }, dst: { node: log-suite, port: value } }
```

### Logging block

Replace the `logging:` block carried over from `test.yaml`:

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

## Deliverables

- `graphs/log/regression_summary.py` (new).
- `graphs/regression.yaml` — the nodes, edges, and logging block above.

## Tests

### Plugin tests

In `graphs/tests/test_regression_summary.py` (new), loading the plugin the way `graphs/tests/test_summary.py` loads `summary.py`, with `graphs/log` on `sys.path` so the sibling import resolves.

- Builder, mode, and two suites' events, then verdict rows → header line reads `Builder: <builder>, Builder Mode: <mode>`; rows are grouped under each suite's path in suite-event order.
- Two suites with a same-named test → one row under each suite's path.
- A row whose key prefix matches no suite event → suite column `NA`.
- No builder or mode event → `NA` in the header.
- `desc` longer than 50 characters is truncated.
- A `FAIL` row → failure-count line appended.
- No rows → `finalise()` writes nothing (console) and creates no file (file processor).
- Console processor colourises only when stdout is a TTY; file processor writes plain text and swallows `OSError`.
- Both processors pass the loader's processor signature validation.

### Graph-level tests

- `graphs/regression.yaml` still loads with no cycles, overloaded inputs, `missing_required_inputs`, or `unknown_persistent_ports`.
- The graph contains `log-builder`, `log-builder-mode`, `log-suite`, and its logging block names `FileRegressionSummaryProcessor` and `ConsoleRegressionSummaryProcessor` from `log/regression_summary.py`.

### E2E tests

From the fixture project root (`tests/e2e/fixtures/proj`), as in [05](05-regression-graph.md#e2e-tests):

- `rtl-comrade regression -l 0` → stdout contains `Regression Results Summary`, `Builder: <fixture default builder>, Builder Mode: reg`, and a `basic` `PASS` row whose suite column is the resolved `verif/sandbox/tests.yaml` path.
- `rtl-comrade regression -l 0 -M debug` → header reads `Builder Mode: debug`.

## Acceptance criteria

- All test stages pass (`docs/testing.md`).
- A regression run prints rtl_buddy's regression table: title, builder/mode line, and suite-path column.
- `graphs/log/summary.py` is unchanged; the `test` and `randtest` graphs' summaries are unaffected.

## Docs

- Add `docs/logger/regression-summary-processor.md`, following `docs/logger/summary-processor.md`.
- Update `docs/graphs/regression.md` and `docs/graphs/regression-dataflow-diagram.md` for the three `logger` nodes, their edges, and the logging block.
- Add an entry to `docs/divergences.md`: the suite column shows the resolved suite config path, where rtl_buddy prints the reg config directory joined with the unnormalised `test-configs` entry (e.g. `<reg dir>/../verif/sandbox/tests.yaml`).

Follow `docs/creating-documentation.md`.

## Constraints

- **Observational.** The processors only collect and render; they drive no graph behaviour.
- **No module changes.** The three events come from `logger` nodes wired in the graph; no shared module gains an event.
- **`summary.py` untouched.** Reuse it by import; do not edit it.
