# Branching, early-exit, and results

`rtl_buddy` is an imperative pipeline with many early `return`s; a graph is fixed dataflow.
This file shows how each early-exit becomes a named output port that routes the item off
the main line, and how the mutually-exclusive results — the 13 result ports — re-converge
at one **`results-summary`** graph node (spec [10d](specs/10d-summarise-results.md)) via the
`any` contract's fan-in, which renders the consolidated table.

## Each terminal outcome is a named output port

For each test invocation `rtl_buddy` produces **exactly one** terminal result. Each
producing stage emits it on a dedicated output port (fanned into `results-summary` — see
[Re-convergence](#re-convergence-the-summary-returns-as-a-graph-node)); the continue-path goes
to the next stage:

| stage | continue port → next stage | result port (→ `results-summary`) |
|---|---|---|
| `filter` | `keep` | `skip` (`TestResult.skip`, `type_=SKIP`) |
| `gate-pre` | `go` | `stop` (`TestResult.early_stop`, `type_=EARLY_STOP`) |
| `cc-int` | `ok` | `fail` (`TestResult.compile_fail`, `type_=COMPILE_FAIL`) |
| `gate-comp` | `go` | `stop` (`TestResult.early_stop`, `type_=EARLY_STOP`) |
| `sim-int` | `ok` | `timeout` (`TestResult.sim_timeout`, `type_=SIM_TIMEOUT`) |
| `gate-sim` | `go` | `stop` (`TestResult.early_stop`, `type_=EARLY_STOP`) |
| `route-post` | `uvm` → `parse-uvm-log`, `plain` → `parse-log` | — (classifier only) |
| `parse-log` | — | `result` (PASS/FAIL/NA) |
| `parse-uvm-log` | — | `result` (PASS/FAIL/NA) |

Because a terminal item leaves the main line, **no downstream stage ever sees it** — which
is why no module needs an "am I already done?" guard. Choosing the port is ordinary
business logic (`rc == 0`, `level out of range`, `rc is None`), expressed as a named-port
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
`EndSentinel` through the rest of the pipeline; no terminal site fires, so `results-summary`
receives zero `TestResult`s and its `finalise()` is a no-op.

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

## Re-convergence: the summary returns as a graph node

> **Redesigned twice.** TODO #15 (2026-06-10) first retired the original `fan-in-results` relay +
> `aggregate-results` sink in favour of an out-of-graph **logging plugin** (`SummaryProcessor`),
> on the argument that rendering is not a termination concern. Spec [10d](specs/10d-summarise-results.md)
> (2026-06-25) **returns the summary to the graph** as a single `results-summary` node: the plugin
> made the summary's data path invisible (a scrape of the logging chain), where a node makes it an
> explicit edge fan-in. The new topology does **not** reintroduce the relay+sink pair — the `any`
> contract fans the 13 result ports **directly** into one accumulating sink, so there is one node,
> not two, and still no designated termination node. The `SummaryProcessor` is retired to dormant
> infra ([10c](specs/10c-summary-handler.md), kept but unwired).

The 13 result ports re-converge at **`results-summary`** (spec [10d](specs/10d-summarise-results.md)).
Each terminal node does two things at its emission site:

1. **emits its `TestResult` on its named output port** — now **wired** by an edge to a distinct
   `results-summary` contract port. The `TestResult` carries `test_name` (the test's `get_name()`,
   the summary's first column), so the node reads it straight off the payload. No module signature
   or `definite_emits` change: the module stays graph-agnostic and does not know that
   `results-summary` listens.
2. **logs its outcome for the exit code** — independent of the table. The failure terminals
   (`compile_failed`, `sim_timeout`, the config-domain `model_*`/`sweep_*`/`preproc_*`/`filelist_*`/`replay_seed_*`, and `parse-log`/`parse-uvm-log` on
   FAIL/NA) `log.error` once, the sole deferred-exit driver; the pass-like terminals
   (`parse-*` on PASS, `filter.skip`, `early-stop-gate`) `log.info` or are silent. These logs no
   longer feed the table — the row comes from the fanned-in `TestResult`.

A `git-status` setup node calls `log.info("git_state", branch=..., sha=..., dirty=...)` once at
run start; it is **not** a terminal and does not reach `results-summary` — it prints to the console
at run start like any other log line. The summary node's role is **outcomes only**: it renders the
`TestResult`s fanned into it and nothing else.

The fan-in is owned by the **`any` contract** ([spec 02](specs/02-any-contract-and-fan-in.md)); the
node + 13 edges + `contract_port_mappings` are specified in [10d](specs/10d-summarise-results.md)
and wired in [06](06-graph-yaml.md). The node's `finalise()` renders the consolidated PASS/FAIL/NA
table once at run end (after the gather, before the failure check), so it renders whether the run
passed or failed-deferred, and **emits the plain table on a single `table` output port**. That port
fans out to two sink nodes — `print-summary` (console, colourises verdict tokens on a TTY,
[10e](specs/10e-print-summary.md)) and `write-summary-log` (`rtl_buddy.log`, plain,
[10f](specs/10f-write-summary-log.md)) — the in-graph form of rtl_buddy's `logger.result`, whose one
emit fans to a colourised console handler and a plain log-file handler. The summary node renders
**once** and stays atomic (accumulate + render + emit); the two sinks each carry one rendering
responsibility.

### The `SummaryProcessor` logging plugin

> **Dormant (since spec [10d](specs/10d-summarise-results.md)).** `SummaryProcessor` is retained as
> reference/standby infra but is **dropped from `test.yaml`'s `logging` block** — the in-graph
> `results-summary` node ([10d](specs/10d-summarise-results.md)) now renders the table from the
> fanned-in payloads. The plugin's table-render parity (header, column widths, verdict colourisation)
> is **shared** with the node; the difference is only the data path (a logging-chain scrape vs. a
> visible edge fan-in). The description below records the dormant plugin's shape; [10c](specs/10c-summary-handler.md)
> owns it.

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

Why it was a processor and not a handler: the processor *class* holds state across events, sits
before `ConsoleRenderer` to intercept-and-accumulate result events, and uses `DropEvent` — a
processor-only mechanism — to suppress their per-event lines in the *same* object.
`finalise()` is the per-run teardown hook the harness invokes at run end, **before** the failure
check (`docs/logger/implementation.md` — "End-of-run finalisation with `finalise()`", extended to
processors per [07 item 27](07-ambiguities-and-assumptions.md)). It was wired per-graph in
`graphs/test.yaml`'s `logging` block; [10d](specs/10d-summarise-results.md) drops that wiring.

### The CRITICAL path

On a `CRITICAL` record `LoggingFatalHandler` raises `typer.Exit(1)` and the run aborts before
the per-run teardown runs, so `finalise()` is never reached and no table renders. This is
acceptable: `CRITICAL` paths (missing/malformed config, builder/testbench resolution) abort
before any test result exists, and the `if not self._rows: return` guard keeps `finalise()` a
no-op whenever there is nothing to summarise.

### One node, not a relay+sink pair

The graph still needs **no designated termination node**. `graph.py` gathers **all** node
coroutines (`runs = [node.run() for node in graph.nodes.values()]; await asyncio.gather(*runs)`),
not a designated sink; each node terminates when its contract returns `EndSentinel`. The original
`fan-in-results` relay existed only to merge the 13 streams before an `aggregate-results` sink —
two nodes for one rendering concern. `results-summary` collapses that to **one**: the `any`
contract *is* the fan-in (it fires on whichever terminal is ready and ends when all 13 end), so it
delivers straight into the accumulating sink with no relay in between. `finalise()` is the
rendering callsite after all results arrive — a *rendering* concern the node owns, not a
*termination* one. `git-status` stays a plain `log.info` from a setup node (no graph routing), and
any future cross-cutting run metadata that is genuinely per-run-singular (timing, platform,
invocation timestamp) can stay a log event; per-*test* outcomes belong on the fan-in.

### The `any` contract (fans the terminals into `results-summary`)

The general-purpose **`any` contract** (fire on whichever port is ready first, one delivery
per call, end when all ports end) backs the `results-summary` fan-in: its 13 input ports are the
terminal `TestResult` edges, and `contract_config: { mapping: result }` funnels every one onto the
`result` output port so the sink module sees one `TestResult` per `run`. The contract stays
graph-agnostic and reusable; its sketch, invariants, and tests live in
[spec 02](specs/02-any-contract-and-fan-in.md), the node wiring in
[spec 10d](specs/10d-summarise-results.md); correctness review is
[07 item 20](07-ambiguities-and-assumptions.md). (It briefly also hosted the interim
parallel-safety shim's `release_lock` hook; that shim was removed entirely by TODO #30 in favour
of per-tag artefact naming — see
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
test.get_name())` and derives per-tag paths, so most artefacts are already isolated:

| artefact | producer | naming | status |
|---|---|---|---|
| `obj_dir_<tag>/` | `build-compile-cmd` (`--Mdir`) | `str(Path(work_dir) / f"obj_dir_{test_tag}")` | per-tag + `work_dir`-rooted (R14) |
| verilator `simv` | compile | `f"{work_dir}/obj_dir_{test_tag}/simv"` | per-tag + `work_dir`-rooted (R14) |
| compile/sim `.log`/`.err` | `run-process` | `f"{logs_dir}/{test_tag}…"` | already per-tag |
| `.randseed` | `write-randseed` | `f"{logs_dir}/{test_tag}…"` | already per-tag |
| **`run.f`** | **`write-filelist`** | **was literal `run.f` → now `Path(work_dir) / f"run.{test_tag}.f"`** | **fixed by (B) + `work_dir`-rooted (R14)** |

Change (B) is the filelist naming: `write-filelist` writes `run.{test_tag}.f` and emits that
`Path` on its `filelist` port; `build-compile-cmd` already passes `filelist.value` to `-f`,
so no edge or downstream change is needed. `write-filelist` reverts to the plain `default`
contract. On top of (B), R14 roots `run.f` and `obj_dir_<tag>/` on `work-dir`'s `work_dir`
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

The exit code and the summary are produced by two cooperating mechanisms:

1. **Exit code** is driven by `log.error` at **two layers**. *At origin*, each failure terminal
   emits its own `log.error` with a **per-case event name** and rich domain context
   (`compile_failed`, `sim_timeout`, the config-domain `model_*`/`sweep_*`/`preproc_*`/`filelist_*`/`replay_seed_*`, and the parse
   terminals' `parse_log_*`/`parse_uvm_*`); FAIL and genuine NA (parse unknown) each fire once.
   *At the summary*, `results-summary.finalise()` emits one consolidated
   `log.error("test_failures", count=…)` if the rendered table holds any FAIL row. Either layer
   sets `handler.failure = True` → exit 1, reproducing `rtl_buddy`'s `exit_code |= 0 if is_pass()
   else 1` (`rtl_buddy/src/rtl_buddy/rtl_buddy.py:206`). SKIP/PASS log only at INFO and contribute
   nothing. **`early-stop` is the one exception**: its result is NA but it emits
   no `log.error` (a user-requested stop is not a failure), and an early-stop NA is **not** a FAIL row, so the consolidated
   check skips it too — a user-requested stop exits 0, a deliberate divergence from rtl_buddy's
   exit 1 (see [07 — Notable divergences](07-ambiguities-and-assumptions.md#notable-divergences-from-rtl_buddy)).
2. **Summary table** is rendered by **`results-summary.finalise()`** (spec
   [10d](specs/10d-summarise-results.md)) from the 13 terminal `TestResult`s fanned into it by the
   `any` contract — see
   [Re-convergence](#re-convergence-the-summary-returns-as-a-graph-node) — reproducing
   `do_cmd_test`'s "Test Results Summary" loop (`rtl_buddy/src/rtl_buddy/rtl_buddy.py:203-207`), and
   **emitted on `table`** to the console sink ([10e](specs/10e-print-summary.md)) and the
   `rtl_buddy.log` sink ([10f](specs/10f-write-summary-log.md)); the same `finalise()` then emits the
   consolidated FAIL error (layer 2 above). The node renders **outcomes only**; the `show_git_rev` git
   state (`rtl_buddy.py:500-522`) is logged separately by `git-status` and falls through to the console
   at run start, not into this table.

`CRITICAL` stays reserved for harness-fatal conditions (missing/malformed `root_config.yaml`,
missing builder/testbench), matching `rtl_buddy`'s `logger.critical` → `typer.Abort`
(e.g. `rtl_buddy/src/rtl_buddy/config/root.py:89`, `config/platform.py:67-83`).

## Log idioms per failure site

Each module and contract that can fail records its idiom here. The **summary row** for every
terminal comes from the `TestResult` it emits on its (now wired) output port → `results-summary`
(spec [10d](specs/10d-summarise-results.md)) — `test_name` (the test's `get_name()`, the summary's
first column) rides the payload. Independently, each terminal **logs** under a **per-case event
name** (no terminal uses the generic `test_result`, which is retired) for the exit code; a
success / skip / stop outcome is recorded by its `TestResult` alone, not logged. The rows below list each site's idiom, per `docs/invariants.md:14-23` and
`docs/harness/logging.md`:

- **`log.fatal`** — immediate `SystemExit(1)`. Reserved for unrecoverable setup/config
  failures and harness-internal scheduling errors.
- **Wired `result` port → `results-summary`** — the terminal outcome is returned on the module's
  named output port (`skip`, `stop`, `fail`, `timeout`, `result`), now wired by an edge to a
  distinct `results-summary` contract port; the fanned-in `TestResult` is the summary row. The
  module stays graph-agnostic and does not know the sink listens.
- **`log.error` at origin (per-case)** — each failure terminal fires once under its own descriptive
  event name (`compile_failed`, `sim_timeout`, `model_*`/`sweep_*`/`preproc_*`/`filelist_*`/`replay_seed_*`, `parse_log_*`,
  `parse_uvm_*`) with rich domain context; a deferred-exit driver (`handler.failure`), independent
  of the summary row (which rides the payload).
- **`TestResult` records the outcome** — a `TestResult`-producing terminal logs only the errors it
  encounters; a PASS / SKIP / early-stop is carried solely by the `TestResult` it emits (the summary row).
- **Consolidated `log.error("test_failures", count=…)`** — `results-summary.finalise()` fires once
  if the rendered table holds any FAIL row; the summary-level exit signal, additional to the
  per-case origin errors.

### Setup / config — `log.fatal`

| Site | Failure |
|---|---|
| `discover-config-file` | `root_config.yaml` not found walking up CWD |
| `parse-root-config` | malformed YAML / schema mismatch |
| `select-platform` | no platform's `unames` matches |
| `resolve-builder` | named builder missing on platform |
| `parse-suite-config` | resolved `test_config` is missing/malformed (it resolves the locator against CWD and opens it — `-c <dir>/tests.yaml` is supported, just CWD-relative); testbench bind failure |
| `select-tests` | named test not in suite |
| `run-process` | subprocess launch failure (binary not on PATH, permission denied) — distinct from non-zero `rc`, which is per-test |

### Per-test failure — `result` port → `results-summary` + per-case `log.error` at origin

Each row below emits its `TestResult` on its wired port (→ `results-summary`, the summary row) and
`log.error`s once — an exit driver, alongside the consolidated `results-summary.finalise()` FAIL
check. The single-failure-mode sites (`interpret-compile`/`interpret-sim`) log one event; the
config-domain sites catch **each exception class in its own `except`**, one event per class
(mirroring `io.py`). Every log carries **exception-specific** fields (`rc`/`stderr_path`/`errno`/
`strerror`/`reason`/`path`) — **never** `result`/`desc` (those are the fanned-in payload's, the
summary row).

| Site | Port → payload (→ `results-summary`) | Emission log(s) (exit driver) — per-exception event names |
|---|---|---|
| `interpret-compile.fail` | `fail` → `TestResult.compile_fail` (`type_=COMPILE_FAIL`) | `log.error("compile_failed", rc, stderr_path)` (single failure mode: `rc != 0`) |
| `interpret-sim.timeout` | `timeout` → `TestResult.sim_timeout` (`type_=SIM_TIMEOUT`) | `log.error("sim_timeout", err)` (single failure mode: `rc is None`) |
| `load-model.fail` | `fail` → `TestResult.prep` (`type_=PREP`) | per-exception: `model_file_not_found` / `model_is_directory` / `model_permission_denied` / `model_invalid_unicode` / `model_read_error` / `model_parse_error` / `model_not_found` (`model_path` + `err`/`errno`/`reason`/`model`) |
| `write-filelist.fail` | `fail` → `TestResult.prep` (`type_=PREP`) | per-exception: `filelist_dir_not_found` / `filelist_is_directory` / `filelist_permission_denied` / `filelist_write_error` / `filelist_resolve_error` (`path` + `err`/`errno`) |
| `expand-sweep.fail` | `fail` → `TestResult.prep` (`type_=PREP`) | per-phase: `sweep_script_not_found` / `sweep_script_permission` / `sweep_script_read_error` (read), `sweep_script_error` (exec, `exc_info`), `sweep_output_invalid` (fan-out) |
| `run-preproc.fail` | `fail` → `TestResult.prep` (`type_=PREP`) | per-phase: `preproc_script_not_found` / `preproc_script_permission` / `preproc_script_read_error` (read), `preproc_script_error` (exec, `exc_info`) |
| `resolve-seed.fail` (REPLAY only) | `fail` → `TestResult.prep` (`type_=PREP`) | per-exception: `replay_seed_not_found` / `replay_seed_malformed` / `replay_seed_permission` (`path` + `err`) |

Parse FAIL/NA verdicts (`parse-log`/`parse-uvm-log`) are in the next table — for the exit they
log their per-case events directly (`parse_log_*`/`parse_uvm_*`). Topology consequence: all 13 result ports are **wired** to
`results-summary` (spec [10d](specs/10d-summarise-results.md)). Adding a new failure terminal adds
one edge to a new `results-summary` contract port (declared in its `contract_port_mappings`) and a
`log.error` for the exit.

**Side-effect-leaf deferred failure (no verdict row).** `write-randseed` (spec [08d](specs/08d-write-randseed.md)) is **not** a terminal and carries no result verdict — the test's PASS/FAIL comes from `parse-log`. But it can fail at its own I/O (an `OSError`/`FileNotFoundError` writing `.randseed`, or a missing `HierInstanceSeed.txt` when the argv asks for it), which it **catches** and logs as `log.error("randseed_write_failed", key, path, exc_info)` — a deferred-exit driver (it flips `handler.failure`) but **not** a terminal, so it emits no `TestResult` to `results-summary`: it forces a non-zero exit without adding a summary row. The module still emits `randseed_done` regardless so `link-latest`'s join cannot dangle. This is the module catching its own error rather than leaning on the harness backstop (which is a fallback, not a contract).

### Per-test terminals that log their verdict directly (the otherwise-silent paths)

These have no prior log event. A non-pass verdict logs its per-case event with `log.error`
(drives the exit); a PASS / SKIP / early-stop is recorded by its `TestResult` only. The summary row
rides the `TestResult` fanned into `results-summary`.

| Site | Port → payload (→ `results-summary`) | Emission log (per-case event) |
|---|---|---|
| `parse-log.result` | `default` → `TestResult.parse` (PASS/FAIL/NA) | `log.error("parse_log_failed"/"parse_log_unknown", …)` on FAIL/NA (exit driver); `log.error("parse_log_unreadable", …)` on an I/O error; a PASS is not logged |
| `parse-uvm-log.result` | `default` → `TestResult.parse` (PASS/FAIL/NA) | `log.error("parse_uvm_failed"/"parse_uvm_no_summary"/"parse_uvm_invalid_summary", …)` on FAIL (exit driver); `log.error("parse_uvm_unreadable", …)` on an I/O error; a PASS is not logged |
| `filter-reglvl.skip` | `skip` → `TestResult.skip` (`type_=SKIP`) | not logged (a skip is not an error; no exit contribution) |
| `early-stop-gate.stop` (×3) | `stop` → `TestResult.early_stop` (`type_=EARLY_STOP`) | not logged *(NA, but not an error — a user-requested stop exits 0; deliberate divergence from rtl_buddy's exit 1, see [07 — Notable divergences](07-ambiguities-and-assumptions.md#notable-divergences-from-rtl_buddy))* |

### Summary rendering + consolidated exit — `results-summary.finalise()`

| Site | Trigger | Action |
|---|---|---|
| `results-summary.finalise()` | run end (node teardown), if any `TestResult` fanned in | render the consolidated **results** table (plain) from the fanned-in payloads and **emit it on `table`** to the two sinks ([10e](specs/10e-print-summary.md) console, [10f](specs/10f-write-summary-log.md) `rtl_buddy.log`), then `log.error("test_failures", count=…)` if any FAIL row (the consolidated exit signal — layered over the per-case origin errors) |
| `git-status` (setup) | run start | `log.info("git_state", branch=..., sha=..., dirty=...)` once; falls through to the console (not a terminal, so not fanned into `results-summary`) |

### Deferred

| Site | Failure | Status |
|---|---|---|
| `parse-log` / `parse-uvm-log` | parse-machinery exception distinct from FAIL classification (log file missing; regex raises on malformed content) | Deferred pending TODO #13 (VlogPost quirks: replicate vs fix) |
