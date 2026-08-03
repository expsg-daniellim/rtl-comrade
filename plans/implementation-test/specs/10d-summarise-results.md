# Spec 10d: in-graph results summary node (`SummariseResultsMod`)

**Depends on:** spec 01 (schema — `TestResult`, now carrying `test_name`), spec [02](02-any-contract-and-fan-in.md) (the `any` contract this node wires).
**References:** [02 — payload conventions](../02-payload-conventions.md), [05 — Re-convergence](../05-branching-and-results.md#re-convergence-the-summary-returns-as-a-graph-node), [06 — graph YAML](../06-graph-yaml.md), [10c](10c-summary-handler.md) (the retired logging-plugin form, shared table-render parity), [10e](10e-print-summary.md) / [10f](10f-write-summary-log.md) (the two downstream summary sinks that consume this node's `table`), `docs/modules/implementation.md`, `docs/harness_configs/graph.md`. Parent index: [idx-10 — Control module, git-status, and the summary node](../idx-10-control-aggregate.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)` signature, the `finalise()` per-run teardown hook (which may **emit** outputs, in the same forms as `run(...)`, forwarded downstream before `EndSentinel` propagates), and config-bearing vs config-less modules. Read the **Contract port mappings** section of `docs/harness_configs/graph.md` and [spec 02](02-any-contract-and-fan-in.md) / `contracts/any.py` for the `any` contract's n→1 `mapping` mode and how a node declares the contract-port surface that differs from the module signature. This module shares `modules/rtl_buddy/summarise_results.py` with the two summary sinks ([10e](10e-print-summary.md) `PrintSummaryMod`, [10f](10f-write-summary-log.md) `WriteSummaryLogMod`); this spec **creates** that file and opens its manifest block, and the sink specs append to both.

## Goal

Render the per-test results table **inside the graph** and **emit it as one value** on a single output port. The 13 terminal `TestResult` ports — emitted but left unwired since the TODO #15 redesign ([05](../05-branching-and-results.md)) — are fanned into a single accumulating node via the **`any` contract** ([02](02-any-contract-and-fan-in.md)); from its `finalise()` teardown hook the node renders the consolidated PASS/FAIL/NA table and **emits it on a single `table` output port**. The data path is a visible edge fan-in **and** a visible edge fan-out, not a scrape of the logging chain and not a print buried in the summary node.

Atomicity: this node does one thing — **accumulate the fanned-in `TestResult`s and emit the rendered table.** It does not print, colourise, gate on a TTY, or write a file (those are handled downstream). It binds three separable concerns; keep them separate.

- **Module — the work.** `SummariseResultsMod` consumes **one `TestResult` per invocation** (`result`), appends it to an instance list, renders the **plain** table from `finalise()` and emits it on `table`, and there emits one consolidated `log.error("test_failures", count=…)` if the table holds any FAIL row. Graph-agnostic: it neither knows nor cares that many sources feed it or that two sinks consume it.
- **Contract — the scheduling.** The **`any` contract** owns the 13-way fan-in: fire on whichever terminal stream is ready, one delivery at a time, end once all have ended. `contract_config: { mapping: result }` (its n→1 string mode) resolves every input port's output to `result`, so each `get_inputs()` returns `{result: <one TestResult>}` and the module is handed exactly one result per call.
- **Node — the binding + ports.** The node's input surface is the **13 contract ports** (the edge destinations), declared on the node via **`contract_port_mappings`** (each → `[result]`), distinct from the module's single `run(...)` parameter; its output surface is the **single `table` port**.

## Surface

I/O surface and skeleton. This is a graph **module** with a `finalise()` teardown hook that renders and **emits** the table — **not** a pure sink. The `run(...)` signature is a clean, definite single parameter; the 13-port fan-in surface is declared on the **node** (`contract_port_mappings`), not inferred from the signature; the single `table` output port is emitted from `finalise()`.

```
module:            summarise-results  (SummariseResultsMod)  — config-less, stateful (run-long self.rows)
contract:          any   (contract_config: { mapping: result })  — n→1 fan-in onto the `result` output port
node input ports:  13 contract ports (edge destinations), declared via contract_port_mappings, each → [result]
node output port:  table — the rendered plain summary table, emitted once from finalise()
inputs (run):      result: TestResult   — one delivery per invocation (the any contract's output port)
outputs:           table: str   — the plain (never colourised) summary table; None / nothing emitted when there are no rows
teardown hook:     finalise()  — renders the plain table once at run end, emits it on `table`, then log.error("test_failures", count) if any FAIL row
exit code:         a consolidated log.error("test_failures") on any FAIL row (additional to each failure terminal's own per-case log.error)
```

```python
# modules/rtl_buddy/summarise_results.py
from __future__ import annotations
import structlog

log = structlog.get_logger()

class SummariseResultsMod:
    def __init__(self):
        self.rows = []                            # one TestResult per invocation; run-long, fresh per run

    def run(self, result):                        # the any contract delivers one TestResult under `result`
        self.rows.append(result)

    def finalise(self):                           # per-run teardown hook, at run end
        if len(self.rows) == 0:                   # list-mode / CRITICAL abort → emit nothing
            return None
        lines = ["\nTest Results Summary"]
        for r in self.rows:                       # rtl_buddy.py:203-205 widths; None → 'NA' (test_results.py:23-27)
            lines.append(f"{r.test_name or 'NA':<30} {r.result or 'NA':<8} {r.desc or 'NA':<30}")
        table = "\n".join(lines)                  # plain text — never colourised here
        n_fail = sum(1 for r in self.rows if r.result == "FAIL")
        if n_fail > 0:                            # consolidated summary signal → drives the exit (handler.failure)
            log.error("test_failures", count=n_fail)
        return ("table", table)                   # emit the plain table on the `table` port
```

`SummariseResultsMod` is **config-less** (no `Config`, no `config` parameter on `__init__`), so the harness constructs it with no args (`has_config` keys off the `__init__` signature — `module.py:53`); `self.rows` is fresh each run. It reads `TestResult` fields directly (`r.test_name`/`r.result`/`r.desc`) — no event-dict scraping. It renders **plain** text and **emits** it; it never colourises, prints, gates on `sys.stdout.isatty()`, or writes a file. The module never references the contract, the 13 edges, the downstream sinks, or the graph.

## Algorithm

`run(self, result)` — runs once per delivery the `any` contract hands it:
1. Append `result` (one `TestResult`) to `self.rows`. No output, no logging.

`finalise(self)` — the per-run teardown hook, invoked at run end (after the gather, before the failure check):
2. If `self.rows` is empty (list-mode, or a CRITICAL abort before any result), return `None` — emit nothing, so the sinks receive only `EndSentinel` and do nothing.
3. Render the `test_name`/`result`/`desc` table from `self.rows` in arrival order (`test_name` first, parity with rtl_buddy's `test_name` column — `rtl_buddy.py:205`) as **plain** text. Each row uses rtl_buddy's column widths (`{test_name:<30} {result:<8} {desc:<30}`, `rtl_buddy.py:205`), defaulting a missing field to `'NA'` (`test_results.py:23-27`). No colour, no TTY gate — the rendered string is plain regardless of where it ends up.
4. **Drive the consolidated exit signal.** Count the FAIL rows (`r.result == "FAIL"`); if any, emit one `log.error("test_failures", count=n_fail)`. This is the **summary-level** exit driver — distinct from, and additional to, each failure terminal's own per-case `log.error` (which carries the rich domain context at origin). `NA` rows are **not** counted here: a genuine `NA` from `parse-log`/`parse-uvm-log` drives the exit through *its* per-case `log.error` at origin, while an `early-stop` `NA` deliberately drives **no** error (the exit-0 divergence). `SKIP`/`PASS` rows never count.
5. **Emit the table.** Return `("table", table)` — one delivery on the `table` port. The emit happens whether or not there were FAIL rows (the `log.error` in step 4 is additional, not an alternative).

The 13-way fan-in and one-at-a-time delivery are the **`any` contract's** responsibility, fully specified and tested in [spec 02](02-any-contract-and-fan-in.md) — this node reuses it and adds no contract code. Because `any` returns exactly one single-key dict per call, the module sees one `TestResult` per `run`, never a batch.

## Deliverables

In `modules/rtl_buddy/summarise_results.py` — `SummariseResultsMod`:

- A config-less stateful module: `__init__(self)` seeds `self.rows = []`; `run(self, result)` appends the one delivered `TestResult`; `finalise()` renders the plain table, emits it on `table`, and emits the consolidated FAIL signal. No `Config`; **one** output port (`table`); no module-side stream logic.
- `finalise()` renders the `test_name`/`result`/`desc` table from `self.rows` (first column `test_name`) as **plain** text and emits it as `("table", table)`. It does **not** colourise, print, or write a file — the table is plain. It is a **no-op when `self.rows` is empty** (list-mode, or a CRITICAL abort before any result): it returns `None` and emits nothing.
- After rendering, `finalise()` counts the FAIL rows (`r.result == "FAIL"`) and emits **one** `log.error("test_failures", count=n_fail)` if any — the consolidated summary-level exit signal (`handler.failure` → exit 1). This is **additional** to each failure terminal's own per-case `log.error` at origin; `NA`/`SKIP`/`PASS` rows are not counted here.
- Exception handling is the module's own responsibility; a raising `finalise()` is fatal (there is no harness backstop that swallows it).

**Manifest** — `SummariseResultsMod` opens the `rtl_buddy/summarise_results.py` block of `modules/config.yaml` (the two sink specs append their own lines to it):

```yaml
- file: rtl_buddy/summarise_results.py
  plugins:
  - { name: summarise-results, class_name: SummariseResultsMod }
```

**Compatibility source:** `rtl_buddy/src/rtl_buddy/rtl_buddy.py:203-207` — the `do_cmd_test` summary loop: the `"\nTest Results Summary"` header (`:203`) and the per-row format `f"{test_name:<30} {result:<8} {desc:<30}"` (`:205`). rtl_buddy builds this table once (`:207` emits it via `logger.result`); this node renders the same table and emits it once on `table`. The OR-accumulated exit (`:206`) is reproduced as the consolidated `log.error("test_failures", …)` from `finalise()`, layered over each failure terminal's own per-case `log.error` at origin. This is the **same render parity** [10c](10c-summary-handler.md) carried; the table content is identical — only the data path differs (graph edges vs a logging scrape).

### Node + contract wiring (lands in spec [06](../06-graph-yaml.md) / `graphs/test.yaml`)

A single node fans the 13 result ports in and fans the rendered table out to two sinks. Node `results-summary`:

```yaml
- id: results-summary
  module: summarise-results
  contract: any
  contract_config: { mapping: result }       # n→1: every input port funnels onto the `result` output port
  contract_port_mappings:                     # the node's 13-port input surface; each contract port forwards to module param `result`
    compile_fail: [result]
    sim_timeout:  [result]
    load_model:   [result]
    filelist:     [result]
    sweep:        [result]
    preproc:      [result]
    seed:         [result]
    parse_plain:  [result]
    parse_uvm:    [result]
    skip:         [result]
    stop_pre:     [result]
    stop_comp:    [result]
    stop_sim:     [result]
```

- `contract_port_mappings` declares the node's input surface as the 13 contract ports rather than the module signature (`graph.py:97-108`): the node becomes **definite** (`definite_inputs_override=True`), edge destinations validate against the true 13-port surface, and — because the module is definite — each mapping target (`result`) is checked against `run(...)`'s real parameters (`graph.py:102`, fatal `invalid_mapping_target` otherwise). The harness performs **no** forwarding at runtime: the `any` contract already returns module-parameter-keyed results (`{result: val}`), so `contract_port_mappings` is a static-analysis declaration only.
- The node's single output port is `table`, emitted from `finalise()` — the harness infers it from the `finalise()`/`run(...)` emitted-port analysis the same way it infers run-emitted ports, so edges from `results-summary.table` validate.
- 13 input edges, each terminal output port → its distinct `results-summary` contract port, `required: false`:

  | source terminal (node.port) | → `results-summary` port |
  |---|---|
  | `interpret-compile.fail` | `compile_fail` |
  | `interpret-sim.timeout` | `sim_timeout` |
  | `load-model.fail` | `load_model` |
  | `write-filelist.fail` | `filelist` |
  | `expand-sweep.fail` | `sweep` |
  | `run-preproc.fail` | `preproc` |
  | `resolve-seed.fail` | `seed` |
  | `parse-log.default` | `parse_plain` |
  | `parse-uvm-log.default` | `parse_uvm` |
  | `filter-reglvl.skip` | `skip` |
  | `gate-pre.stop` | `stop_pre` |
  | `gate-comp.stop` | `stop_comp` |
  | `gate-sim.stop` | `stop_sim` |

- 2 output edges, the `table` port fanned to both sinks:

  | source (node.port) | → destination (node.port) |
  |---|---|
  | `results-summary.table` | `print-summary.table` ([10e](10e-print-summary.md)) |
  | `results-summary.table` | `write-summary-log.table` ([10f](10f-write-summary-log.md)) |

- Renders at end-of-run: every terminal node always ends, so all 13 ports end and the `any` contract returns `EndSentinel(self.id)`; the node then terminates and its `finalise()` runs — before the harness failure check (`asyncio.gather` completes, then the failure flag is read), the same timing the plugin had. The harness forwards `finalise()`'s emitted `table` downstream **before** propagating `EndSentinel` (`node.py:327-344`), so the one `table` delivery reaches its consumers ahead of the end signal.

This one `any`-fed node replaces the old `fan-in-results` relay + `aggregate-results` pair the TODO #15 redesign retired ([05](../05-branching-and-results.md)) — the contract fans directly into the accumulating node, which fans the rendered table out to the sinks, so **no relay is reintroduced** and the graph still needs no designated termination node.

### Exit code

The exit is driven by `log.error` at two layers ([05 — Result aggregation and exit code](../05-branching-and-results.md#result-aggregation-and-exit-code)):

1. **Per-case, at origin.** Each failure terminal emits its own `log.error` with a specific event name and rich domain context (`compile_failed`, `sim_timeout`, the config-domain `model_*`/`sweep_*`/`preproc_*`/`filelist_*`/`replay_seed_*`, and the parse terminals' `parse_log_*`/`parse_uvm_*`). A genuine `NA` from `parse-*` drives the exit here; an `early-stop` `NA` deliberately emits **no** error (exit-0 divergence).
2. **Consolidated, in this node's `finalise()`.** If the table holds any FAIL row, one `log.error("test_failures", count=…)` — the summary-level signal.

Both set `handler.failure` → exit 1. An all-PASS/SKIP run (and an early-stop-only run) emits no `ERROR` at either layer → exit 0. The pass-like terminals (`parse-*` PASS, `filter.skip`, `early-stop`) emit no log — a `TestResult`-producing node logs only the errors it encounters. Every terminal's summary row, pass-like or not, rides the emitted `TestResult`.

## Companion spec touch-points (coordinated by this spec)

- **[01](01-shared-schema.md) / [02 — payload conventions](../02-payload-conventions.md)** — `TestResult` gains a `test_name: str` field, threaded through its six `@classmethod` constructors (`compile_fail`/`sim_timeout`/`early_stop`/`skip`/`prep`/`parse`). The node sees only the payload, and the table's first column is `test_name` (the test's `get_name()`); terminal sites already compute it for their log calls, so they pass it to the constructor too. (Enrich-over-`key`: the value rides the payload, not a side-channel.)
- **[02 — `any` contract](02-any-contract-and-fan-in.md) / [05 — Re-convergence](../05-branching-and-results.md#re-convergence-the-summary-returns-as-a-graph-node) / [`docs/contracts/index.md`](../../docs/contracts/index.md)** — `any` is now **wired** (consumer: `results-summary`): the "no consumer / retained but unwired" prose is updated, 05's re-convergence section is rewritten to reflect the summary returning as a node that **emits** to two sinks, and `any` is promoted to a first-class row in the contracts index.
- **[10e](10e-print-summary.md) / [10f](10f-write-summary-log.md)** — the two summary sinks that consume `table`; both append to `modules/rtl_buddy/summarise_results.py` and to this spec's `modules/config.yaml` block.
- **[10c](10c-summary-handler.md)** — `SummaryProcessor` retires to dormant infra: dropped from `test.yaml`'s `logging` block but kept in place, unwired. It shares the table-render parity with this node.

## Tests

`modules/tests/test_summarise_results.py`, driven by `run_module_scenario` (`docs/modules/testing.md`). Fixtures: hand-built `TestResult`s (mixed `PASS`/`FAIL`/`NA`/`SKIP`, each carrying `test_name`/`result`/`desc`); the scenario's **emitted-output** capture for the `table` value; `logging_handler` (with its `.failure` flag) for the consolidated error. No graph/harness needed — the fan-in is the `any` contract's, covered by [spec 02](02-any-contract-and-fan-in.md); the console/file rendering is the sinks', covered by [10e](10e-print-summary.md)/[10f](10f-write-summary-log.md).

- Feed an `input_sequence` of N results under `result`, then `finalise()` → exactly one emit on `table`, a **plain** string with a `test_name`/`result`/`desc` row per result in arrival order (first column `test_name`), header `"\nTest Results Summary"`, and **no** ANSI escape codes regardless of environment.
- A `TestResult` with a falsy field (e.g. empty `desc`) → that column renders as `'NA'` in the emitted table (boundary: `None`/empty defaulting, `test_results.py:23-27`).
- No results fed → `finalise()` returns `None`, emits nothing on `table`, and emits no error (boundary: list-mode / CRITICAL abort before any result).
- State persists across calls on one instance: K `run` calls then `finalise()` → one emit whose table holds K rows (accumulation is run-long, instance-held).
- **Consolidated FAIL signal** — rows containing ≥1 FAIL → `finalise()` emits exactly one `log.error("test_failures", count=<n_fail>)` with the FAIL count and `logging_handler.failure is True`, **and still emits the table** (boundary: the summary-level exit driver is additional to, not a replacement for, the table emit).
- **No false exit** — rows of only PASS/SKIP, **and** rows of PASS/SKIP plus an `EARLY_STOP` `NA` (no FAIL) → `finalise()` emits **no** `log.error`, `logging_handler.failure is False`, and still emits the table (boundary: an early-stop NA is not a FAIL row, so it does not drive the consolidated exit — the exit-0 divergence; a genuine `parse` NA drives the exit at *its* origin, not here).

The `any` fan-in behaviour (one delivery per call, no loss across simultaneously-ready ports, `EndSentinel` only after all ports end) is owned and tested by [spec 02](02-any-contract-and-fan-in.md); console colourisation and the file write are owned and tested by [10e](10e-print-summary.md)/[10f](10f-write-summary-log.md). This spec cross-references them and adds no contract or sink test.

## Acceptance criteria

- Tests pass.
- `SummariseResultsMod` is a config-less stateful node: `run(self, result)` appends one `TestResult` per call; `finalise()` renders the **plain** table once (a **no-op returning `None`** when `self.rows` is empty), emits it on the single `table` output port, then emits one `log.error("test_failures", count=…)` iff the table holds a FAIL row; it has **exactly one** output port (`table`) and does no printing, colourising, or file I/O.
- The emitted table renders `test_name` as the first column (rtl_buddy parity) followed by `result`/`desc`, with a missing field shown as `'NA'`, identical content to the retired [10c](10c-summary-handler.md) plugin, and is **plain** (no ANSI).
- This node does no printing, colourising, or file I/O.
- The `modules/config.yaml` manifest entry `{ name: summarise-results, class_name: SummariseResultsMod }` validates and the harness resolves `summarise-results` → `SummariseResultsMod`.
- The `results-summary` node loads: its `contract_port_mappings` builds the 13-port input surface, all 13 input edges validate as destinations, the `table` output port validates and its 2 fan-out edges to `print-summary`/`write-summary-log` resolve, the `any` contract's `mapping: result` delivers each result under `result`, and `finalise()` emits before the failure check (cross-cutting wiring exercised end-to-end in [spec 11](11-graph-and-manifests.md) / [12](12-end-to-end.md)).

## Constraints

- The module is **graph-agnostic**: it consumes **one `TestResult` per invocation** under `result`, renders **plain** text, and emits **one** `("table", str)` from `finalise()`; it never references the `any` contract, the 13 edges, the two sinks, or the graph. The fan-in lives in the contract; the 13-port input surface lives on the node (`contract_port_mappings`). Do **not** give the module `**kwargs` or build its ports from edges.
- The module **never** colourises, prints, gates on `sys.stdout.isatty()`, or writes a file. The rendered table is plain. Keep this node to its single responsibility — accumulate and emit the rendered table.
- `run(self, result)` is the **definite** single-parameter signature; `contract_config: { mapping: result }` is what makes the `any` contract return `{result: val}`, so the contract output port name and the module parameter name must match (`result`).
- `finalise()` renders the table once (a **no-op returning `None`** when `self.rows` is empty — list-mode / CRITICAL abort), emits it on `table`, then emits **one** `log.error("test_failures", count=…)` iff any row has `result == "FAIL"` — the consolidated exit signal, layered over each failure terminal's per-case `log.error`. Count FAIL rows only: `NA`/`SKIP`/`PASS` never trigger it. The table emit is additional to, not gated by, the FAIL check.
- Render parity with rtl_buddy (and the retired [10c](10c-summary-handler.md)): header `"\nTest Results Summary"`, per-row `{test_name:<30} {result:<8} {desc:<30}` with `'NA'` defaulting. Read `TestResult` fields directly — no event-dict scraping.

## Notes

This restores the summary as a **visible graph node**: its data path is the 13 terminal edges fanning in to `results-summary` **and** the `table` edges fanning out, not a scrape of the logging chain. The render content is identical to the [10c](10c-summary-handler.md) plugin it replaces; the change is one of dataflow visibility plus atomicity — this node only summarises and emits the rendered table.
