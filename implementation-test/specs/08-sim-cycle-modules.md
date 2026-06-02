# Spec 08: Sim-cycle modules

**Depends on:** spec 03 (run-process), spec 07 (compile cycle), spec
[01a](01a-builder-schema.md) (`ResolveSeedMod` and `BuildSimCmdMod` consume
`RtlBuilderConfig` methods), spec [01b](01b-suite-schema.md) (`BuildSimCmdMod` reads
`ctx["test"].get_timeout()`, `get_plusargs()`, `get_plusdefines()`).
**References:** [03 — Run expansion + Simulation sections](../03-module-catalog.md), [04 — keyed_join paragraph](../04-pipeline-and-contracts.md).

## Goal

Build the per-run simulate leg: fan out per run-id, resolve the seed, assemble the sim
argv (with log paths in `command` and `seed`/`log` folded into `ctx`), run the subprocess,
then write `.randseed` (the second keyed_join), force the `test.*` symlinks, and route
on timeout.

## Deliverables

In `modules/rtl_test/sim.py`:

- `ExpandRunsMod` — `(ctx, run_ids:list=[None])` → generator yielding one `ctx` per
  `run_id` (key suffixed `#run`, `run_id` recorded in `ctx`).
- `ResolveSeedMod` — `(ctx, seed_mode, builder_cfg, logs_dir:str="logs")` → integrated
  seed-producer for all three modes:
  - `NEW` → `random.randrange(1_000_000)`
  - `DEFAULT` → `builder_cfg.get_seed()`
  - `REPLAY` → reads `f"{logs_dir}/{test_name}[_{run_id:04d}].randseed"` (uses
    `ctx["run_id"]` for the suffix; `logs_dir` is a persistent input fed by `--logs-dir`,
    default `"logs"`, matching rtl_buddy `tools/vlog_sim.py:199-203`); on
    missing/malformed file, emit `("fail", {"key", "result": <FAIL payload>})` and call
    `log.error` at emission with the attempted path. See
    [05 — Log idioms](../05-branching-and-results.md#log-idioms-per-failure-site).
  Emits in lockstep on success: `("ctx", ctx)`, `("seed", {"key", "seed"})`; on REPLAY
  failure: `("fail", result)`.
  **Failure handling**: REPLAY only — catch `(FileNotFoundError, ValueError)` around the
  `int(open(path).readline().strip())` parse (exactly matches
  `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:200-203`). `PermissionError` also possible;
  include in the catch. FAIL payload's `desc` is `f"Replay seed missing or invalid at
  {path}"` (rtl_buddy parity, `vlog_sim.py:203`). `NEW` and `DEFAULT` modes have no
  failure path.
- `BuildSimCmdMod` — `(ctx, seed, builder_cfg, builder_mode, logs_dir:str="logs")` → assembles
  `[simv_path] + builder_cfg.get_run_time_opts(builder_mode, seed=seed["seed"]) + plusdefines + plusargs`,
  where `simv_path` is `ctx["simv"]` (already resolved by `build-compile-cmd` honouring
  the spec [01a — Verilator quirk](01a-builder-schema.md): `f"{build_dir}/simv"` for
  verilator, `builder_cfg.get_simv()` otherwise). `get_run_time_opts` appends
  `builder_cfg.sim_rand_prefix + str(seed)` internally — do **not** add the seed
  separately. `plusdefines` is built from `ctx["test"].get_plusdefines()` exactly as in
  `BuildCompileCmdMod` (spec [07](07-compile-cycle-modules.md)); `plusargs` is built
  from `ctx["test"].get_plusargs()` (spec [01b](01b-suite-schema.md) — returns `dict |
  None`; when not `None`, format each entry as `f"+{k}={v}"` or `f"+{k}"` for `v is
  None`, mirroring `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:95-105`). Computes
  `(timeout, is_custom) = ctx["test"].get_timeout()` (spec [01b](01b-suite-schema.md)
  — `(self.timeout, True)` if a per-test override is set, else `(60, False)`); the
  `timeout` value (an `int` seconds) is emitted as a `float | None`. Log paths are
  `f"{logs_dir}/{test_name}[_{run_id:04d}].log"`/`.err` (default `logs/...`, matching
  rtl_buddy; `logs_dir` is a persistent input fed by `--logs-dir`). Also composes
  `randseed_path = f"{logs_dir}/{test_name}[_{run_id:04d}].randseed"` and folds it into
  `ctx` so the downstream `keyed_join` (`write-randseed`) carries the path without
  needing a persistent config port. Does not `mkdir(logs_dir)` — `ensure-logs-dir` has
  already bootstrapped the directory via the env_ready chain. Emits in lockstep:
  `("ctx", ctx_with_seed_log_and_randseed_path)`, `("command", {"key", "argv", "stdout_path", "stderr_path"})`,
  `("timeout", float | None)`.
  **Failure handling**: `builder_cfg.get_run_time_opts(builder_mode, seed)` calls
  `log.critical` if `builder_mode` is not in `builder_cfg.opts` or the mode's
  `run_time` is `None` — see spec [01a](01a-builder-schema.md). No catching.
- `WriteRandseedMod` — `(ctx, proc)`, with `keyed_join` contract on the node; writes
  `ctx["randseed_path"]` (composed by `build-sim-cmd` from `logs_dir` + `test_name` +
  `run_id`; default `logs/<test>[_NNNN].randseed`) from `ctx["seed"]`
  (+ `HierInstanceSeed.txt` contents if present); folds `rc`/`timed_out` from `proc` into
  `ctx`; emits `ctx`. The directory was materialised at startup by `ensure-logs-dir`;
  this module does not `mkdir`. `logs_dir` is **not** a persistent input here —
  `keyed_join` joins every port by key and cannot carry a persistent config port (see
  [02 — Path composition](../02-payload-conventions.md) and [07 Implementation
  notes](../07-ambiguities-and-assumptions.md)), so the path is delivered through `ctx`
  instead.
- `LinkLatestMod` — `(ctx)` → force CWD symlinks `test.log`/`test.err`/`test.randseed`
  to this run's files (in the configured `logs_dir`, default `logs/`, via the paths
  already folded into `ctx` by `build-sim-cmd`); emits `ctx`. Symlinks themselves are
  always placed in CWD, matching rtl_buddy.
- `InterpretSimMod` — `(ctx)` → pure routing: `ctx["timed_out"]` → `("timeout",
  {"key", "result": SimTimeoutResults()})`, else `("ok", ctx)`.
  **Failure handling**: routing on `ctx["timed_out"]`; no Python exception is caught.
  The ERROR log at emission of `("timeout", ...)` carries `ctx["key"]`, the configured
  timeout, and the sim `stderr_path` (mirrors rtl_buddy's `vlog_sim.py` timeout reporting).

Manifest entries per [06](../06-graph-yaml.md).

Tests in `modules/tests/test_sim_cycle.py`:
- `expand-runs` defaults `[None]` → single passthrough; explicit `[1,2,3]` → 3 ctxs with
  correct keys.
- `resolve-seed` covers all three modes; REPLAY round-trips a written `.randseed`.
- `resolve-seed` REPLAY honours `logs_dir`: write `.randseed` under a custom
  `logs_dir="custom_logs"`, then resolve-seed REPLAY with the same `logs_dir` reads it
  back. The REPLAY-missing fail path quotes the `logs_dir`-prefixed path in the FAIL
  payload's `desc`.
- `build-sim-cmd` argv matches rtl_buddy `VlogSim.execute`; timeout pulled from test
  config. `stdout_path` / `stderr_path` in `command` and `log` / `randseed_path` in `ctx`
  all carry the `logs_dir` prefix (verify with default `"logs"` and a custom value).
- `write-randseed` writes to `ctx["randseed_path"]` (not a hard-coded `logs/...` path) —
  exercise with a custom `logs_dir` end-to-end. `link-latest` forces symlinks atomically
  (use `os.replace` or unlink+symlink ordering); `interpret-sim` routes timeout-vs-ok.

## Acceptance criteria

- Tests pass.
- End-to-end against a real `simv` (or fake): a passing run produces correct log/err/
  randseed files and symlinks; a sleep-and-timeout run produces `rc=4444` and
  `interpret-sim` emits `timeout`.

## Notes

`write-randseed` is the **second** `keyed_join` node (the sim-side join). It holds the
join because it's the first node needing both `ctx` (for the seed) and `proc` (for the
completion signal + rc). `link-latest` and `interpret-sim` are downstream single-source
`default` nodes; no further joins. Mirror [04 — Why each contract](../04-pipeline-and-contracts.md).
