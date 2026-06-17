# Branching, early-exit, and results

`rtl_buddy` is an imperative pipeline with many early `return`s; a graph is fixed dataflow.
This file shows how each early-exit becomes a named output port that routes the item off
the main line, and how the mutually-exclusive results — terminal ports left **unwired**
since the TODO #15 redesign — are instead collected by the `SummaryProcessor` logging
plugin rather than re-converging through a graph node.

## Each terminal outcome is a named output port

For each test invocation `rtl_buddy` produces **exactly one** terminal result. Each
producing stage emits it on a dedicated output port (left **unwired** since the TODO #15
redesign — see [Re-convergence](#re-convergence-the-summary-is-a-logging-concern-not-a-graph-node))
and additionally logs a `test_result` row; the continue-path goes to the next stage:

| stage | continue port → next stage | terminal port (unwired; logs `test_result`) |
|---|---|---|
| `filter` | `keep` | `skip` (`SkipResults`) |
| `gate-pre` | `go` | `stop` (`EarlyStopResults`) |
| `cc-int` | `ok` | `fail` (`CompileFailResults`) |
| `gate-comp` | `go` | `stop` (`EarlyStopResults`) |
| `sim-int` | `ok` | `timeout` (`SimTimeoutResults`) |
| `gate-sim` | `go` | `stop` (`EarlyStopResults`) |
| `route-post` | `uvm` → `parse-uvm-log`, `plain` → `parse-log` | — (classifier only) |
| `parse-log` | — | `result` (PASS/FAIL/NA) |
| `parse-uvm-log` | — | `result` (PASS/FAIL/NA) |

Because a terminal item leaves the main line, **no downstream stage ever sees it** — which
is why no module needs an "am I already done?" guard. Choosing the port is ordinary
business logic (`rc == 0`, `level out of range`, `timed_out`), expressed as a named-port
return — the framework's sanctioned mechanism, and statically analysable (all port names
are string literals, so `definite_emits` holds).

## `--early-stop` as gates

Three `early-stop-gate` nodes sit at the pre/comp/sim boundaries. Each compares the global
`early_stop` value (a persistent input) against its configured `phase`; if the run should
stop here it emits `stop`, else `go`. Since `early_stop` is one global value, a gate makes
the same choice for every item — so the gate at the configured boundary diverts the whole
stream, reproducing `rtl_buddy`. `--early-stop post` (default) means no gate fires.

## `--list` as an empty stream

In list-mode `route-list` fires its `list` branch: `list-names` prints the suite's test names
and the `run` branch never fires. `select` therefore receives only the `EndSentinel` the harness
broadcasts to every destination at node end, fans out nothing, and the empty stream propagates
`EndSentinel` through the rest of the pipeline; no terminal site fires, so `SummaryProcessor`
collects zero `test_result` rows and its `finalise()` is a no-op.

The one subtlety that makes this exit 0 is the contract choice on `select` and `list-names`:
both use **`default`**, not `unit`. A node fed an empty stream (its required port ends before any
data) is a `missing_required_inputs` **error** under `unit` (`contracts/unit.py`) — an `ERROR`
that flips the harness failure flag → exit 1 — but under `default` the same empty stream returns
`EndSentinel` silently (`contract_default.py` logs only on a *partial* end). Because exactly one
of `route-list`'s branches is unfired on every run, the *other* branch's node is always fed an
empty stream: in list-mode that is `select`, in run-mode it is `list-names`. Pairing both with
`default` is what keeps `--list` at exit 0 and keeps a normal passing run from being forced to
exit 1 by the unfired `list-names`. See
[04 — Why each contract](04-pipeline-and-contracts.md#default--the-post-branch-run-once-nodes-select-list-names).
No special casing anywhere else.

## Re-convergence: the summary is a logging concern, not a graph node

> **Redesigned (TODO #15, 2026-06-10; plugin form revised 2026-06-11).** Earlier drafts
> re-converged the 13 terminal ports at a `fan-in-results` relay feeding an `aggregate-results`
> sink whose `finalise()` rendered the summary table and drove the exit code. TODO #15 retired
> that topology: the summary is rendered by a per-graph **logging plugin**, so the terminal
> nodes need no collector and the graph needs no sink. The plugin is a stateful structlog
> **processor** (`SummaryProcessor`), revised from an earlier `SummaryHandler` +
> `drop_summary_events` two-piece form — a processor accumulates *and* suppresses in one
> object, which is the natural fit (a handler was a workaround for the missing
> processor-finalisation hook; see [07 item 27](07-ambiguities-and-assumptions.md)). Rationale
> in [Why the summary left the graph](#why-the-summary-left-the-graph).

The 13 terminal ports no longer converge anywhere. Each terminal node does two things at its
emission site:

1. **emits its `TestResults` on its named output port exactly as before** — but that port is
   left **unwired**, so the harness logs `no_destination` at INFO and the item simply leaves
   the graph. No module signature or `definite_emits` change: the module stays graph-agnostic
   and does not know whether anything listens.
2. **logs its outcome** (carrying `test_name`/`key`/`result`/`desc`; `test_name` = the test's
   `get_name()`, the summary's first column) so the summary processor can collect
   the row, in one of two styles:
   - the result-producing terminals that would otherwise log nothing
     (`parse-log`/`parse-uvm-log`, `filter.skip`, `early-stop-gate`) call `log.info("test_result",
     …)` (pass-like) or `log.error("test_result", …)` (non-`is_pass()`, which also drives the exit);
   - the failure terminals that already `log.error` (`compile_failed`, `sim_timeout`, the five
     `*_failed`) just add `test_name`/`result`/`desc` kwargs to their existing call.

A `git-status` setup node similarly calls `log.info("git_state", branch=..., sha=...,
dirty=...)` once at run start. The summary plugin's role is **outcomes only** — it collects the
events on its watch-list and nothing else; `git_state` is not on the list. A **`SummaryProcessor`**
— a per-graph structlog processor — accumulates the watched rows and renders the table from its
`finalise()` teardown hook. `git_state` falls through the processor to the console and prints at
run start like any other log line.

### The `SummaryProcessor` logging plugin

The plugin is a stateful structlog **processor**, not a `logging.Handler`. It sits in the
harness handler's formatter chain **before** `ConsoleRenderer` (non-terminal under
`include_default: true`, so `__call__` returns an `EventDict`). A `Config` carries the
**watch-list** of outcome event names it collects (default: `test_result` plus the failure
terminals' `compile_failed`/`sim_timeout`/`*_failed`) and a `suppress` subset (default just
`test_result`). On each watched event it harvests `{key, result, desc}` into a row; for events in
`suppress` it then raises `DropEvent` to drop the per-event console line, while the failure events
are collected **and** returned so they still print as errors. Every non-watched event (including
`git_state`) is returned unchanged and flows on to `ConsoleRenderer`. The table is rendered once
in `finalise()` (full spec in [10c](specs/10c-summary-handler.md)):

```python
# log/summary.py
from __future__ import annotations
from typing import Any
from collections.abc import MutableMapping
from serde import serde, field
from structlog.exceptions import DropEvent

class SummaryProcessor:
    @serde
    class Config:
        events: list[str] = field(default_factory=lambda: [
            "test_result", "compile_failed", "sim_timeout", "load_model_failed",
            "sweep_failed", "preproc_failed", "filelist_failed", "replay_seed_invalid"])
        suppress: list[str] = field(default_factory=lambda: ["test_result"])

    def __init__(self, config):
        self._events, self._suppress = set(config.events), set(config.suppress)
        self._rows = []                          # fresh per run

    def __call__(self, logger, method_name: str,
                 event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
        name = event_dict.get("event")
        if name in self._events:
            self._rows.append({"test_name": event_dict.get("test_name"),   # summary's first column
                               "key": event_dict.get("key"),
                               "result": event_dict.get("result"),
                               "desc": event_dict.get("desc")})
            if name in self._suppress:
                raise DropEvent                  # summary-only → drop the console line
        return event_dict                        # failure errors, git_state, etc. fall through

    def finalise(self):
        if not self._rows:                       # nothing to summarise → no-op
            return
        ...                                      # render the consolidated PASS/FAIL/NA table
```

Why a processor and not a handler: the processor *class* holds state across events (that is
what processor classes are for), sits before `ConsoleRenderer` to intercept-and-accumulate
result events, and uses `DropEvent` — a processor-only mechanism — to suppress their per-event
lines in the *same* object. A `logging.Handler` could not raise `DropEvent` against the harness
handler's output, so a handler form needed a *second* `drop_summary_events` processor; the
single processor removes that. `finalise()` is the per-run teardown hook the harness invokes at
run end, **before** the failure check, so the table renders whether the run passed or
failed-deferred (`docs/logger/implementation.md` — "End-of-run finalisation with `finalise()`",
extended to processors per [07 item 27](07-ambiguities-and-assumptions.md)).

It is wired per-graph in `graphs/test.yaml` (see [06](06-graph-yaml.md)); a graph that wants no
summary simply omits the `logging` block.

### The CRITICAL path

On a `CRITICAL` record `LoggingFatalHandler` raises `typer.Exit(1)` and the run aborts before
the per-run teardown runs, so `finalise()` is never reached and no table renders. This is
acceptable: `CRITICAL` paths (missing/malformed config, builder/testbench resolution) abort
before any test result exists, and the `if not self._rows: return` guard keeps `finalise()` a
no-op whenever there is nothing to summarise.

### Why the summary left the graph

The graph never needed a sink node for termination. `graph.py` gathers **all** node
coroutines (`runs = [node.run() for node in graph.nodes.values()]; await asyncio.gather(*runs)`),
not a designated sink; each node terminates when its contract returns `EndSentinel`, and a
node with no outbound edge simply propagates to an empty destination list. `aggregate-results`
contributed nothing to termination — its only purpose was to provide a `finalise()` callsite
after all results arrived, which is a *rendering* concern, not a *termination* one. Moving
rendering to a logging plugin removes both `aggregate-results` and the `fan-in-results` relay
that existed solely to feed it. It also dissolves the original awkwardness that prompted TODO
#15: `git-status` becomes a plain `log.info` from a setup node, with no graph routing,
persistent inputs, or payload surgery. Any future cross-cutting run metadata (timing,
platform, invocation timestamp) follows the same pattern.

### The `any` contract (retained, currently unwired)

The general-purpose **`any` contract** (fire on whichever port is ready first, one delivery
per call, end when all ports end) was created for `fan-in-results`. With the relay removed it
has **no consumer in the `test` graph**, but it is retained as a reusable contract. Its
sketch, invariants, and tests live in [spec 02](specs/02-any-contract-and-fan-in.md);
correctness review is [07 item 20](07-ambiguities-and-assumptions.md). (It briefly also hosted
the interim parallel-safety shim's `release_lock` hook; that shim was removed entirely by
TODO #30 in favour of per-tag artefact naming — see
[Interim CWD-collision posture](#interim-cwd-collision-posture--per-tag-artefact-naming).)

## Interim CWD-collision posture — per-tag artefact naming

> **Posture (TODO #30, 2026-06-10): name artefacts per-tag; no serialisation.** An earlier
> draft serialised the compile/sim region with a process-wide `asyncio.Lock`
> (`serial_acquire` on `write-filelist` + an `any.release_lock` release on `fan-in`). That
> shim was **removed**: it only ever bought correctness, not parallelism (it held the lock
> across the whole expensive region), and the TODO #15 redesign deleted its release node. In
> its place, the graph names the artefacts it controls **per-tag**, so concurrent tests don't
> collide and the region stays genuinely concurrent. This is an **interim, graph-local subset**
> of [07](07-ambiguities-and-assumptions.md) item 17 — the upstream per-invocation-subdir
> change — which remains the **reference fix** and is kept on the books (see "Residual" below).

### The hazard

A compile produces non-graph-routed artefacts in CWD that the *same test's* sim later
consumes. The harness launches all node tasks concurrently (`asyncio.gather`), and `cc-run`
(compile) and `sim-run` (sim) are *different* nodes, so test B's compile can run while test
A's sim has not yet read its artefacts. The collision is on any **shared-name** artefact.

### What the graph names per-tag (collision removed)

`build-compile-cmd` already computes `test_tag = re.sub(r"[^A-Za-z0-9_.-]", "_",
ctx["test"].get_name())` and derives per-tag paths, so most artefacts are already isolated:

| artefact | producer | naming | status |
|---|---|---|---|
| `obj_dir_<tag>/` | `build-compile-cmd` (`--Mdir`) | `str(Path(work_dir) / f"obj_dir_{test_tag}")` | per-tag + `work_dir`-rooted (R14) |
| verilator `simv` | compile | `f"{work_dir}/obj_dir_{test_tag}/simv"` | per-tag + `work_dir`-rooted (R14) |
| compile/sim `.log`/`.err` | `run-process` | `f"{logs_dir}/{test_tag}…"` | already per-tag |
| `.randseed` | `write-randseed` | `f"{logs_dir}/{test_tag}…"` | already per-tag |
| **`run.f`** | **`write-filelist`** | **was literal `run.f` → now `Path(work_dir) / f"run.{test_tag}.f"`** | **fixed by (B) + `work_dir`-rooted (R14)** |

Change (B) is the filelist naming: `write-filelist` writes `run.{test_tag}.f` and emits that
`Path` on its `filelist` port; `build-compile-cmd` already passes `filelist["filelist"]` to `-f`,
so no edge or downstream change is needed. `write-filelist` reverts to the plain `default`
contract. On top of (B), R14 roots `run.f` and `obj_dir_<tag>/` on `check-suite-cwd`'s `work_dir`
(both writers take it as a load-bearing persistent input), bringing them under the same
artefact-location provider model as `logs/` so a relocation is a one-node change.

### Residual — what only item 17 fixes

Per-tag naming closes the filelist collision and confirms the already-per-tag artefacts, but
it does **not** cover artefacts whose names the graph cannot freely choose. These split into two
severity classes — one **corrupting**, one benign:

- **non-verilator `simv` (corrupting — silent wrong results)** — a *fixed configured* name from
  `builder_cfg.get_simv()` (no `build_dir` prefix; see
  [01a — Verilator quirk](specs/01a-builder-schema.md)). Two concurrent compiles write the same
  CWD path, so test B's compile can overwrite the binary test A is about to simulate: test A then
  runs B's `simv`, both exit rc 0, and the summary shows two meaningless passes. The corruption is
  **silent** — no error, no parity check catches it. Redirecting it per-tag needs a
  builder-specific output-path option, not a rename the graph owns.
- **anything the simulator/compiler writes into CWD under a fixed name (corrupting)** —
  intermediate files, tool dbs/logs; same silent-overwrite hazard as the `simv` for any tool that
  hard-codes a CWD output name.
- **`test.log`/`test.err`/`test.randseed` symlinks (benign)** — `link-latest` forces fixed
  "latest" names in CWD; concurrent runs race on them (last-writer-wins), but they are convenience
  pointers to per-tag targets, so a race only mispoints the pointer — it does **not** corrupt
  results.

These are exactly the artefacts that **item 17's per-invocation working directories** isolate
wholesale, and that reference implementation is materially more complete than this naming
subset. Until item 17 lands, structural concurrency is safe for verilator builders and the
filelist, but **unsafe for fixed-`simv` (non-verilator) builders**: a concurrent multi-test run
on such a builder can silently produce wrong results (above). There is **no built-in
serialisation** — the lock shim was removed (TODO #30) and not replaced — so the only interim
workaround is **operational**: invoke such suites one test per `rtl-comrade test` call (a single
item in flight) until item 17 is ported into rtl_comrade. This residual is recorded under item 17 — do not
re-introduce a lock to paper over it; that path was tried and removed.

## Result aggregation and exit code

There is no aggregator node. The exit code and the summary are produced by two independent,
self-contained mechanisms:

1. **Exit code** is driven by the **per-emission `log.error`** at each failure site (table
   below). A single `ERROR` sets `handler.failure = True`, which the harness turns into a
   non-zero exit, reproducing `rtl_buddy`'s `exit_code |= 0 if is_pass() else 1`
   (`rtl_buddy/src/rtl_buddy/rtl_buddy.py:206`) exactly (SKIP/PASS log no `ERROR` and
   contribute nothing; FAIL and genuine NA — compile fail, timeout, parse FAIL/NA, unknown —
   each `log.error` once and force exit 1). **`early-stop` is the one exception**: its
   `EarlyStopResults` is NA but it logs `log.info`, not `log.error`, so a user-requested stop
   exits 0 — a deliberate divergence from rtl_buddy's exit 1 (see
   [07 — Notable divergences](07-ambiguities-and-assumptions.md#notable-divergences-from-rtl_buddy)).
   This is now the **sole** exit-code driver; the old
   belt-and-braces `aggregate-results.finalise()` `log.error` is gone with the node.
2. **Summary table** is rendered by `SummaryProcessor.finalise()` from the watch-list events each
   terminal site emits (`test_result` from the otherwise-silent paths; the failure terminals' own
   `compile_failed`/`sim_timeout`/`*_failed`) — see
   [Re-convergence](#re-convergence-the-summary-is-a-logging-concern-not-a-graph-node) — reproducing
   `do_cmd_test`'s "Test Results Summary" loop (`rtl_buddy/src/rtl_buddy/rtl_buddy.py:203-207`).
   The processor collects **outcomes only**; the `show_git_rev` git state (`rtl_buddy.py:500-522`)
   is logged separately by `git-status` and falls through to the console at run start, not into
   this table.

`CRITICAL` stays reserved for harness-fatal conditions (missing/malformed `root_config.yaml`,
missing builder/testbench), matching `rtl_buddy`'s `logger.critical` → `typer.Abort`
(e.g. `rtl_buddy/src/rtl_buddy/config/root.py:89`, `config/platform.py:67-83`).

## Log idioms per failure site

Each module and contract that can fail records its idiom here. Every terminal site logs its
outcome (carrying `test_name`/`key`/`result`/`desc`; `test_name` = the test's `get_name()`, the
summary's first column) so `SummaryProcessor`'s watch-list can collect its row —
**either** as a `test_result` event (the result-producing terminals that would otherwise be
silent: `parse-log`/`parse-uvm-log`, `filter.skip`, `early-stop-gate`) **or** as the terminal's
own watched event with `result`/`desc` kwargs added (the failure terminals that already
`log.error`). The rows below list each site's idiom. Four idioms are in play, per
`docs/invariants.md:14-23` and `docs/harness/logging.md`:

- **`log.fatal`** — immediate `SystemExit(1)`. Reserved for unrecoverable setup/config
  failures and harness-internal scheduling errors.
- **Unwired `result` port** — the terminal outcome is still returned on the module's named
  output port (`skip`, `stop`, `fail`, `timeout`, `result`), but the port has no edge, so
  the harness logs `no_destination` at INFO and the item leaves the graph. No collector.
- **`log.error` at emission** — fires once at every per-test FAIL emission site and is the
  **sole** deferred-exit driver (`handler.failure`). Carries `result`/`desc` so the watch-list
  collects the row from the *same* event (no separate `test_result` for these). There is no
  second `finalise()` site.
- **`log.info("test_result", …)`** — pass-like terminals (PASS, SKIP) emit their summary row at
  INFO, so they are collected but do **not** affect the exit code.

### Setup / config — `log.fatal`

| Site | Failure |
|---|---|
| `discover-config-file` | `root_config.yaml` not found walking up CWD |
| `parse-root-config` | malformed YAML / schema mismatch |
| `select-platform` | no platform's `unames` matches |
| `resolve-builder` | named builder missing on platform |
| `check-suite-cwd` | `test_config` resolves outside CWD (parent ≠ CWD) — catches `-c /abs/elsewhere/tests.yaml`, `-c ../sibling/tests.yaml`, `-c subdir/tests.yaml`; also fires if the resolved path is not a file. Not wired in regression (chdir's per-suite) |
| `parse-suite-config` | `tests.yaml` missing/malformed; testbench bind failure |
| `select-tests` | named test not in suite |
| `run-process` | subprocess launch failure (binary not on PATH, permission denied) — distinct from non-zero `rc`, which is per-test |

### Per-test failure — unwired `result` port + `log.error` at emission (sole exit driver; the same event carries the summary row)

Each row below `log.error`s **its own watched event** carrying `result`/`desc`; `SummaryProcessor`'s
`Config` watch-list lists those event names, so the failure event *is* the summary row — no
separate `test_result` is emitted for these.

| Site | Port → payload (unwired) | Emission log (watched event) |
|---|---|---|
| `interpret-compile.fail` | `fail` → `CompileFailResults` | `log.error("compile_failed", rc, stderr_path, result, desc)` |
| `interpret-sim.timeout` | `timeout` → `SimTimeoutResults` | `log.error("sim_timeout", err, result, desc)` |
| `load-model.fail` | `fail` → FAIL payload | `log.error("load_model_failed", model_path, result, desc)` |
| `write-filelist.fail` | `fail` → FAIL payload | `log.error("filelist_failed", path, result, desc)` |
| `expand-sweep.fail` | `fail` → FAIL payload | `log.error("sweep_failed", exc_info, result, desc)` |
| `run-preproc.fail` | `fail` → FAIL payload | `log.error("preproc_failed", exc_info, result, desc)` |
| `resolve-seed.fail` (REPLAY only) | `fail` → FAIL payload | `log.error("replay_seed_invalid", path, result, desc)` |

Parse FAIL/NA verdicts (`parse-log`/`parse-uvm-log`) are in the next table — they have no prior
event name, so they emit `test_result` directly. Topology consequence: all 13 terminal ports stay
**unwired** — there is no `fan-in`/`aggregate-results` to receive them (TODO #15 redesign). Adding
a new failure terminal adds no edge; the module enriches its existing `log.error` and the
watch-list name is added to `SummaryProcessor`'s `Config`.

### Per-test terminals that log `test_result` directly (the otherwise-silent paths)

These have no prior log event, so they emit `test_result` themselves — `log.error` when
`not is_pass()` (drives the exit), `log.info` when pass-like.

| Site | Port → payload (unwired) | Emission log |
|---|---|---|
| `parse-log.result` | `result` → PASS/FAIL/NA | `log.error("test_result", …)` on FAIL/NA (exit driver); `log.info("test_result", …)` on PASS |
| `parse-uvm-log.result` | `result` → PASS/FAIL/NA | `log.error("test_result", …)` on FAIL/NA; `log.info("test_result", …)` on PASS |
| `filter-reglvl.skip` | `skip` → `SkipResults` | `log.info("test_result", …)` (SKIP is pass-like via `is_pass()`; no exit contribution) |
| `early-stop-gate.stop` (×3) | `stop` → `EarlyStopResults` | `log.info("test_result", …)` *(NA, but `log.info` not `log.error` — a user-requested stop exits 0; deliberate divergence from rtl_buddy's exit 1, see [07 — Notable divergences](07-ambiguities-and-assumptions.md#notable-divergences-from-rtl_buddy))* |

### Summary rendering — `SummaryProcessor.finalise()` (not an exit driver)

| Site | Trigger | Action |
|---|---|---|
| `SummaryProcessor.finalise()` | run end (per-run teardown), if any watched row collected | render the consolidated **results** table; **no** `log.error` (exit is driven per-emission above) |
| `git-status` (setup) | run start | `log.info("git_state", branch=..., sha=..., dirty=...)` once; falls through to the console (not collected by `SummaryProcessor`) |

### Deferred

| Site | Failure | Status |
|---|---|---|
| `parse-log` / `parse-uvm-log` | parse-machinery exception distinct from FAIL classification (log file missing; regex raises on malformed content) | Deferred pending TODO #13 (VlogPost quirks: replicate vs fix) |
