# Branching, early-exit, and results

`rtl_buddy` is an imperative pipeline with many early `return`s; a graph is fixed dataflow.
This file shows how each early-exit becomes a named output port that routes the item off
the main line, and how the mutually-exclusive results re-converge through a custom contract.

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

`select-tests` with `list=True` prints names and emits nothing. The empty stream
propagates `EndSentinel` through every node; no terminal site fires, so `SummaryHandler`
collects zero `test_result` rows and its `finalise()` is a no-op, no `log.error` fires →
exit 0. No special casing anywhere else.

## Re-convergence: the summary is a logging concern, not a graph node

> **Redesigned (TODO #15, 2026-06-10).** Earlier drafts re-converged the 13 terminal ports
> at a `fan-in-results` relay feeding an `aggregate-results` sink whose `finalise()` rendered
> the summary table and drove the exit code. TODO #15 retired that topology: the summary is
> rendered by a per-graph **logging handler**, so the terminal nodes need no collector and
> the graph needs no sink. Rationale in [Why the summary left the graph](#why-the-summary-left-the-graph).

The 13 terminal ports no longer converge anywhere. Each terminal node does two things at its
emission site:

1. **emits its `TestResults` on its named output port exactly as before** — but that port is
   left **unwired**, so the harness logs `no_destination` at INFO and the item simply leaves
   the graph. No module signature or `definite_emits` change: the module stays graph-agnostic
   and does not know whether anything listens.
2. **calls `log.info("test_result", key=..., result=..., desc=...)`** so the summary handler
   can collect the row. (Previously these rows were emitted only by `aggregate-results.finalise()`;
   they now move to each terminal site.)

A `git-status` setup node similarly calls `log.info("git_state", branch=..., sha=...,
dirty=...)` once at run start. A **`SummaryHandler`** — a per-graph `logging.Handler` plugin —
collects both event kinds and renders the consolidated table (with the git stateline) from
its `finalise()` teardown hook.

### The `SummaryHandler` logging plugin

The handler attaches **no formatter**, so it receives the raw structured event `dict` as
`record.msg` (`docs/harness/logging.md` — "a wholly-custom `logging.Handler` inherits only the
shared preprocessors"). It accumulates `test_result` rows and the single `git_state` event,
then renders in `finalise()`:

```python
# log/summary.py
import logging

class SummaryHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self._rows = []
        self._git_state = None

    def emit(self, record):
        event = record.msg                      # raw event dict; no formatter attached
        if not isinstance(event, dict):
            return
        match event.get("event"):
            case "test_result":
                self._rows.append(event)
            case "git_state":
                self._git_state = event

    def finalise(self):
        if not self._rows:                      # nothing to summarise → no-op
            return
        if self._git_state is not None:
            ...                                 # render the git stateline
        ...                                     # render the consolidated PASS/FAIL/NA table
```

`finalise()` is the now-real teardown hook: `App.cleanup` walks the root logger's handlers
and calls `finalise()` on any that define one, **before** the failure check, so the table
renders whether the run passed or failed-deferred (`src/rtl_comrade/app.py:171-174`,
`docs/logger/implementation.md` — "End-of-run finalisation with `finalise()`").

### The paired drop-processor

With `include_default: true` the harness `ConsoleRenderer` would also print every
`test_result` / `git_state` line, duplicating the table. A processor in the same `logging`
block raises `structlog.exceptions.DropEvent` on those two events to hide them from the
console; the `SummaryHandler`, being a separate root handler with its own (empty) chain,
still receives them (`docs/harness/logging.md` — the `DropEvent` catch is on the harness
handler's write path only).

```python
# log/summary.py
from structlog.exceptions import DropEvent

def drop_summary_events(logger, method_name, event_dict):
    if event_dict.get("event") in ("test_result", "git_state"):
        raise DropEvent
    return event_dict
```

Both are wired per-graph in `graphs/test.yaml` (see [06](06-graph-yaml.md)); a graph that
wants no summary simply omits the `logging` block.

### The CRITICAL path

`SummaryHandler` is added to the root logger **after** `LoggingFatalHandler`, which raises
`typer.Exit(1)` on a `CRITICAL` record before any later handler runs — so the handler never
observes `CRITICAL` (`docs/harness/logging.md` — "custom handlers never observe `CRITICAL`
records"). On a `CRITICAL` path the run aborts before `App.cleanup`, so `finalise()` is never
reached and no table renders. This is acceptable: `CRITICAL` paths (missing/malformed config,
builder/testbench resolution) abort before any test result exists, and the `if not self._rows:
return` guard keeps `finalise()` a no-op whenever there is nothing to summarise.

### Why the summary left the graph

The graph never needed a sink node for termination. `graph.py` gathers **all** node
coroutines (`runs = [node.run() for node in graph.nodes.values()]; await asyncio.gather(*runs)`),
not a designated sink; each node terminates when its contract returns `EndSentinel`, and a
node with no outbound edge simply propagates to an empty destination list. `aggregate-results`
contributed nothing to termination — its only purpose was to provide a `finalise()` callsite
after all results arrived, which is a *rendering* concern, not a *termination* one. Moving
rendering to a logging handler removes both `aggregate-results` and the `fan-in-results` relay
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
| `obj_dir_<tag>/` | `build-compile-cmd` (`--Mdir`) | `f"obj_dir_{test_tag}"` | already per-tag |
| verilator `simv` | compile | `f"obj_dir_{test_tag}/simv"` | already per-tag |
| compile/sim `.log`/`.err` | `run-process` | `f"{logs_dir}/{test_tag}…"` | already per-tag |
| `.randseed` | `write-randseed` | `f"{logs_dir}/{test_tag}…"` | already per-tag |
| **`run.f`** | **`write-filelist`** | **was literal `run.f` → now `run.{test_tag}.f`** | **fixed by (B)** |

The only change (B) makes is the filelist: `write-filelist` writes `run.{test_tag}.f` and
emits that `Path` on its `filelist` port; `build-compile-cmd` already passes
`filelist["filelist"]` to `-f`, so no edge or downstream change is needed. `write-filelist`
reverts to the plain `default` contract.

### Residual — what only item 17 fixes

Per-tag naming closes the filelist collision and confirms the already-per-tag artefacts, but
it does **not** cover artefacts whose names the graph cannot freely choose:

- **non-verilator `simv`** — a *fixed configured* name from `builder_cfg.get_simv()` (no
  `build_dir` prefix; see [01a — Verilator quirk](specs/01a-builder-schema.md)). Redirecting
  it per-tag needs a builder-specific output-path option, not a rename the graph owns.
- **`test.log`/`test.err`/`test.randseed` symlinks** — `link-latest` forces fixed "latest"
  names in CWD; concurrent runs race on them (last-writer-wins; convenience pointers, not
  corrupting).
- **anything the simulator/compiler writes into CWD itself** (intermediate files, tool logs).

These are exactly the artefacts that **item 17's per-invocation working directories** isolate
wholesale, and that reference implementation is materially more complete than this naming
subset. Until item 17 lands, structural concurrency is safe for verilator builders and the
filelist; for builders whose `simv` is a fixed name, concurrent same-builder runs still rely
on item 17 (or running them one at a time). This residual is recorded under item 17 — do not
re-introduce a lock to paper over it; that path was tried and removed.

## Result aggregation and exit code

There is no aggregator node. The exit code and the summary are produced by two independent,
self-contained mechanisms:

1. **Exit code** is driven by the **per-emission `log.error`** at each failure site (table
   below). A single `ERROR` sets `handler.failure = True`, which the harness turns into a
   non-zero exit, reproducing `rtl_buddy`'s `exit_code |= 0 if is_pass() else 1`
   (`rtl_buddy/src/rtl_buddy/rtl_buddy.py:206`) exactly (SKIP/PASS log no `ERROR` and
   contribute nothing; FAIL/NA — compile fail, timeout, early-stop, unknown — each
   `log.error` once and force exit 1). This is now the **sole** exit-code driver; the old
   belt-and-braces `aggregate-results.finalise()` `log.error` is gone with the node.
2. **Summary table** is rendered by `SummaryHandler.finalise()` from the `test_result` rows
   each terminal site emits (see [Re-convergence](#re-convergence-the-summary-is-a-logging-concern-not-a-graph-node)),
   reproducing `do_cmd_test`'s "Test Results Summary" loop
   (`rtl_buddy/src/rtl_buddy/rtl_buddy.py:203-207`) plus the `show_git_rev` stateline
   (`rtl_buddy.py:500-522`).

`CRITICAL` stays reserved for harness-fatal conditions (missing/malformed `root_config.yaml`,
missing builder/testbench), matching `rtl_buddy`'s `logger.critical` → `typer.Abort`
(e.g. `rtl_buddy/src/rtl_buddy/config/root.py:89`, `config/platform.py:67-83`).

## Log idioms per failure site

Each module and contract that can fail records its idiom here. Every terminal site (failure
or not) additionally emits `log.info("test_result", key=..., result=..., desc=...)` at
emission so `SummaryHandler` can collect its row; the rows below list only the *failure*
idiom. Three failure idioms are in play, per `docs/invariants.md:14-23` and
`docs/harness/logging.md`:

- **`log.critical`** — immediate `SystemExit(1)`. Reserved for unrecoverable setup/config
  failures and harness-internal scheduling errors.
- **Unwired `result` port** — the terminal outcome is still returned on the module's named
  output port (`skip`, `stop`, `fail`, `timeout`, `result`), but the port has no edge, so
  the harness logs `no_destination` at INFO and the item leaves the graph. No collector.
- **`log.error` at emission** — fires once at every per-test FAIL emission site and is the
  **sole** deferred-exit driver (`handler.failure`). There is no second `finalise()` site.
- **No `log.error`** — non-failure terminals (SKIP, early-stop) emit their `test_result`
  row but log no `ERROR`, so they do not affect the exit code.

### Setup / config — `log.critical`

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

### Per-test failure — unwired `result` port + `log.error` at emission (sole exit driver) + `log.info("test_result")` row

| Site | Port → payload (unwired) | Emission log |
|---|---|---|
| `interpret-compile.fail` | `fail` → `CompileFailResults` | `log.error` (compile `rc`, stderr path) |
| `interpret-sim.timeout` | `timeout` → `SimTimeoutResults` | `log.error` (`timed_out`, stderr path) |
| `parse-log.result` (FAIL) | `result` → FAIL payload | `log.error` (parsed reason) |
| `parse-uvm-log.result` (FAIL) | `result` → FAIL payload | `log.error` (severity counts) |
| `load-model.fail` | `fail` → FAIL payload | `log.error` (`models.yaml` path, reason) |
| `write-filelist.fail` | `fail` → FAIL payload | `log.error` (filelist generation reason) |
| `expand-sweep.fail` | `fail` → FAIL payload | `log.error` (sweep script trace) |
| `run-preproc.fail` | `fail` → FAIL payload | `log.error` (preproc script trace) |
| `resolve-seed.fail` (REPLAY only) | `fail` → FAIL payload | `log.error` (missing/malformed `.randseed` path) |

The bottom five rows are **new failure ports** added to modules that previously had only a
success path. Topology consequence: all 13 terminal ports are now **unwired** — there is no
`fan-in`/`aggregate-results` to receive them (TODO #15 redesign). Adding a new terminal source
adds no edge; the module just emits its `test_result` row and leaves its port unwired. Every
failure site emits exactly one `log.error` (the sole exit-code driver) and one
`log.info("test_result", ...)` (the summary row).

### Per-test non-failure terminals — unwired `result` port + `log.info("test_result")` row, **no `log.error`**

| Site | Port → payload (unwired) |
|---|---|
| `filter-reglvl.skip` | `skip` → `SkipResults` (SKIP is pass-like via `is_pass()`) |
| `early-stop-gate.stop` (×3 instances) | `stop` → `EarlyStopResults` (normal terminal, not a failure) |

### Summary rendering — `SummaryHandler.finalise()` (not an exit driver)

| Site | Trigger | Action |
|---|---|---|
| `SummaryHandler.finalise()` | run end (via `App.cleanup`), if any `test_result` row collected | render the consolidated table + git stateline; **no** `log.error` (exit is driven per-emission above) |
| `git-status` (setup) | run start | `log.info("git_state", branch=..., sha=..., dirty=...)` once; collected by `SummaryHandler` |

### Deferred

| Site | Failure | Status |
|---|---|---|
| `parse-log` / `parse-uvm-log` | parse-machinery exception distinct from FAIL classification (log file missing; regex raises on malformed content) | Deferred pending TODO #13 (VlogPost quirks: replicate vs fix) |
