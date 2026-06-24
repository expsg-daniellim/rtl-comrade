# Spec 10c: summary logging plugin (`SummaryProcessor`)

**Depends on:** spec 01 (schema), spec [10a](10a-early-stop-gate.md) / [10b](10b-git-status.md) (emit the `test_result` events this processor accumulates). Uses the **per-run processor-finalisation hook**: `App.cleanup` finalises the run's processors (then handlers), duck-typed, before the failure check and not on a `CRITICAL` exit (`docs/logger/implementation.md:95-99`, timing at `:165-167`).
**References:** [03 — Control section](../03-module-catalog.md), [05 — Re-convergence](../05-branching-and-results.md#re-convergence-the-summary-is-a-logging-concern-not-a-graph-node), [07 item 27](../07-ambiguities-and-assumptions.md), `docs/logger/implementation.md`, `docs/harness/logging.md`. Parent index: [idx-10 — Control module, git-status, and the summary logging plugin](../idx-10-control-aggregate.md).

## Goal

Implement the per-graph logging **processor** that accumulates the per-test outcome rows from a **`Config` watch-list of event names** (default `["test_result"]`; the list is configuration) and renders the summary table once, in its `finalise()` teardown hook. Its role is deliberately narrow: **collect the watch-list outcomes only.** `git_state` and every other non-watched event pass straight through to the console untouched; there is no git stateline in the table. The exit code is driven solely by the per-emission `log.error` at each failure site, not by this processor.

> **Filename note.** This file is named `10c-summary-handler.md` for link stability; the plugin is a structlog **processor** (`SummaryProcessor`), not a `logging.Handler`.

## Before you start

Read `docs/logger/implementation.md` (writing a structlog processor; the per-run finalisation hook) and the "Processors", "Suppressing events with `DropEvent`", "Per-Graph Custom Logging", and "`include_default` and the terminal renderer" sections of `docs/harness/logging.md`. The plugin is a **stateful processor class instance** in the harness handler's formatter chain — it sits **before** `ConsoleRenderer` (non-terminal under `include_default: true`), so `__call__` returns an `EventDict` and never sees a pre-rendered string. It is classified as a processor (not a handler) because it does not subclass `logging.Handler`; as a processor *class* it is instantiated once per run, so `self.rows` starts empty each run. This module **creates** `graphs/log/summary.py` and is its sole writer (spec [11](11-graph-and-manifests.md) only *wires* the plugin into the graph's `logging` block, it does not append to the file).

## Surface

Wiring surface and skeleton, mirrored from [05 — The `SummaryProcessor` logging plugin](../05-branching-and-results.md#the-summaryprocessor-logging-plugin) — that section is the design view, this is the build view; update both when behaviour changes. This is a structlog **processor**, not a graph module and not a `logging.Handler`: it has no `run()`, no ports, and no module manifest entry. In place of the module I/O block, the wiring surface below names what it accumulates, what it passes through, its teardown hook, and how it is registered.

```
plugin:         SummaryProcessor  (structlog processor class — stateful; NOT a logging.Handler)
chain position: harness handler's formatter chain, before ConsoleRenderer (include_default: true)
accumulates:    a Config watch-list of per-test outcome events (default: ["test_result"];
                the list is configuration) → {test_name,key,result,desc} appended to
                self.rows (test_name = the test's get_name(), the table's first column)
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
import re
import sys
from typing import Any
from collections.abc import MutableMapping
from serde import serde, field
from structlog.exceptions import DropEvent

VERDICT_COLOURS = {"PASS": "\033[1;92m", "FAIL": "\033[1;91m", "NA": "\033[1;93m"}  # SKIP left plain — rtl_buddy parity
COLOUR_END = "\033[0m"

def colourise(line: str) -> str:                  # mirror PassFailFormatter (rtl_buddy.py:52-60): wrap verdict tokens, SKIP uncoloured
    for tok, colour in VERDICT_COLOURS.items():
        line = re.sub(rf"\b{tok}\b", f"{colour}{tok}{COLOUR_END}", line)
    return line

class SummaryProcessor:
    @serde
    class Config:
        # watch-list of per-test outcome events to collect — default is just the universal `test_result`;
        # callers configure additional outcome events to watch. Do not bake a larger list in here.
        events: list[str] = field(default_factory=lambda: ["test_result"])
        # subset of `events` whose per-event console line is suppressed (summary-only rows)
        suppress: list[str] = field(default_factory=lambda: ["test_result"])

    def __init__(self, config):
        self.events = set(config.events)        # watch-list
        self.suppress = set(config.suppress)    # drop-from-console subset
        self.rows = []                          # fresh per run

    def __call__(self, logger, method_name: str,
                 event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
        name = event_dict.get("event")
        if name in self.events:
            self.rows.append({                  # harvest the row
                "test_name": event_dict.get("test_name"),   # summary's first column (rtl_buddy parity)
                "key": event_dict.get("key"),
                "result": event_dict.get("result"),
                "desc": event_dict.get("desc"),
            })
            if name in self.suppress:
                raise DropEvent                  # summary-only → no per-event console line
        return event_dict                        # non-watched events (incl. git_state, failure errors) flow on

    def finalise(self):                          # per-run teardown hook, at run end
        if not self.rows:                       # list-mode / CRITICAL abort → no-op
            return
        colour = sys.stdout.isatty()              # gate ANSI on a real terminal; plain text when piped/redirected
        lines = ["\nTest Results Summary"]
        for row in self.rows:                   # rtl_buddy.py:203-205 widths; None → 'NA' (test_results.py:23-27)
            line = f"{row['test_name'] or 'NA':<30} {row['result'] or 'NA':<8} {row['desc'] or 'NA':<30}"
            lines.append(colourise(line) if colour else line)
        print("\n".join(lines))                  # raw stdout; finalise runs out-of-band, after the formatter chain
```

It accumulates the **watch-list** events and nothing else. The failure events (`compile_failed`/`sim_timeout`/`*_failed`) are collected into rows but **not** suppressed, so they still print as errors on the console; only the summary-only `test_result` rows are `DropEvent`'d. `git_state` is not on the watch-list — the processor returns it unchanged, so it prints via `ConsoleRenderer` at run start like any other log line (no `self.git_state`, no git rendering here).

## Algorithm

`__call__(logger, method_name, event_dict)` — runs per log event, before `ConsoleRenderer`:
1. If `event_dict["event"]` is in the Config **watch-list** (`self.events`), harvest `{test_name, key, result, desc}` into `self.rows` (`test_name` = the test's `get_name()`, rendered as the summary's first column for rtl_buddy parity; `key` retained for correlation). If it is *also* in the `suppress` subset (default just `test_result`), `raise DropEvent` so its per-event console line is suppressed.
2. Otherwise return `event_dict` unchanged. Watched-but-unsuppressed events (the failure `log.error`s — `compile_failed` etc.) are both collected **and** returned, so they still print as errors; non-watched events, including `git_state`, fall straight through to `ConsoleRenderer`.

`finalise()` — the per-run teardown hook, invoked at run end (after the gather, before the failure check):
3. If `self.rows` is empty (list-mode, or a CRITICAL abort before any result), return — a no-op.
4. Otherwise render the `test_name`/`result`/`desc` table from `self.rows` (`test_name` first, parity with rtl_buddy's `test_name` column — `rtl_buddy.py:205`) and `print` it to stdout. Each row uses rtl_buddy's column widths (`{test_name:<30} {result:<8} {desc:<30}`, `rtl_buddy.py:205`), defaulting a missing field to `'NA'` (`test_results.py:23-27`). When `sys.stdout.isatty()`, wrap the `PASS`/`FAIL`/`NA` verdict tokens in ANSI via `colourise` (mirrors `PassFailFormatter`, `rtl_buddy.py:52-60`; `SKIP` stays plain); when piped or redirected, print plain text so no escape codes leak into the sink. It drives no exit code (that is the per-emission `log.error` at each failure site).

## Deliverables

In `graphs/log/summary.py` — a single `SummaryProcessor` class:

- A structlog processor (a **stateful class instance**; classified as a processor because it is not a `logging.Handler` subclass, and instantiated once per run so `self.rows` is fresh).
- A `Config` carries the **watch-list** `events` — the per-test outcome event names to collect — defaulting to **just `["test_result"]`** and configurable to watch further outcome events; do not bake a larger list into the default. A `suppress` subset (default `["test_result"]`) marks the summary-only rows. Each watched event must carry `test_name`/`key`/`result`/`desc` (`test_name` = the test's `get_name()`).
- `__call__` harvests `{test_name, key, result, desc}` from every watched event into `self.rows`; it raises `structlog.exceptions.DropEvent` only for events in `suppress` (the summary-only `test_result` rows), and returns **everything else unchanged** — so the failure `log.error`s, `git_state`, and all module logs still reach the console.
- `finalise()` (the per-run teardown hook the harness invokes at run end) renders the `test_name`/`result`/`desc` table from `self.rows` (first column `test_name`, parity with rtl_buddy's `test_name` column) and `print`s it to stdout. It colourises the `PASS`/`FAIL`/`NA` verdict tokens (via the module-level `colourise`, mirroring `PassFailFormatter`; `SKIP` stays plain) **only when `sys.stdout.isatty()`**, and prints plain text otherwise so no ANSI leaks into a pipe/redirect/CI log. It is a **no-op when `self.rows` is empty** (list-mode, or a CRITICAL abort before any result). It drives **no** exit code.

The single `SummaryProcessor` both accumulates the rows and suppresses the summary-only ones. The summary plugin's *only* job is to collect outcomes and render them once at the end.

Sketches in [05 — The `SummaryProcessor` logging plugin](../05-branching-and-results.md#the-summaryprocessor-logging-plugin).
**CRITICAL path**: on a `CRITICAL` record the harness exits before the per-run teardown runs, so `finalise()` is never reached and no table renders — acceptable, since no results exist then. On a normal or deferred-`ERROR` run the teardown runs (before the failure check) and the table renders.

**Compatibility source:** `rtl_buddy/src/rtl_buddy/rtl_buddy.py:203-207` — the `do_cmd_test` summary loop: the `"\nTest Results Summary\n"` header (`:203`), the per-row format `f"{test_name:<30} {result:<8} {desc:<30}"` (`:205`), the OR-accumulated exit this processor replaces (`:206`), and the `logger.result(result_string)` emit (`:207`) — a custom-level (25) dual-sink log that this processor reproduces out-of-graph as a single `print` to stdout. Verdict colourisation is ported from `PassFailFormatter.format` (`rtl_buddy.py:52-60`), which rtl_buddy gates on its `--colour` option (`:144`); here the equivalent gate is `sys.stdout.isatty()`.

`graphs/log/summary.py` is referenced by `path`/`name` in the `logging` block, not a manifest.

## Tests

`graphs/tests/test_summary.py` (or alongside the plugin). Fixtures: a fresh `SummaryProcessor(Config(...))` instance per test (default `Config` unless a case overrides the watch-list); hand-built `event_dict`s; `capsys` for the rendered table; `pytest.raises(DropEvent)` for the suppression cases. No graph/harness needed.

- Feed N `test_result` events (mix PASS/SKIP/FAIL/NA, each carrying `test_name`) through `__call__`, then `finalise()` → one table rendered with a `test_name`/`result`/`desc` row per event in arrival order (first column `test_name`).
- Colourisation gating (monkeypatch `sys.stdout.isatty`): with `isatty()` true, a FAIL/PASS/NA row's verdict token is ANSI-wrapped and `SKIP` is not; with `isatty()` false, the same rows render with no escape codes (boundary: TTY gate, parity with rtl_buddy's `--colour`).
- A missing field on a watched event → that column renders as `'NA'` (boundary: `None` defaulting, `test_results.py:23-27`).
- A watched **failure** event on a `Config(events=["test_result", "compile_failed"])` instance (a `compile_failed` carrying `test_name`/`key`/`result`/`desc`) → a row is appended **and** the event is returned unchanged (no `DropEvent`), so it still reaches the console (boundary: collected-but-not-suppressed, and the failure name is watch-listed via config — not a plugin default).
- No events fed → `finalise()` is a no-op, renders nothing (boundary: list-mode / CRITICAL abort before any result).
- `__call__` on a `test_result` event → `raise DropEvent` and `self.rows` grows by one (row accumulated, console line suppressed — `test_result` is in the default `suppress` set).
- `__call__` on a non-watched event (e.g. `git_state`, an arbitrary module log) → returns the `event_dict` unchanged, no `DropEvent` (so it survives to `ConsoleRenderer`); no `self.git_state` is kept.
- Config-driven watch-list: a `Config(events=["only_this"], suppress=[])` instance collects `only_this` events, drops nothing, and ignores `test_result` (boundary: the watch-list and suppress set are config, not hard-coded).
- State persists across calls on one instance: K watched calls then `finalise()` → renders K rows (accumulation is run-long, instance-held).
- The `__call__` signature satisfies the strict processor contract: three positional params after `self` (`logger`, `method_name: str`, `event_dict: EventDict`) and it returns an `EventDict` (boundary: contract-shape check, fails at registration otherwise).

## Acceptance criteria

- Tests pass.
- **Outcome-only role**: only the watch-list events are collected (`{test_name, key, result, desc}`); `git_state` and other non-watched events pass through to the console untouched (no git stateline in the table, no `self.git_state`). Failure events are collected **and** still printed — only `test_result` (the `suppress` set) is dropped.
- Exit-code semantics: a run with any FAIL/NA emits ≥1 `log.error` → harness exit 1; an all-PASS/SKIP run emits none → exit 0. This reproduces rtl_buddy's `exit_code |= 0 if is_pass() else 1` via the per-emission `log.error`, not an aggregator.
- The summary table renders `test_name` as the first column (rtl_buddy parity) followed by `result`/`desc`, with a missing field shown as `'NA'`.
- Verdict colourisation (rtl_buddy parity): on a TTY the `PASS`/`FAIL`/`NA` tokens are ANSI-wrapped (`SKIP` plain); when stdout is not a TTY the table prints with no escape codes.
- The `logging` block resolves `graphs/log/summary.py` to the single `SummaryProcessor`, which renders on a normal and a deferred-`ERROR` run (not on CRITICAL).

## Constraints

- It is a structlog **processor** (a stateful class instance), **not** a `logging.Handler` — no `run()`, no ports, no module manifest entry. Instantiated once per run, so `self.rows` starts empty each run.
- Sits **before** `ConsoleRenderer` (non-terminal under `include_default: true`); `__call__` returns an `EventDict`, never a pre-rendered string.
- Collect the **Config watch-list** events (default `["test_result"]`, configurable) — harvest `{test_name, key, result, desc}` into `self.rows` (`test_name` = the test's `get_name()`, the rendered first column). `raise DropEvent` only for events in the `suppress` set (default `["test_result"]`); return **every other** event (failure errors, `git_state`, module logs) unchanged. Do **not** bake a larger watch-list into the default, keep a `self.git_state`, or render git state in the table.
- `finalise()` renders the table once; it is a **no-op when `self.rows` is empty** (list-mode / CRITICAL abort) and drives **no** exit code (the per-emission `log.error` does).
- Keep accumulation and suppression in the one `SummaryProcessor` object — do not split them across two processors.

## Notes

This uses the per-run processor-finalisation hook documented at `docs/logger/implementation.md:95-99` (timing at `:165-167`; see [07 item 27](../07-ambiguities-and-assumptions.md)).

The watch-list (`events`) and the suppressed subset (`suppress`) are both `Config`; the plugin hard-codes neither and defaults to the single universal `test_result`. Watching further outcome events is therefore a configuration change, not a code change in this file.
