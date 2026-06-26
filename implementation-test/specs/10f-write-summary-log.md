# Spec 10f: summary log-file sink (`WriteSummaryLogMod`)

**Depends on:** spec [10d](10d-summarise-results.md) (creates `modules/rtl_buddy/summarise_results.py` and emits the `table` string this node writes).
**References:** [10d](10d-summarise-results.md), [06 — graph YAML](../06-graph-yaml.md), `docs/modules/implementation.md` (config-bearing modules, `{graph}`-relative `Path` config, the exhaustive file-I/O exception rule), `modules/io.py` (`FileReadMod`, the file-I/O example). Parent index: [idx-10 — Control module, git-status, and the summary node](../idx-10-control-aggregate.md).

## Before you start

Read `docs/modules/implementation.md` — config-bearing modules (a nested `@serde Config` deserialised and passed as `config=`), `Path` config fields and `{graph}`-relative resolution, and the **exhaustive exception-handling** rule for file I/O (walk every line, catch what it can raise, never escape `run(...)`). `modules/io.py` `FileReadMod` is the file-I/O reference. This is one of three plugins in `modules/rtl_buddy/summarise_results.py`: [10d](10d-summarise-results.md) `SummariseResultsMod` **creates** the file and opens the manifest block, this spec and [10e](10e-print-summary.md) **append**.

## Goal

The **file sink** for the summary table. It consumes the one plain `table` string `results-summary` emits ([10d](10d-summarise-results.md)) and writes it to `rtl_buddy.log` — **plain, never colourised** — reproducing the file half of rtl_buddy's `logger.result` dual-sink (the `rtl_buddy.log` `FileHandler` with the plain `file_formatter`, always uncoloured regardless of `--colour`, `rtl_buddy.py:139-148`). The console half is [10e](10e-print-summary.md). It does one thing — write the received table to the configured log path — and reads nothing from `TestResult`: the table arrives fully rendered from [10d](10d-summarise-results.md).

## Surface

```
module:   write-summary-log  (WriteSummaryLogMod)  — config-bearing, stateless file sink
contract: default  (single input; fires once on the one table delivery, then ends)
inputs:   table: str  — the rendered plain summary table from results-summary (10d)
outputs:  none
config:   log_path: Path = rtl_buddy.log   ({graph}-relative; defaults to rtl_buddy.log in the CWD, matching rtl_buddy)
```

```python
# modules/rtl_buddy/summarise_results.py  (appended; 10d creates the file)
from __future__ import annotations
from pathlib import Path
from serde import serde
import structlog

log = structlog.get_logger()

class WriteSummaryLogMod:
    @serde
    class Config:
        log_path: Path = Path("rtl_buddy.log")    # rtl_buddy opens this mode='w' once per run (rtl_buddy.py:139)

    def __init__(self, config):
        self.log_path = config.log_path

    def run(self, table):                          # one delivery: the plain table from results-summary (10d)
        try:
            with open(self.log_path, "w", encoding="utf-8") as f:   # truncate per run; plain, never ANSI (file_formatter, :145)
                f.write(table + "\n")
        except OSError as e:
            log.error("summary_log_write_failed", path=str(self.log_path), err=e.strerror, errno=e.errno)  # a run-level problem → deferred exit
```

`WriteSummaryLogMod` is **config-bearing**: `Config.log_path` is a `Path` (so it accepts a `{graph}`-relative value), defaulting to `rtl_buddy.log` — a CWD-relative path matching where rtl_buddy writes its log. It writes the received table **verbatim plus one trailing newline**, always plain, and reads no `TestResult`.

## Algorithm

`run(self, table)` — runs once, on the single `table` delivery the default contract hands it:
1. Open `self.log_path` in mode `"w"` (truncate per run — rtl_buddy opens `rtl_buddy.log` with `mode='w'` once per invocation, `rtl_buddy.py:139`).
2. Write the received `table` string plus one trailing newline. Plain — never colourise (rtl_buddy's `file_formatter` is the plain formatter regardless of `--colour`, `:145`).
3. Catch `OSError` (covering `FileNotFoundError`/`PermissionError`/`IsADirectoryError` and the rest) → `log.error("summary_log_write_failed", path, err, errno)`; never let it escape. A failed log write is a **deferred-exit driver**: the exit code reports whether the run as a whole hit a problem (it is *not* the test pass/fail verdict — that is the summary's job), and being unable to write `rtl_buddy.log` is such a problem, so it flips `handler.failure` → exit 1 like any other run-level fault. The run still continues (best-effort, and the summary already reached the console via [10e](10e-print-summary.md)). No output port.

## Deliverables

In `modules/rtl_buddy/summarise_results.py` (appended) — `WriteSummaryLogMod`:

- A config-bearing stateless file sink: a nested `@serde Config` with `log_path: Path = Path("rtl_buddy.log")`; `__init__(self, config)` stores it; `run(self, table)` writes the received table (plain, plus one trailing newline) to `log_path`, truncating per run; **no** output ports.
- Exhaustive file-I/O exception handling: catch `OSError` around the open/write and emit `log.error("summary_log_write_failed", path, err, errno)`; the exception never escapes `run(...)`. A write failure is a run-level problem, so it **flips the run's failure flag** (deferred exit 1) — it does not, however, abort the run.

**Manifest** — append to the `rtl_buddy/summarise_results.py` block [10d](10d-summarise-results.md) opens:

```yaml
  - { name: write-summary-log, class_name: WriteSummaryLogMod }
```

**Compatibility source:** `rtl_buddy/src/rtl_buddy/rtl_buddy.py:139-148` — the `rtl_buddy.log` `FileHandler(mode='w')` and its plain `file_formatter` (always uncoloured, regardless of `--colour`). The summary lands in that file because `logger.result` (`:207`, level `RESULT`=25) clears the file handler's `INFO` threshold (`:140`). This node reproduces the **plain file write** of the summary. Note: rtl_buddy's `rtl_buddy.log` holds the **whole** `INFO`+ run log (banner, git rev, status, the summary, …); this node writes **only** the summary table. Making `rtl_buddy.log` the full run log is a separate harness-logging concern, out of scope here.

### Node + wiring (lands in spec [06](../06-graph-yaml.md) / `graphs/test.yaml`)

```yaml
- { id: write-summary-log, module: write-summary-log, contract: default }   # rtl_buddy.log sink for the summary table
```

- One input edge: `results-summary.table` → `write-summary-log.table` ([10d](10d-summarise-results.md) emits `table` from `finalise()`).
- `default` (not `unit`): the node fires once on the one table delivery, then drains `EndSentinel` silently; on a no-result run [10d](10d-summarise-results.md) emits nothing, so this node simply never fires (no empty `rtl_buddy.log` is written).
- `config` is optional — `log_path` defaults to `rtl_buddy.log` in the CWD (rtl_buddy parity); a graph may override it with a `{graph}`-relative path.

## Tests

`modules/tests/test_summarise_results.py` (shared with [10d](10d-summarise-results.md)/[10e](10e-print-summary.md)), driven by `run_module_scenario` (`docs/modules/testing.md`). Fixtures: hand-built plain table strings; `tmp_path` for `log_path`; `logging_handler` (with its `.failure` flag) for the warning path.

- `run(table)` with `Config(log_path=tmp_path/"rtl_buddy.log")` → the file contains exactly the table plus one trailing newline, plain (assert no ANSI escape codes present).
- A table that already contains verdict tokens → written verbatim (the file sink never colourises — the file is always plain).
- Truncate-per-run: two `run` calls (fresh instance each, matching per-run construction) writing to the same path → the file holds only the most recent table (mode `"w"`).
- Write failure: a `log_path` that cannot be written (e.g. pointing at a directory) → `log.error("summary_log_write_failed", …)`, no exception escapes, and `logging_handler.failure is True` (boundary: a run-level fault is a deferred-exit driver; the call still returns rather than raising).

## Acceptance criteria

- Tests pass.
- `write-summary-log` → `WriteSummaryLogMod` resolves from `modules/config.yaml`; `Config.log_path` defaults to `rtl_buddy.log`.
- The received table is written **plain** (no ANSI) to `log_path`, truncated per run, with one trailing newline.
- A write `OSError` is caught and logged at `ERROR` (`summary_log_write_failed`), never raised; it **flips the run's failure flag** (deferred exit 1) without aborting the run.
- The node loads and the `results-summary.table` → `write-summary-log.table` edge validates (cross-cutting wiring exercised in [spec 11](11-graph-and-manifests.md) / [12](12-end-to-end.md)).

## Constraints

- Config-bearing (`log_path: Path`, `{graph}`-relative), stateless, **no** output ports — a pure file sink.
- Write the received table string **verbatim** (plus one trailing newline); never colourise, re-render rows, or read `TestResult` fields — it receives the finished plain table from [10d](10d-summarise-results.md).
- Truncate per run (mode `"w"`) for rtl_buddy parity. Catch all `OSError` (file I/O is the module's responsibility per `docs/modules/implementation.md`); a write failure is a run-level fault → `log.error` (a deferred-exit driver, since the exit code tracks run problems rather than the test verdict), and must not escape `run(...)` or abort the run.

## Notes

Atomic file sink: one node, one responsibility. Pairs with the console sink [10e](10e-print-summary.md). This writes only the summary table to `rtl_buddy.log`; making `rtl_buddy.log` the full `INFO`+ run log (as upstream) is a separate harness-logging change beyond this node.
