# Spec 10c: summary logging plugin (`SummaryProcessor`)

**Depends on:** spec 01 (schema), spec [10a](10a-early-stop-gate.md) /
[10b](10b-git-status.md) (emit the `test_result` events this processor accumulates). Relies on
the **per-run processor-finalisation hook** (see [07 item 27](../07-ambiguities-and-assumptions.md));
assumed available. No dependency on spec 02 — the `fan-in-results` relay was removed by
TODO #15.
**References:** [03 — Control section](../03-module-catalog.md),
[05 — Re-convergence](../05-branching-and-results.md#re-convergence-the-summary-is-a-logging-concern-not-a-graph-node),
[07 item 27](../07-ambiguities-and-assumptions.md), `docs/logger/implementation.md`,
`docs/harness/logging.md`. Parent index:
[10 — Control module, git-status, and the summary logging plugin](10-control-aggregate-modules.md).

## Goal

Implement the per-graph logging **processor** that accumulates the per-test `test_result`
rows and renders the summary table once, in its `finalise()` teardown hook — replacing the
removed `aggregate-results` sink (TODO #15). Its role is deliberately narrow: **accumulate
results only.** `git_state` and every other log event pass straight through to the console
untouched; there is no git stateline in the table. The exit code is driven solely by the
per-emission `log.error` at each failure site, not by this processor.

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
starts empty each run.

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
accumulates:    test_result        (results only → appended to self._rows, then DropEvent'd)
passes through: every other event, incl. git_state → ConsoleRenderer (returned unchanged)
teardown hook:  finalise()  — invoked per-run at run end (after the gather, before failure check)
registration:   logging block in graphs/test.yaml by path/name  (NOT a module manifest)
exit code:      none  (driven per-emission by log.error at each failure site)
```

```python
# graphs/log/summary.py
from __future__ import annotations
from typing import Any
from collections.abc import MutableMapping
from structlog.exceptions import DropEvent

class SummaryProcessor:
    def __init__(self):
        self._rows = []                          # results only; fresh per run

    def __call__(self, logger, method_name: str,
                 event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
        if event_dict.get("event") == "test_result":
            self._rows.append(event_dict)        # accumulate the row
            raise DropEvent                      # suppress the per-event console line
        return event_dict                        # everything else (incl. git_state) falls through

    def finalise(self):                          # per-run teardown hook, at run end
        if not self._rows:                       # list-mode / CRITICAL abort → no-op
            return
        ...                                      # render the key/result/desc table
```

It accumulates `test_result` and **nothing else**. `git_state` is an ordinary event the
processor returns unchanged, so it prints via `ConsoleRenderer` at run start like any other
log line — there is no `self._git_state` and no git rendering here.

## Algorithm

`__call__(logger, method_name, event_dict)` — runs per log event, before `ConsoleRenderer`:
1. If `event_dict.get("event") == "test_result"`, append the dict to `self._rows` and `raise
   DropEvent` so the per-event line is suppressed from the console.
2. Otherwise return `event_dict` unchanged — every other event, including `git_state`, falls
   through to `ConsoleRenderer`.

`finalise()` — the per-run teardown hook, invoked at run end (after the gather, before the
failure check):
3. If `self._rows` is empty (list-mode, or a CRITICAL abort before any result), return — a
   no-op.
4. Otherwise render the `key`/`result`/`desc` table from `self._rows`. It drives no exit code
   (that is the per-emission `log.error` at each failure site).

## Deliverables

In `graphs/log/summary.py` — a single `SummaryProcessor` class:

- A structlog processor (a **stateful class instance**; classified as a processor because it
  is not a `logging.Handler` subclass, and instantiated once per run so `self._rows` is fresh).
- `__call__` appends every `test_result` event to `self._rows` and raises
  `structlog.exceptions.DropEvent` (so the harness handler does not also print the per-event
  line). It returns **every other event unchanged**, so `git_state` and all module logs reach
  the console normally.
- `finalise()` (the per-run teardown hook the harness invokes at run end) renders the
  `key`/`result`/`desc` table from `self._rows`. It is a **no-op when `self._rows` is empty**
  (list-mode, or a CRITICAL abort before any result). It drives **no** exit code.

There is **no** separate `drop_summary_events` processor: the single `SummaryProcessor` both
accumulates the row and drops it from the console. The summary plugin's *only* job is to
collect results and render them once at the end.

Sketches in [05 — The `SummaryProcessor` logging plugin](../05-branching-and-results.md#the-summaryprocessor-logging-plugin).
**CRITICAL path**: on a `CRITICAL` record the harness exits before the per-run teardown runs,
so `finalise()` is never reached and no table renders — acceptable, since no results exist
then. On a normal or deferred-`ERROR` run the teardown runs (before the failure check) and the
table renders.

**Compatibility source:** `rtl_buddy/src/rtl_buddy/rtl_buddy.py:203-207` — the `do_cmd_test` summary loop (`f"{test_name:<30} {result:<8} {desc:<30}"`) that this processor reproduces out-of-graph; the OR-accumulated exit it replaces is `rtl_buddy.py:206`.

`graphs/log/summary.py` is referenced by `path`/`name` in the `logging` block, not a manifest.

## Tests

`graphs/tests/test_summary.py` (or alongside the plugin):

- feeding N `test_result` events (mix of PASS/SKIP/FAIL/NA) into one instance → `finalise()`
  renders one table; empty input → `finalise()` is a no-op.
- `__call__` raises `DropEvent` on `test_result`, and returns every other event — including
  `git_state` — unchanged (so they survive to the console).
- accumulation is held on the instance and survives across `__call__` invocations (state
  persists run-long).
- the `__call__` signature satisfies the strict processor contract (three positional params
  with `self` dropped; `method_name: str`; `event_dict` an `EventDict`; returns an `EventDict`).

## Acceptance criteria

- Tests pass.
- **Results-only role**: only `test_result` rows are collected; `git_state` and all other
  events pass through to the console untouched (no git stateline in the table, no
  `self._git_state`).
- Exit-code semantics: a run with any FAIL/NA emits ≥1 `log.error` → harness exit 1; an
  all-PASS/SKIP run emits none → exit 0. This reproduces rtl_buddy's
  `exit_code |= 0 if is_pass() else 1` via the per-emission `log.error`, not an aggregator.
- The summary table content matches what `aggregate-results.finalise()` previously produced
  (same `key`/`result`/`desc` columns).
- No `fan-in`/`agg` node exists in `graphs/test.yaml`, and there is **no** separate
  `drop_summary_events` entry; the `logging` block resolves `graphs/log/summary.py` to the
  single `SummaryProcessor` and renders on a normal and a deferred-`ERROR` run (not on CRITICAL).

## Constraints

- It is a structlog **processor** (a stateful class instance), **not** a `logging.Handler` — no
  `run()`, no ports, no module manifest entry. Instantiated once per run, so `self._rows` starts
  empty each run.
- Sits **before** `ConsoleRenderer` (non-terminal under `include_default: true`); `__call__`
  returns an `EventDict`, never a pre-rendered string.
- Accumulate `test_result` **only** — append the row then `raise DropEvent` to suppress its
  console line. Return **every other** event (including `git_state`) unchanged. Do **not** keep a
  `self._git_state` or render git state in the table.
- `finalise()` renders the table once; it is a **no-op when `self._rows` is empty** (list-mode /
  CRITICAL abort) and drives **no** exit code (the per-emission `log.error` does).
- Do **not** add a separate `drop_summary_events` processor — accumulation and suppression live
  in this one object.

## Notes

This relies on the per-run processor-finalisation hook (the assume-closed harness gap recorded
in [07 item 27](../07-ambiguities-and-assumptions.md)). Adding a new terminal-result source
means adding one `log.info("test_result", ...)` call at the new site — no edge, no plugin
change.
