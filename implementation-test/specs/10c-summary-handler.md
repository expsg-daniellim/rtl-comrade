# Spec 10c: summary logging plugin (`SummaryHandler` + `drop_summary_events`)

**Depends on:** spec 01 (schema), spec [10a](10a-early-stop-gate.md) /
[10b](10b-git-status.md) (emit the `test_result` / `git_state` events this handler
collects). No dependency on spec 02 any more — the `fan-in-results` relay was removed by
TODO #15.
**References:** [03 — Control section](../03-module-catalog.md),
[05 — Re-convergence](../05-branching-and-results.md#re-convergence-the-summary-is-a-logging-concern-not-a-graph-node),
[07 item 27](../07-ambiguities-and-assumptions.md), `docs/logger/implementation.md`,
`docs/harness/logging.md`. Parent index:
[10 — Control module, git-status, and the summary logging plugin](10-control-aggregate-modules.md).

## Goal

Implement the per-graph **logging plugin** that renders the summary table and git stateline
in its `finalise()` teardown hook — replacing the removed `aggregate-results` sink
(TODO #15). The exit code is driven solely by the per-emission `log.error` at each failure
site, not by this handler.

## Before you start

Read `docs/logger/implementation.md` (writing a logging plugin; the `finalise()` teardown
hook) and the "Per-Graph Custom Logging" + "custom handler inherits only the shared
preprocessors" sections of `docs/harness/logging.md`. The handler attaches **no** formatter
and reads `record.msg` as the raw event dict.

## Deliverables

In `graphs/log/summary.py` — `SummaryHandler` + `drop_summary_events`:

The summary is a per-graph logging plugin, wired via the `logging` block in
[`graphs/test.yaml`](../06-graph-yaml.md). Two exported objects:

- `SummaryHandler(logging.Handler)` — attaches no formatter, so `record.msg` is the raw event
  dict. `emit` collects `event["event"] == "test_result"` rows into `self._rows` and the
  single `git_state` event into `self._git_state`. `finalise(self)` (the teardown hook
  `App.cleanup` invokes) renders the git stateline (if any) and the `key`/`result`/`desc`
  table; it is a **no-op when `self._rows` is empty** (list-mode, or a CRITICAL abort before
  any result). It drives **no** exit code — the exit is the per-emission `log.error`.
- `drop_summary_events(logger, method_name, event_dict)` — a structlog processor that raises
  `structlog.exceptions.DropEvent` when `event_dict["event"]` is `test_result` or `git_state`,
  so the console `ConsoleRenderer` (`include_default: true`) does not duplicate the rows the
  handler will render. The handler is a separate root handler with its own empty chain, so it
  still receives the events.

Sketches in [05 — The `SummaryHandler` logging plugin](../05-branching-and-results.md#the-summaryhandler-logging-plugin).
**CRITICAL path**: the handler is added after `LoggingFatalHandler`, so it never observes
`CRITICAL` and never renders on a fatal abort — acceptable, since no results exist then.

**Compatibility source:** `rtl_buddy/src/rtl_buddy/rtl_buddy.py:203-207` — the `do_cmd_test` summary loop (`f"{test_name:<30} {result:<8} {desc:<30}"`) that this handler reproduces out-of-graph; the OR-accumulated exit it replaces is `rtl_buddy.py:206`.

`graphs/log/summary.py` is referenced by `path`/`name` in the `logging` block, not a manifest.

## Tests

`graphs/tests/test_summary.py` (or alongside the plugin):

- feeding N `test_result` events (mix of PASS/SKIP/FAIL/NA) + one `git_state` → `finalise()`
  renders one table with the git stateline; empty input → `finalise()` is a no-op.
- `drop_summary_events` raises `DropEvent` on `test_result`/`git_state` and passes every other
  event dict through unchanged.
- the handler attached with no formatter receives the raw dict (round-trip a `logging.LogRecord`
  whose `msg` is the event dict).

## Acceptance criteria

- Tests pass.
- Exit-code semantics: a run with any FAIL/NA emits ≥1 `log.error` → harness exit 1; an
  all-PASS/SKIP run emits none → exit 0. This reproduces rtl_buddy's
  `exit_code |= 0 if is_pass() else 1` via the per-emission `log.error`, not an aggregator.
- The summary table content matches what `aggregate-results.finalise()` previously produced
  (same `key`/`result`/`desc` columns), now with the git stateline prepended.
- No `fan-in`/`agg` node exists in `graphs/test.yaml`; the `logging` block resolves
  `graphs/log/summary.py` and renders on a normal and a deferred-`ERROR` run (not on CRITICAL).

## Notes

Adding a new terminal-result source means adding one `log.info("test_result", ...)` call at
the new site — no edge, no handler change.
