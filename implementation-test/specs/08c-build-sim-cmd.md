# Spec 08c: build-sim-cmd (`BuildSimCmdMod`)

**Depends on:** spec 03 (run-process), spec 07 (compile cycle — `ctx["simv"]`), spec
[01a](01a-builder-schema.md) (`BuildSimCmdMod` consumes `RtlBuilderConfig` methods), spec
[01b](01b-suite-schema.md) (`BuildSimCmdMod` reads `ctx["test"].get_timeout()`,
`get_plusargs()`, `get_plusdefines()`).
**References:** [03 — Simulation section](../03-module-catalog.md). Parent index:
[08 — Sim-cycle modules](08-sim-cycle-modules.md).

## Goal

Assemble the per-run sim argv (with log paths in `command` and `seed`/`log`/`randseed_path`
carried in `sim_cmd`) and the timeout.

## Deliverables

In `modules/rtl_test/sim.py`:

- `BuildSimCmdMod` — `(ctx, seed, builder_cfg, builder_mode, logs_dir:str="logs")` → assembles
  `[simv_path] + builder_cfg.get_run_time_opts(builder_mode, seed=seed["seed"]) + plusdefines + plusargs`,
  where `simv_path` is `ctx["simv"]` (set by `build-compile-cmd` — see spec
  [07a](07a-build-compile-cmd.md) and spec [01a — Verilator quirk](01a-builder-schema.md)). `get_run_time_opts`
  appends `builder_cfg.sim_rand_prefix + str(seed)` internally — do **not** add the seed
  separately. `plusdefines` is built from `ctx["test"].get_plusdefines()` exactly as in
  `BuildCompileCmdMod` (spec [07a](07a-build-compile-cmd.md)); `plusargs` is built
  from `ctx["test"].get_plusargs()` (spec [01b](01b-suite-schema.md) — returns `dict |
  None`; when not `None`, format each entry as `f"+{k}={v}"` or `f"+{k}"` for `v is
  None`, mirroring `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:95-105`). Computes
  `(timeout, is_custom) = ctx["test"].get_timeout()` (spec [01b](01b-suite-schema.md)
  — `(self.timeout, True)` if a per-test override is set, else `(60, False)`); the
  `timeout` value (an `int` seconds) is emitted as a `float | None`. Log paths are
  `f"{logs_dir}/{test_name}[_{run_id:04d}].log"`/`.err` (default `logs/...`, matching
  rtl_buddy; `logs_dir` is a persistent input fed by `--logs-dir`). Also composes
  `randseed_path = f"{logs_dir}/{test_name}[_{run_id:04d}].randseed"`. These paths are
  emitted in `sim_cmd` (not folded into `ctx`) so `write-randseed` receives them as a
  dedicated keyed port. Does not `mkdir(logs_dir)` — `ensure-logs-dir` has already
  bootstrapped the directory via the env_ready chain. Emits in lockstep:
  `("ctx", ctx)` (unchanged), `("sim_cmd", {"key", "seed", "log", "err", "randseed_path"})`,
  `("command", {"key", "argv", "stdout_path", "stderr_path"})`, `("timeout", float | None)`.
  **Failure handling**: `builder_cfg.get_run_time_opts(builder_mode, seed)` calls
  `log.critical` if `builder_mode` is not in `builder_cfg.opts` or the mode's
  `run_time` is `None` — see spec [01a](01a-builder-schema.md). No catching.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:195,221-235` — `VlogSim.execute` argv + `get_timeout`; `get_run_time_opts` at `config/rtl.py:104-123`, `get_timeout` at `config/test.py:210-219`.

Manifest entries per [06](../06-graph-yaml.md).

## Tests

In `modules/tests/test_sim_cycle.py`:

- `build-sim-cmd` argv matches rtl_buddy `VlogSim.execute`; timeout pulled from test
  config. `stdout_path`/`stderr_path` in `command` and `log`/`randseed_path` in `sim_cmd`
  all carry the `logs_dir` prefix (verify with default `"logs"` and a custom value).

## Acceptance criteria

- Tests pass.
- All four output ports (`ctx`, `sim_cmd`, `command`, `timeout`) are exercised; argv
  matches rtl_buddy and every log/randseed path carries the `logs_dir` prefix.
