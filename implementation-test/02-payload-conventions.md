# Payload conventions

Modules receive raw values (the harness unwraps `Payload` before calling `run`). There is
**no single payload type** threaded through the graph. Instead there are three small,
purpose-specific payload shapes, plus one correlation key.

## The correlation key

A stable string identifying one test invocation, suffixed at each fan-out **that actually
produces variants**:

- `select` → `key = "<test_name>"`
- `sweep`  → `key = "<test_name>#<sweep_idx>"` **per produced variant**; a test with no sweep
  script passes through with its key **unchanged** (see [spec 05f](specs/05f-expand-sweep.md))
- `runs`   → `key = "<test_name>[#<sweep_idx>]#<run_id>"` when `run_id is not None`; for the
  plain `test` command `run_ids = [None]`, so the key is **unchanged** (see
  [spec 08a](specs/08a-expand-runs.md))

The suffix is only added when the fan-out emits more than the single passthrough item; the
invariant the joins rely on is uniqueness, not a fixed `#i#run` shape.

The key exists so the two join nodes can match a subprocess result back to the test it
came from. It appears as a field only on payloads that actually enter a `keyed_join`
(the `ctx` and `proc` payloads). Modules copy it forward; they never parse or branch on it.

## Shape 1 — `ctx`: the main-line correlation record

A stable 3-field dict from `select` through the compile join (`cc-int`) and on through to
`write-randseed`:

```python
ctx = {
    "key":    "alu_smoke#0#0",  # correlation key — stamped at select/sweep/runs fan-outs
    "test":   <TestConfig>,     # mutated in-place by preproc/sweep; model attached by load-model
    "run_id": int | None,       # set by expand-runs; None for plain test (R=1)
    "simv":   <Path>,           # set by build-compile-cmd; absent on the pre-compile segment
}
```

- **One addition, at one boundary.** `build-compile-cmd` sets `simv` in `ctx` — the only
  field added after `select` creates the record. After that point no further fields are
  added. `seed`, `log`, `err`, and `randseed_path` travel as a separate `sim_cmd` keyed
  payload (Shape 2) from `sim-build` to `write-randseed`.
- **Always a dict** — `keyed_join` reads `payload["key"]` to correlate ports; `ctx`
  satisfies this at both join points (`cc-int`, `write-randseed`).
- **`ctx["test"]` is the live `TestConfig`**, mutated in-place by `run-preproc` /
  `expand-sweep`; `ctx["test"].model` carries the loaded `ModelConfig` after `load-model`.
  These reimplement rtl_buddy `TestConfig` (`rtl_buddy/src/rtl_buddy/config/test.py:43-302`)
  and `ModelConfig` (`config/model.py:9-51`); the Plan B field renames are pinned in
  specs [01b](specs/01b-suite-schema.md) / [01c](specs/01c-model-schema.md). The `seed_mode`
  payload is the `SeedMode` enum (`rtl_buddy/src/rtl_buddy/seed_mode.py:4-7`).
- **No `result` field, ever.** Terminal outcomes leave as Shape-3 payloads, removing the
  need for any guard inside modules.
- Modules forward `ctx` unchanged on their continue-port and read only the fields they use.

## Shape 1b — `test_run`: the post-sim context record

Assembled once by `write-randseed` (the sim-side join) from `ctx`, `proc`, and `sim_cmd`.
Replaces `ctx` as the main payload from `write-randseed` onward: `link-latest` →
`sim-int` → `gate-sim` → `route-post` → `parse-log` / `parse-uvm-log`:

```python
test_run = {
    "key":          "alu_smoke#0#0",
    "test":         <TestConfig>,
    "run_id":       int | None,
    "rc":           int,
    "timed_out":    bool,
    "log":          <Path>,         # sim .log path (parse-log / parse-uvm-log / link-latest)
    "err":          <Path>,         # sim .err path (link-latest)
    "randseed_path":<Path>,         # .randseed path (link-latest)
}
```

Assembled once at `write-randseed`; no downstream node adds to it.

## Shape 2 — work payloads (local, single-hop)

Values produced by one stage for the next, carrying the key so a downstream join can match:

```python
filelist = { "key": k, "filelist": <Path> }                 # write-filelist  → build-compile-cmd
command  = { "key": k, "argv": [ ... ],                      # build-*-cmd     → run-process
             "stdout_path": Path, "stderr_path": Path }
proc     = { "key": k, "rc": int, "timed_out": bool,         # run-process     → interpret-*
             "stdout_path": Path, "stderr_path": Path }
seed     = { "key": k, "seed": int }                         # resolve-seed    → build-sim-cmd
sim_cmd  = { "key": k, "seed": int, "log": Path,             # sim-build        → write-randseed
             "err": Path, "randseed_path": Path, "argv": [ ... ] }
```

These never accumulate. Each is consumed by exactly the next stage(s).

## Shape 3 — result payloads (terminal; port unwired, row logged)

The single shape every terminal output port emits, regardless of which stage produced it:

```python
result = { "key": k, "result": <TestResults> }
```

Emitted on a stage's terminal port (`skip`, `stop`, `fail`, `timeout`, `result`). Since the
TODO #15 redesign these ports are **unwired** — there is no `aggregate-results` collector.
Each terminal additionally **logs its outcome**, and the per-graph `SummaryProcessor` plugin
collects those log events (via a configured watch-list) and renders the table. Two emission
styles, both carrying `key`/`result`/`desc`:

- **`test_result` directly** — the result-producing terminals that would otherwise log nothing
  (`parse-log`/`parse-uvm-log` on PASS/NA/FAIL, `filter.skip`, `early-stop-gate`) call
  `log.info("test_result", …)` (pass-like) or `log.error("test_result", …)` (non-`is_pass()`,
  which also drives the exit). The `early-stop-gate` pattern. **Exception:** `early-stop-gate`
  always uses `log.info` even though its `EarlyStopResults` is NA — a user-requested stop is not
  a failure, so it does **not** drive the exit (deliberate exit-0 divergence from rtl_buddy; see
  [07 — Notable divergences](07-ambiguities-and-assumptions.md#notable-divergences-from-rtl_buddy)).
- **A domain event the watch-list collects** — the failure terminals that already `log.error`
  (`interpret-compile`→`compile_failed`, `interpret-sim`→`sim_timeout`, and
  `load-model`/`expand-sweep`/`run-preproc`/`write-filelist`/`resolve-seed`→`*_failed`) just add
  `result`/`desc` kwargs to their existing call; `SummaryProcessor`'s `Config` watch-list lists
  those event names, so no parallel `test_result` is emitted for them.

The `<TestResults>` object is still built (for `is_pass()` classification and the logged
`result`/`desc`). See [05](05-branching-and-results.md) and [spec 10c](specs/10c-summary-handler.md).

## `TestResults` values used at the terminal ports

Reuse `rtl_buddy.runner.test_results` (`rtl_buddy/src/rtl_buddy/runner/test_results.py`):
base `TestResults` + `is_pass` at `:10-33`, `TestPassResults` `:35-42`, `CompileFailResults`
`:44-51`, `EarlyStopResults` `:53-60`, `SimTimeoutResults` `:62-69`, `SkipResults` `:71-78`.
The generic per-test FAIL (no dedicated subclass) is built via `make_fail_result(desc)` —
a base `TestResults` with `{"result": "FAIL", "desc": desc}`, defined in `results.py`
(spec [01](specs/01-shared-schema.md)) and used by `load-model`/`expand-sweep`/`run-preproc`/
`write-filelist`/`resolve-seed`/`parse-log`/`parse-uvm-log`.

| terminal port (node) | result | is_pass? | exit contribution |
|---|---|---|---|
| `skip` (`filter`) | `SkipResults(desc)` | yes (SKIP) | none |
| `stop` (`gate-*`) | `EarlyStopResults(desc)` | no (NA) | **exit 0** (deliberate divergence — see below) |
| `fail` (`interpret-compile`) | `CompileFailResults` | no (FAIL) | exit 1 |
| `timeout` (`interpret-sim`) | `SimTimeoutResults` | no (FAIL) | exit 1 |
| `result` (`parse-log` / `parse-uvm-log`) | `TestPassResults` / FAIL / NA | PASS→yes | non-pass→exit 1 |

`TestResults.is_pass()` is the single source of truth for the exit code (SKIP counts as
pass; NA/FAIL do not), exactly as in `rtl_buddy` — **except `early-stop`**: `EarlyStopResults`
is NA (and `rtl_buddy` exits 1 on `--early-stop`), but Plan B treats a user-requested stop as a
non-failure and exits 0. This is the one deliberate exit-code divergence
([07 — Notable divergences](07-ambiguities-and-assumptions.md#notable-divergences-from-rtl_buddy)).
A genuine NA verdict from `parse-log`/`parse-uvm-log` still drives exit 1.

## Sentinels

`EndSentinel` (handled entirely by contracts) is the only sentinel. No `GroupEnd` or
`BranchSkip` is used: branches are mutually exclusive, and since the TODO #15 redesign the
terminal ports are unwired (no re-convergence). The test graph's contracts are `unit` /
`default` / `keyed_join` (plus an unwired `any`); there is no `merge` contract.
