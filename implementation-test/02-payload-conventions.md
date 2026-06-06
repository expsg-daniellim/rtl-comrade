# Payload conventions

Modules receive raw values (the harness unwraps `Payload` before calling `run`). There is
**no single payload type** threaded through the graph. Instead there are three small,
purpose-specific payload shapes, plus one correlation key.

## The correlation key

A stable string identifying one test invocation, stamped at each fan-out:

- `select` → `key = "<test_name>"`
- `sweep`  → `key = "<test_name>#<sweep_idx>"`
- `runs`   → `key = "<test_name>#<sweep_idx>#<run_id>"`

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
command  = { "key": k, "argv": [ ... ] }                     # build-*-cmd     → run-process
proc     = { "key": k, "rc": int, "stdout": bytes,           # run-process     → interpret-*
             "stderr": bytes, "timed_out": bool }
seed     = { "key": k, "seed": int }                         # resolve-seed    → build-sim-cmd
sim_cmd  = { "key": k, "seed": int, "log": Path,             # sim-build        → write-randseed
             "err": Path, "randseed_path": Path }
```

These never accumulate. Each is consumed by exactly the next stage(s).

## Shape 3 — result payloads (terminal, route to the collector)

The single shape every terminal output port emits, regardless of which stage produced it:

```python
result = { "key": k, "result": <TestResults> }
```

Emitted on a stage's terminal port (`skip`, `stop`, `fail`, `timeout`, `result`) and routed
to one port of `aggregate-results`. See [05](05-branching-and-results.md).

## `TestResults` values used at the terminal ports

Reuse `rtl_buddy.runner.test_results`:

| terminal port (node) | result | is_pass? | exit contribution |
|---|---|---|---|
| `skip` (`filter`) | `SkipResults(desc)` | yes (SKIP) | none |
| `stop` (`gate-*`) | `EarlyStopResults(desc)` | no (NA) | exit 1 |
| `fail` (`interpret-compile`) | `CompileFailResults` | no (FAIL) | exit 1 |
| `timeout` (`interpret-sim`) | `SimTimeoutResults` | no (FAIL) | exit 1 |
| `result` (`parse-log` / `parse-uvm-log`) | `TestPassResults` / FAIL / NA | PASS→yes | non-pass→exit 1 |

`TestResults.is_pass()` is the single source of truth for the exit code (SKIP counts as
pass; NA/FAIL do not), exactly as in `rtl_buddy`.

## Sentinels

`EndSentinel` (handled entirely by contracts) is the only sentinel. No `GroupEnd` or
`BranchSkip` is used: branches are mutually exclusive and re-converge through the `merge`
contract, not through `branch_aware_join`.
