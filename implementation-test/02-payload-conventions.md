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

The key exists so the `keyed_join` nodes can correlate a node's inputs back to the test
they came from. Under the split it appears on **every** main-line edge (all are `{key, …}`
dicts) — each `keyed_join` reads `payload["key"]` to match its ports. Modules copy it
forward; they never parse or branch on it.

## Shape 1 — the split per-test/per-run edges (`{key, value}`)

There is **no `ctx` bag**. Per-test data rides the main line as **separate keyed edges**, each a `{key, value}` dict — the port/edge name says what `value` is:

```python
test    = { "key": "alu_smoke#0#0", "value": <TestConfig> }  # select → … → parse-*  (the long-lived edge)
simv    = { "key": k, "value": <str> }                       # build-compile-cmd → … → build-sim-cmd, then dies
run_id  = { "key": k, "value": int | None }                  # expand-runs → … → build-sim-cmd, then dies
seed    = { "key": k, "value": int }                         # resolve-seed → build-sim-cmd, then dies
timeout = { "key": k, "value": float | None }                # build-sim-cmd → sim-run
filelist= { "key": k, "value": <Path> }                      # write-filelist → build-compile-cmd
```

- **`key`** is the synthesized correlation string, stamped/re-suffixed at the fan-outs (`select`→`name`, `sweep`→`name#i`, `expand-runs`→`name#i#run`). Every edge carries it so `keyed_join` nodes correlate ports by it. Nothing intrinsic to `test`/`simv` is unique post-fan-out (names collide across sweep variants and run-ids; `simv` is a shared/fixed string), so the explicit synthesized key is required.
- **`value`** is the generic single-value slot: the edge name conveys the type, so the field is just `value` (`test["value"]` is the `TestConfig`, `simv["value"]` the simv path, …). *Multi-field* cohesive messages (`proc`, `command`, `randseed`) keep named fields instead (Shape 2).
- **Edge lifetimes are bounded and visible:** `test` threads the whole pipeline; `simv` lives `[build-compile-cmd, build-sim-cmd]`; `run_id` `[expand-runs, build-sim-cmd]`; `seed` `[resolve-seed, build-sim-cmd]` — `simv`/`run_id`/`seed` all die at `build-sim-cmd`.
- **`test["value"]` is the live `TestConfig`**, mutated in-place by `run-preproc`/`expand-sweep`; `.model` attached by `load-model`. These reimplement rtl_buddy `TestConfig` (`config/test.py:43-302`) and `ModelConfig` (`config/model.py:9-51`); renames pinned in specs [01b](specs/01b-suite-schema.md)/[01c](specs/01c-model-schema.md). The `seed_mode` payload is the `SeedMode` enum (`seed_mode.py:4-7`).
- **No `result` field, ever.** Terminal outcomes leave as Shape-3 result edges.
- **Why split, not bagged:** the per-field edges expose true data dependencies (each node's inputs = exactly what it reads) and let `keyed_join` correlate by key rather than relying on lockstep arrival order. Config singletons (`builder_cfg`, `logs_dir`, …) reach the command-builders as `persistent_inputs` on those same `keyed_join` nodes. Full rationale + the node/contract/edge table + edge-wiring list: [`06-graph-yaml.md`](06-graph-yaml.md).

## Shape 1b — `test_run`: dissolved

There is **no post-sim bag**. The split runs all the way through. After `run-process` (sim), the post-sim region consumes the `test` edge + `proc` (the subprocess result — it echoes the sim log/err paths as `stdout_path`/`stderr_path`) + `randseed`, joined by key. `write-randseed` **no longer assembles a `test_run` record** — it is a side-effect leaf (write the seed file, emit a `randseed_done` ordering signal). The post-sim region is **two parallel branches off `proc`**:

- **side-effects:** `write-randseed` (writes `.randseed`; emits `randseed_done`) → `link-latest` (forces the `test.*` symlinks; terminal).
- **classification:** `interpret-sim` → `gate-sim` → `route-post` → `parse-log` / `parse-uvm-log`, each `keyed_join`ing `test` + `proc`.

`run_id` is **dead post-sim** (it survives only in the `key` suffix and the already-composed paths), so it is not carried past `build-sim-cmd`. Removing the assembly was the atomicity fix — `write-randseed`'s function is "persist the seed record", not "build the result bundle".

## Shape 2 — multi-field cohesive messages

Payloads produced whole by one node for specific consumers, carrying the key so a `keyed_join` can match. These keep **named fields** (not the `{key, value}` slot) because each is one cohesive message with several parts produced in one shot:

```python
command  = { "key": k, "argv": [ ... ],                      # build-*-cmd     → run-process
             "stdout_path": Path, "stderr_path": Path }
proc     = { "key": k, "rc": int, "timed_out": bool,         # run-process     → interpret-* (and, sim leg,
             "stdout_path": Path, "stderr_path": Path }       #                   → write-randseed gate + link-latest)
randseed = { "key": k, "seed": int, "randseed_path": Path,   # build-sim-cmd   → write-randseed + link-latest
             "argv": [ ... ] }                                #                   (argv: the hier_inst_seed check)
randseed_done = { "key": k }                                 # write-randseed  → link-latest (ordering signal only)
```

`proc` echoes the redirect paths (`stdout_path`/`stderr_path` = the sim log/err), so the post-sim parsers read the log from `proc` — there is no separate `sim_cmd` bag (its parts became `command` + `randseed`). Single-value edges (`filelist`, `seed`, `timeout`) use the `{key, value}` form (Shape 1). These never accumulate; each is consumed by exactly the next stage(s).

## Shape 3 — result payloads (terminal; port unwired, row logged)

The single shape every terminal output port emits, regardless of which stage produced it:

```python
result = { "key": k, "result": <TestResults> }
```

Emitted on a stage's terminal port (`skip`, `stop`, `fail`, `timeout`, `result`). Since the
TODO #15 redesign these ports are **unwired** — there is no `aggregate-results` collector.
Each terminal additionally **logs its outcome**, and the per-graph `SummaryProcessor` plugin
collects those log events (via a configured watch-list) and renders the table. Two emission
styles, both carrying `test_name`/`key`/`result`/`desc` (`test_name` = the test's `get_name()`,
rendered as the summary's first column for rtl_buddy parity; `key` is retained for correlation):

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
  `test_name`/`result`/`desc` kwargs to their existing call; `SummaryProcessor`'s `Config`
  watch-list lists those event names, so no parallel `test_result` is emitted for them.

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
is NA (and `rtl_buddy` exits 1 on `--early-stop`), but this plan treats a user-requested stop as a
non-failure and exits 0. This is the one deliberate exit-code divergence
([07 — Notable divergences](07-ambiguities-and-assumptions.md#notable-divergences-from-rtl_buddy)).
A genuine NA verdict from `parse-log`/`parse-uvm-log` still drives exit 1.

## Sentinels

`EndSentinel` (handled entirely by contracts) is the only sentinel. No `GroupEnd` or
`BranchSkip` is used: branches are mutually exclusive, and since the TODO #15 redesign the
terminal ports are unwired (no re-convergence). The test graph's contracts are `unit` /
`default` / `keyed_join` (plus an unwired `any`); there is no `merge` contract.
