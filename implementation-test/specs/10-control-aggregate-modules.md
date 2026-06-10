# Spec 10: Control module, git-status, and the summary logging plugin

**Depends on:** spec 01 (schema). No dependency on spec 02 any more — the `fan-in-results`
relay was removed by TODO #15.
**References:** [03 — Control section](../03-module-catalog.md),
[05 — Re-convergence](../05-branching-and-results.md#re-convergence-the-summary-is-a-logging-concern-not-a-graph-node),
[07 item 27](../07-ambiguities-and-assumptions.md), `docs/logger/implementation.md`,
`docs/harness/logging.md`.

## Goal

Implement the cross-cutting early-stop gate (reused at three boundaries), the `git-status`
setup node, and the per-graph **logging plugin** that renders the summary table and drives
exit semantics — replacing the removed `aggregate-results` sink (TODO #15).

## Before you start

Read `docs/logger/implementation.md` (writing a logging plugin; the `finalise()` teardown
hook) and the "Per-Graph Custom Logging" + "custom handler inherits only the shared
preprocessors" sections of `docs/harness/logging.md`. The handler attaches **no** formatter
and reads `record.msg` as the raw event dict.

## Deliverables

### `modules/rtl_test/control.py` — `EarlyStopGateMod`

`(payload, early_stop:str="post")` with module `Config` containing `phase:str` (one of
`pre`/`comp`/`sim`). `payload` is `ctx` at `gate-pre`/`gate-comp` and `test_run` at
`gate-sim`; the module reads only `payload["key"]` and is agnostic to the shape otherwise.
Compares `early_stop` against `phase` using the ordering `pre < comp < sim < post`; if stop
here → `("stop", {"key": payload["key"], "result": EarlyStopResults(f"Stopped early at
{phase}")})` **and** `log.info("test_result", key=..., result="NA", desc=...)`; else
`("go", payload)`. Three node instances, differing only in `config.phase`. The `stop` port is
**unwired** (TODO #15) — the harness logs `no_destination` at INFO.
**Failure handling**: routing only; no exception, no `log.error` (a `stop` is a normal
terminal, not a failure). See [05 — Log idioms](../05-branching-and-results.md#log-idioms-per-failure-site).

### `modules/rtl_test/setup.py` — `GitStatusMod`

Zero-input `unit` node. `run(self)` shells out to git (`git rev-parse --abbrev-ref HEAD`,
`git rev-parse HEAD`, `git status --porcelain`) and calls
`log.info("git_state", branch=..., sha=..., dirty=bool(...))` once. If not in a git repo or
`git` is unavailable, `log.warning("git_state_unavailable", reason=...)` and emit nothing
collectable — **never** `log.error`/`log.critical`. Returns `("default", True)`; the port is
unwired (the node exists only for the side-effect log).

### `graphs/log/summary.py` — `SummaryHandler` + `drop_summary_events`

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

Manifest entries for `EarlyStopGateMod` / `GitStatusMod` per [06](../06-graph-yaml.md);
`graphs/log/summary.py` is referenced by `path`/`name` in the `logging` block, not a manifest.

## Tests

`modules/tests/test_control.py`:
- Gate routing matches expected ordering across all four `early_stop` values for each of the
  three `phase` configurations; a `stop` also emits one `test_result` event at INFO.
- `GitStatusMod` in a temp git repo emits `git_state` with branch/sha/dirty; outside a repo
  emits `git_state_unavailable` at WARNING and no ERROR/CRITICAL.

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

The phase ordering should reuse rtl_buddy's `RunDepth` enum (or a small local equivalent in
the schema package from spec 01) rather than ad-hoc string compares.
