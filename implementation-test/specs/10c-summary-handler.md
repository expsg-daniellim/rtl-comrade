# Spec 10c: summary logging plugin (`SummaryProcessor`)

**Depends on:** spec 01 (schema), spec [10a](10a-early-stop-gate.md) /
[10b](10b-git-status.md) (emit the `test_result` events this processor accumulates). Uses the
**per-run processor-finalisation hook**: `App.cleanup` finalises the run's processors (then
handlers), duck-typed, before the failure check and not on a `CRITICAL` exit
(`docs/logger/implementation.md:95-99`, timing at `:165-167`). No dependency on spec 02 — the
`fan-in-results` relay was removed by TODO #15.
**References:** [03 — Control section](../03-module-catalog.md),
[05 — Re-convergence](../05-branching-and-results.md#re-convergence-the-summary-is-a-logging-concern-not-a-graph-node),
[07 item 27](../07-ambiguities-and-assumptions.md), `docs/logger/implementation.md`,
`docs/harness/logging.md`. Parent index:
[10 — Control module, git-status, and the summary logging plugin](10-control-aggregate-modules.md).

## Goal

Implement the per-graph logging **processor** that accumulates the per-test outcome rows from a
**`Config` watch-list of event names** (`test_result` from the otherwise-silent paths, plus the
failure terminals' `compile_failed`/`sim_timeout`/`*_failed`) and renders the summary table once,
in its `finalise()` teardown hook — replacing the removed `aggregate-results` sink (TODO #15).
Its role is deliberately narrow: **collect the watch-list outcomes only.** `git_state` and every
other non-watched event pass straight through to the console untouched; there is no git stateline
in the table. The exit code is driven solely by the per-emission `log.error` at each failure
site, not by this processor.

> **Filename note.** This file is named `10c-summary-handler.md` for link stability; the plugin
> is a structlog **processor** (`SummaryProcessor`), not a `logging.Handler`.

## Before you start

Read `docs/logger/implementation.md` (writing a structlog processor; the per-run
finalisation hook) and the "Processors", "Suppressing events with `DropEvent`",
"Per-Graph Custom Logging", and "`include_default` and the terminal renderer" sections of
`docs/harness/logging.md`. The plugin is a **stateful processor class instance** in the
harness handler's formatter chain — it sits **before** `ConsoleRenderer` (non-terminal under
`include_default: true`), so `__call__` returns an `EventDict` and never sees a pre-rendered
string. It is classified as a processor (not a handler) because it does not subclass
`logging.Handler`; as a processor *class* it is instantiated once per run, so `self._rows`
starts empty each run. This module **creates** `graphs/log/summary.py` and is its sole writer
(spec [11](11-graph-and-manifests.md) only *wires* the plugin into the graph's `logging` block,
it does not append to the file).

## Surface

Wiring surface and skeleton, mirrored from
[05 — The `SummaryProcessor` logging plugin](../05-branching-and-results.md#the-summaryprocessor-logging-plugin)
— that section is the design view, this is the build view; update both when behaviour changes.
This is a structlog **processor**, not a graph module and not a `logging.Handler`: it has no
`run()`, no ports, and no module manifest entry. In place of the module I/O block, the wiring
surface below names what it accumulates, what it passes through, its teardown hook, and how it
is registered.

```
plugin:         SummaryProcessor  (structlog processor class — stateful; NOT a logging.Handler)
chain position: harness handler's formatter chain, before ConsoleRenderer (include_default: true)
accumulates:    a Config watch-list of per-test outcome events (default: test_result,
                compile_failed, sim_timeout, load_model_failed, sweep_failed, preproc_failed,
                filelist_failed, replay_seed_invalid) → {test_name,key,result,desc} appended to
                self._rows (test_name = the test's get_name(), the table's first column)
suppresses:     only the Config `suppress` subset (default: test_result) via DropEvent; the
                failure events are collected but still print to the console as errors
passes through: every non-watched event, incl. git_state → ConsoleRenderer (returned unchanged)
teardown hook:  finalise()  — invoked per-run at run end (after the gather, before failure check)
registration:   logging block in graphs/test.yaml by path/name  (NOT a module manifest)
exit code:      none  (driven per-emission by log.error at each failure site)
```

```python
# graphs/log/summary.py
from __future__ import annotations
from typing import Any
from collections.abc import MutableMapping
from serde import serde, field
from structlog.exceptions import DropEvent

class SummaryProcessor:
    @serde
    class Config:
        # per-test outcome events to collect into the table — the parsers/skip/early-stop emit
        # `test_result`; the failure terminals keep their own event names (which already exist).
        events: list[str] = field(default_factory=lambda: [
            "test_result", "compile_failed", "sim_timeout", "load_model_failed",
            "sweep_failed", "preproc_failed", "filelist_failed", "replay_seed_invalid",
        ])
        # subset of `events` whose per-event console line is suppressed (summary-only rows)
        suppress: list[str] = field(default_factory=lambda: ["test_result"])

    def __init__(self, config):
        self._events = set(config.events)        # watch-list
        self._suppress = set(config.suppress)    # drop-from-console subset
        self._rows = []                          # fresh per run

    def __call__(self, logger, method_name: str,
                 event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
        name = event_dict.get("event")
        if name in self._events:
            self._rows.append({                  # harvest the row
                "test_name": event_dict.get("test_name"),   # summary's first column (rtl_buddy parity)
                "key": event_dict.get("key"),
                "result": event_dict.get("result"),
                "desc": event_dict.get("desc"),
            })
            if name in self._suppress:
                raise DropEvent                  # summary-only → no per-event console line
        return event_dict                        # non-watched events (incl. git_state, failure errors) flow on

    def finalise(self):                          # per-run teardown hook, at run end
        if not self._rows:                       # list-mode / CRITICAL abort → no-op
            return
        ...                                      # render the test_name/result/desc table
```

It accumulates the **watch-list** events and nothing else. The failure events
(`compile_failed`/`sim_timeout`/`*_failed`) are collected into rows but **not** suppressed, so
they still print as errors on the console; only the summary-only `test_result` rows are
`DropEvent`'d. `git_state` is not on the watch-list — the processor returns it unchanged, so it
prints via `ConsoleRenderer` at run start like any other log line (no `self._git_state`, no git
rendering here).

## Algorithm

`__call__(logger, method_name, event_dict)` — runs per log event, before `ConsoleRenderer`:
1. If `event_dict["event"]` is in the Config **watch-list** (`self._events`), harvest
   `{test_name, key, result, desc}` into `self._rows` (`test_name` = the test's `get_name()`,
   rendered as the summary's first column for rtl_buddy parity; `key` retained for correlation).
   If it is *also* in the `suppress` subset (default just
   `test_result`), `raise DropEvent` so its per-event console line is suppressed.
2. Otherwise return `event_dict` unchanged. Watched-but-unsuppressed events (the failure
   `log.error`s — `compile_failed` etc.) are both collected **and** returned, so they still print
   as errors; non-watched events, including `git_state`, fall straight through to `ConsoleRenderer`.

`finalise()` — the per-run teardown hook, invoked at run end (after the gather, before the
failure check):
3. If `self._rows` is empty (list-mode, or a CRITICAL abort before any result), return — a
   no-op.
4. Otherwise render the `test_name`/`result`/`desc` table from `self._rows` (`test_name` first,
   parity with rtl_buddy's `test_name` column — `rtl_buddy.py:204`). It drives no exit code
   (that is the per-emission `log.error` at each failure site).

## Deliverables

In `graphs/log/summary.py` — a single `SummaryProcessor` class:

- A structlog processor (a **stateful class instance**; classified as a processor because it
  is not a `logging.Handler` subclass, and instantiated once per run so `self._rows` is fresh).
- A `Config` carries the **watch-list** `events` — the per-test outcome event names to collect
  (default covers `test_result`, emitted by the parsers / `filter.skip` / `early-stop`, **plus**
  the failure terminals' own events: `compile_failed`, `sim_timeout`, `load_model_failed`,
  `sweep_failed`, `preproc_failed`, `filelist_failed`, `replay_seed_invalid`) — and a `suppress`
  subset (default `["test_result"]`). Each watched event must carry `test_name`/`key`/`result`/`desc`
  (`test_name` = the test's `get_name()`; the failure terminals enrich their existing
  `log.error(...)` with `test_name`/`result`/`desc`; see their specs).
- `__call__` harvests `{test_name, key, result, desc}` from every watched event into `self._rows`; it raises
  `structlog.exceptions.DropEvent` only for events in `suppress` (the summary-only `test_result`
  rows), and returns **everything else unchanged** — so the failure `log.error`s, `git_state`,
  and all module logs still reach the console.
- `finalise()` (the per-run teardown hook the harness invokes at run end) renders the
  `test_name`/`result`/`desc` table from `self._rows` (first column `test_name`, parity with
  rtl_buddy's `test_name` column). It is a **no-op when `self._rows` is empty**
  (list-mode, or a CRITICAL abort before any result). It drives **no** exit code.

There is **no** separate `drop_summary_events` processor: the single `SummaryProcessor` both
accumulates the rows and suppresses the summary-only ones. The summary plugin's *only* job is to
collect outcomes and render them once at the end.

Sketches in [05 — The `SummaryProcessor` logging plugin](../05-branching-and-results.md#the-summaryprocessor-logging-plugin).
**CRITICAL path**: on a `CRITICAL` record the harness exits before the per-run teardown runs,
so `finalise()` is never reached and no table renders — acceptable, since no results exist
then. On a normal or deferred-`ERROR` run the teardown runs (before the failure check) and the
table renders.

**Compatibility source:** `rtl_buddy/src/rtl_buddy/rtl_buddy.py:203-207` — the `do_cmd_test` summary loop (`f"{test_name:<30} {result:<8} {desc:<30}"`) that this processor reproduces out-of-graph; the OR-accumulated exit it replaces is `rtl_buddy.py:206`.

`graphs/log/summary.py` is referenced by `path`/`name` in the `logging` block, not a manifest.

## Tests

`graphs/tests/test_summary.py` (or alongside the plugin). Fixtures: a fresh
`SummaryProcessor(Config(...))` instance per test (default `Config` unless a case overrides the
watch-list); hand-built `event_dict`s; `capsys` for the rendered table; `pytest.raises(DropEvent)`
for the suppression cases. No graph/harness needed.

- Feed N `test_result` events (mix PASS/SKIP/FAIL/NA, each carrying `test_name`) through
  `__call__`, then `finalise()` → one table rendered with a `test_name`/`result`/`desc` row per
  event in arrival order (first column `test_name`).
- A watched **failure** event (e.g. `compile_failed` carrying `test_name`/`key`/`result`/`desc`) → a row is
  appended **and** the event is returned unchanged (no `DropEvent`), so it still reaches the
  console (boundary: collected-but-not-suppressed).
- No events fed → `finalise()` is a no-op, renders nothing (boundary: list-mode / CRITICAL
  abort before any result).
- `__call__` on a `test_result` event → `raise DropEvent` and `self._rows` grows by one (row
  accumulated, console line suppressed — `test_result` is in the default `suppress` set).
- `__call__` on a non-watched event (e.g. `git_state`, an arbitrary module log) → returns the
  `event_dict` unchanged, no `DropEvent` (so it survives to `ConsoleRenderer`); no
  `self._git_state` is kept.
- Config-driven watch-list: a `Config(events=["only_this"], suppress=[])` instance collects
  `only_this` events, drops nothing, and ignores `test_result` (boundary: the watch-list and
  suppress set are config, not hard-coded).
- State persists across calls on one instance: K watched calls then `finalise()` →
  renders K rows (accumulation is run-long, instance-held).
- The `__call__` signature satisfies the strict processor contract: three positional params
  after `self` (`logger`, `method_name: str`, `event_dict: EventDict`) and it returns an
  `EventDict` (boundary: contract-shape check, fails at registration otherwise).

## Acceptance criteria

- Tests pass.
- **Outcome-only role**: only the watch-list events are collected (`{test_name, key, result, desc}`);
  `git_state` and other non-watched events pass through to the console untouched (no git
  stateline in the table, no `self._git_state`). Failure events are collected **and** still
  printed — only `test_result` (the `suppress` set) is dropped.
- Exit-code semantics: a run with any FAIL/NA emits ≥1 `log.error` → harness exit 1; an
  all-PASS/SKIP run emits none → exit 0. This reproduces rtl_buddy's
  `exit_code |= 0 if is_pass() else 1` via the per-emission `log.error`, not an aggregator.
- The summary table content matches what `aggregate-results.finalise()` previously produced,
  with `test_name` as the first column (rtl_buddy parity) followed by `result`/`desc`.
- No `fan-in`/`agg` node exists in `graphs/test.yaml`, and there is **no** separate
  `drop_summary_events` entry; the `logging` block resolves `graphs/log/summary.py` to the
  single `SummaryProcessor` and renders on a normal and a deferred-`ERROR` run (not on CRITICAL).

## Constraints

- It is a structlog **processor** (a stateful class instance), **not** a `logging.Handler` — no
  `run()`, no ports, no module manifest entry. Instantiated once per run, so `self._rows` starts
  empty each run.
- Sits **before** `ConsoleRenderer` (non-terminal under `include_default: true`); `__call__`
  returns an `EventDict`, never a pre-rendered string.
- Collect the **Config watch-list** events (default: `test_result` + the failure-terminal events)
  — harvest `{test_name, key, result, desc}` into `self._rows` (`test_name` = the test's
  `get_name()`, the rendered first column). `raise DropEvent` only for events in the
  `suppress` set (default `["test_result"]`); return **every other** event (failure errors,
  `git_state`, module logs) unchanged. Do **not** hard-code the event names, keep a
  `self._git_state`, or render git state in the table.
- `finalise()` renders the table once; it is a **no-op when `self._rows` is empty** (list-mode /
  CRITICAL abort) and drives **no** exit code (the per-emission `log.error` does).
- Do **not** add a separate `drop_summary_events` processor — accumulation and suppression live
  in this one object.

## Notes

This uses the per-run processor-finalisation hook documented at
`docs/logger/implementation.md:95-99` (timing at `:165-167`; see
[07 item 27](../07-ambiguities-and-assumptions.md)). Adding a new
terminal-result source means **either** emitting `test_result` at
the new site (the parsers / `filter.skip` / `early-stop` pattern) **or** adding the site's own
event name to the `Config` watch-list (the failure-terminal pattern) — no edge change either way.
