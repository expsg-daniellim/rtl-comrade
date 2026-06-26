# Spec 10e: summary console sink (`PrintSummaryMod`)

**Depends on:** spec [10d](10d-summarise-results.md) (creates `modules/rtl_buddy/summarise_results.py` and emits the `table` string this node prints).
**References:** [10d](10d-summarise-results.md), [10c](10c-summary-handler.md) (shared verdict-colourisation parity), [06 — graph YAML](../06-graph-yaml.md), `docs/modules/implementation.md`, `modules/io.py` (`StdoutMod`, the config-less stdout sink). Parent index: [idx-10 — Control module, git-status, and the summary node](../idx-10-control-aggregate.md).

## Before you start

Read `docs/modules/implementation.md` — config-less modules (constructed with no args), the single-input `run(...)` shape, and `modules/io.py` `StdoutMod` (the minimal `run(self, a): print(a)` console sink this generalises). This is one of three plugins in `modules/rtl_buddy/summarise_results.py`: [10d](10d-summarise-results.md) `SummariseResultsMod` **creates** the file and opens the manifest block, this spec and [10f](10f-write-summary-log.md) **append**.

## Goal

The **console sink** for the summary table. It consumes the one plain `table` string `results-summary` emits ([10d](10d-summarise-results.md)) and prints it to stdout, colourising the `PASS`/`FAIL`/`NA` verdict tokens when stdout is a TTY (the `PassFailFormatter` parity, gated on `sys.stdout.isatty()`) and printing plain text otherwise so no escape codes leak into a pipe/redirect/CI log. This is the **colour half** of rtl_buddy's `logger.result` dual-sink (the console `PassFailFormatter`, gated on `--colour`, `rtl_buddy.py:144`); the plain file half is [10f](10f-write-summary-log.md). It does one thing — print the received table, colourised on a TTY — and reads nothing from `TestResult`: the table arrives fully rendered from [10d](10d-summarise-results.md).

## Surface

```
module:   print-summary  (PrintSummaryMod)  — config-less, stateless console sink
contract: default  (single input; fires once on the one table delivery, then ends)
inputs:   table: str  — the rendered plain summary table from results-summary (10d)
outputs:  none
```

```python
# modules/rtl_buddy/summarise_results.py  (appended; 10d creates the file)
from __future__ import annotations
import re
import sys

VERDICT_COLOURS = {"PASS": "\033[1;92m", "FAIL": "\033[1;91m", "NA": "\033[1;93m"}  # SKIP left plain — rtl_buddy parity
COLOUR_END = "\033[0m"

def colourise(text: str) -> str:                  # mirror PassFailFormatter (rtl_buddy.py:52-60): wrap verdict tokens, SKIP uncoloured
    for tok, colour in VERDICT_COLOURS.items():
        text = re.sub(rf"\b{tok}\b", f"{colour}{tok}{COLOUR_END}", text)
    return text

class PrintSummaryMod:
    def run(self, table):                         # one delivery: the plain table from results-summary (10d)
        print(colourise(table) if sys.stdout.isatty() else table)
```

`PrintSummaryMod` is **config-less** (no `Config`, no `config` parameter on `__init__`). `colourise` and `VERDICT_COLOURS` move here from the pre-split [10d](10d-summarise-results.md) — this is their sole home. It colourises the **whole** received string (one regex pass over the table, the way `PassFailFormatter.format` regexes the whole message), never per-field, and reads no `TestResult`: it receives the finished plain table.

## Algorithm

`run(self, table)` — runs once, on the single `table` delivery the default contract hands it:
1. If `sys.stdout.isatty()`, wrap the `PASS`/`FAIL`/`NA` verdict tokens in ANSI via `colourise` (`SKIP` stays plain); otherwise leave the table plain.
2. `print` the result to stdout. No output port.

## Deliverables

In `modules/rtl_buddy/summarise_results.py` (appended) — `PrintSummaryMod`:

- A config-less stateless console sink: `run(self, table)` prints the received table, colourising the `PASS`/`FAIL`/`NA` verdict tokens **only when `sys.stdout.isatty()`** and printing plain text otherwise; **no** output ports.
- Module-level `colourise(text)` + `VERDICT_COLOURS` (mirroring `PassFailFormatter`; `SKIP` left plain), operating on the whole table string. These move here from the pre-split [10d](10d-summarise-results.md).

**Manifest** — append to the `rtl_buddy/summarise_results.py` block [10d](10d-summarise-results.md) opens:

```yaml
  - { name: print-summary, class_name: PrintSummaryMod }
```

**Compatibility source:** `rtl_buddy/src/rtl_buddy/rtl_buddy.py:52-60` — `PassFailFormatter.format`, the verdict-token regex (`PASS`/`FAIL`/`NA` wrapped, `SKIP` left plain). rtl_buddy gates this on its `--colour` option (`:144`); here the equivalent gate is `sys.stdout.isatty()`. This is the **console handler** half of the `logger.result` dual-sink (`:135-146`); the file half is [10f](10f-write-summary-log.md).

### Node + wiring (lands in spec [06](../06-graph-yaml.md) / `graphs/test.yaml`)

```yaml
- { id: print-summary, module: print-summary, contract: default }   # console sink for the summary table
```

- One input edge: `results-summary.table` → `print-summary.table` ([10d](10d-summarise-results.md) emits `table` from `finalise()`).
- `default` (not `unit`): the node fires once on the one table delivery, then drains `EndSentinel` silently; on a no-result run [10d](10d-summarise-results.md) emits nothing, so this node simply never fires.

## Tests

`modules/tests/test_summarise_results.py` (shared with [10d](10d-summarise-results.md)/[10f](10f-write-summary-log.md)), driven by `run_module_scenario` (`docs/modules/testing.md`). Fixtures: hand-built plain table strings; `capsys` for stdout; `monkeypatch` for `sys.stdout.isatty`.

- `isatty()` true: a table containing `FAIL`/`PASS`/`NA` rows → printed with those verdict tokens ANSI-wrapped and `SKIP` left plain (boundary: TTY colourisation, parity with rtl_buddy `--colour`).
- `isatty()` false: the same table → printed with **no** escape codes (boundary: piped/redirected/CI — plain output).
- The printed text, modulo the wrapped verdict tokens, matches the input table byte-for-byte (the sink renders nothing of its own — it prints what it receives).

## Acceptance criteria

- Tests pass.
- `print-summary` → `PrintSummaryMod` resolves from `modules/config.yaml`.
- On a TTY the `PASS`/`FAIL`/`NA` tokens are ANSI-wrapped (`SKIP` plain); off a TTY the table prints with no escape codes.
- The node loads and the `results-summary.table` → `print-summary.table` edge validates (cross-cutting wiring exercised in [spec 11](11-graph-and-manifests.md) / [12](12-end-to-end.md)).

## Constraints

- Config-less, stateless, **no** output ports — a pure console sink.
- Colourise the **whole** received string (one regex pass, `SKIP` plain), gated strictly on `sys.stdout.isatty()`. Do **not** re-render rows, read `TestResult` fields, or change the table content — it receives the finished plain table from [10d](10d-summarise-results.md) and only prints (colourised on a TTY).
- Drives **no** exit code.

## Notes

Atomic console sink: one node, one responsibility. Pairs with the file sink [10f](10f-write-summary-log.md). Together, fanned from `results-summary.table`, they reproduce rtl_buddy's `logger.result` two-handler fan-out (console colourised + log file plain) as two explicit graph nodes.
