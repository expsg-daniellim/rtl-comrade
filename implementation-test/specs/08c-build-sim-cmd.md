# Spec 08c: build-sim-cmd (`BuildSimCmdMod`)

**Depends on:** spec 03 (run-process), spec 07 (compile cycle — `ctx["simv"]`), spec
[01a](01a-builder-schema.md) (`BuildSimCmdMod` consumes `RtlBuilderConfig` methods), spec
[01b](01b-suite-schema.md) (`BuildSimCmdMod` reads `ctx["test"].get_timeout()`,
`get_plusargs()`, `get_plusdefines()`).
**References:** [03 — Simulation section](../03-module-catalog.md). Parent index:
[idx-08 — Sim-cycle modules](../idx-08-sim-cycle.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)`
signature, the allowed output forms (plain return / named-port tuple / generator), the
`finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py`
are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry
below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit
`a69d962`). This module appends to `modules/rtl_buddy/sim.py`, which is created by spec
[`08a`](08a-expand-runs.md) — append, do not overwrite. The file is shared with the sim-cycle
modules (`08a`–`08f`, index [idx-08](../idx-08-sim-cycle.md)) and the post modules (`09a`–`09c`,
index [idx-09](../idx-09-post.md)); coordinate shared imports and helpers with those specs.

## Goal

Assemble the per-run sim argv (with log paths in `command` and `seed`/`log`/`randseed_path`
carried in `sim_cmd`) and the timeout.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry —
the catalog is the design view, this is the build view; update both when behaviour changes.
All four outputs are emitted in lockstep via a generator. The skeleton is **illustrative** —
`plusdefines`/`plusargs` are constructed per Algorithm step 2 (the Algorithm + Deliverables
are authoritative for the list-building details elided here).

```
contract:          default
persistent_inputs: [builder_cfg, builder_mode, logs_dir]
inputs:            ctx, seed, builder_cfg, builder_mode, logs_dir:Path
outputs:           ctx     → ctx
                   sim_cmd → {key, seed, log, err, randseed_path, argv}
                   command → {key, argv, stdout_path, stderr_path}
                   timeout → float | None
```

`logs_dir` is the **resolved artefact directory** (a `Path`) supplied by `ensure-logs-dir`, not
the CLI subdir name — the log/randseed stems join onto it and never touch the ambient CWD.

```python
class BuildSimCmdMod:
    def run(self, ctx, seed, builder_cfg, builder_mode, logs_dir):
        simv = ctx["simv"]   # set by build-compile-cmd
        argv = [simv, *builder_cfg.get_run_time_opts(builder_mode, seed=seed["seed"]), *plusdefines, *plusargs]  # plusdefines/plusargs built per Algorithm step 2
        timeout, is_custom = ctx["test"].get_timeout()
        if is_custom:
            log.warning("custom_sim_timeout", key=ctx["key"], timeout=timeout)   # rtl_buddy vlog_sim.py:233-234
        stem = logs_dir / f"{ctx['test'].get_name()}{run_suffix(ctx)}"   # logs_dir: resolved Path from ensure-logs-dir
        log_path, err_path, rs_path = f"{stem}.log", f"{stem}.err", f"{stem}.randseed"
        yield ("ctx", ctx)
        yield ("sim_cmd", { "key": ctx["key"], "seed": seed["seed"], "log": log_path,
                            "err": err_path, "randseed_path": rs_path, "argv": argv })
        yield ("command", { "key": ctx["key"], "argv": argv,
                            "stdout_path": log_path, "stderr_path": err_path })
        yield ("timeout", float(timeout))
```

## Algorithm

1. Take the compiled simv from ctx: `simv = ctx["simv"]` (set by `build-compile-cmd`).
2. Build plusdefines from `ctx["test"].get_plusdefines()` exactly as in `build-compile-cmd`,
   and plusargs from `ctx["test"].get_plusargs()` (spec 01b → `dict | None`): each entry
   `f"+{k}={v}"`, or `f"+{k}"` when `v is None`.
3. Assemble the argv: `[simv, *builder_cfg.get_run_time_opts(builder_mode, seed=seed["seed"]),
   *plusdefines, *plusargs]`. `get_run_time_opts` already appends `sim_rand_prefix + str(seed)`
   internally — do **not** add the seed again.
4. Resolve the timeout: `(timeout, is_custom) = ctx["test"].get_timeout()` (spec 01b —
   `(self.timeout, True)` on a per-test override, else `(60, False)`); when `is_custom`, log
   `log.warning("custom_sim_timeout", …)` (rtl_buddy parity, `vlog_sim.py:233-234`); emit
   `timeout` as `float`.
5. Compose the log/randseed paths off one stem `stem = logs_dir /
   f"{ctx['test'].get_name()}{run_suffix(ctx)}"` → `log = f"{stem}.log"`, `err = f"{stem}.err"`,
   `randseed_path = f"{stem}.randseed"`. `logs_dir` is the resolved `Path` from `ensure-logs-dir`
   (join onto it — no ambient-CWD assumption). `run_suffix(ctx)` returns `""` when
   `ctx["run_id"] is None`, else `f"_{ctx['run_id']:04d}"` (run-id zero-padded to four digits) —
   rtl_buddy `_get_log_path` (`tools/vlog_sim.py:82-86`); e.g. run-id 5 →
   `<logs_dir>/my_test_0005.log`. Do not `mkdir(logs_dir)` — already bootstrapped.
6. Emit in lockstep: `("ctx", ctx)`; `("sim_cmd", {"key": ctx["key"], "seed": seed["seed"],
   "log": log, "err": err, "randseed_path": randseed_path, "argv": argv})`; `("command",
   {"key": ctx["key"], "argv": argv, "stdout_path": log, "stderr_path": err})`; `("timeout",
   float(timeout))`. The `argv` rides `sim_cmd` as well as `command` so the downstream
   `keyed_join` `write-randseed` can check it for `hier_inst_seed` (spec 08d).
7. **Failure — bad builder mode.** No catch: `builder_cfg.get_run_time_opts(builder_mode,
   seed)` `log.fatal`s if `builder_mode` is unknown or its `run_time` is `None` (spec 01a).

## Deliverables

In `modules/rtl_buddy/sim.py`:

- `BuildSimCmdMod` — `(ctx, seed, builder_cfg, builder_mode, logs_dir:Path)` → assembles
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
  — `(self.timeout, True)` if a per-test override is set, else `(60, False)`); when `is_custom`,
  logs `log.warning("custom_sim_timeout", …)` (rtl_buddy parity, `vlog_sim.py:233-234`); the
  `timeout` value (an `int` seconds) is emitted as a `float | None`. Log paths are
  `logs_dir / f"{test_name}{run_suffix}.log"`/`.err`, where `run_suffix` is `""` when
  `ctx["run_id"] is None` and `f"_{run_id:04d}"` (run-id zero-padded to four digits) otherwise —
  e.g. `<logs_dir>/my_test.log` for a single run, `<logs_dir>/my_test_0005.log` for run-id 5
  (path format is rtl_buddy `_get_log_path`, `tools/vlog_sim.py:82-86`; `logs_dir` is the
  resolved artefact `Path` persistent input supplied by `ensure-logs-dir`). Also composes
  `randseed_path = logs_dir / f"{test_name}{run_suffix}.randseed"` (same stem). These paths are
  emitted in `sim_cmd` (not folded into `ctx`) so `write-randseed` receives them as a
  dedicated keyed port. The assembled `argv` is **also** carried on `sim_cmd` (in addition to
  `command`) so the downstream `keyed_join` `write-randseed` can perform the
  `"hier_inst_seed" in argv` membership check rtl_buddy does (spec
  [08d](08d-write-randseed.md)). Does not `mkdir(logs_dir)` — `ensure-logs-dir` has already
  bootstrapped the directory, and this node blocks on its (first-run-required) `logs_dir` input
  before composing, so the directory exists by the time `run-process` redirects into it. Emits in lockstep:
  `("ctx", ctx)` (unchanged), `("sim_cmd", {"key", "seed", "log", "err", "randseed_path",
  "argv"})`, `("command", {"key", "argv", "stdout_path", "stderr_path"})`,
  `("timeout", float | None)`.
  **Failure handling**: `builder_cfg.get_run_time_opts(builder_mode, seed)` calls
  `log.fatal` if `builder_mode` is not in `builder_cfg.opts` or the mode's
  `run_time` is `None` — see spec [01a](01a-builder-schema.md). No catching.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:195,221-235` — `VlogSim.execute` argv + `get_timeout`; `get_run_time_opts` at `config/rtl.py:104-123`, `get_timeout` at `config/test.py:210-219`.

**Manifest** — append to the `- file: rtl_buddy/sim.py` block in `modules/config.yaml`
(opened by [`08a`](08a-expand-runs.md); append, don't re-create):

```yaml
  - { name: build-sim-cmd, class_name: BuildSimCmdMod }
```

## Tests

In `modules/tests/test_sim_cycle.py`. Fixtures: a `builder_cfg` double exposing
`get_run_time_opts(mode, seed=…)`; a `ctx` carrying `simv` and a `test`
(`get_timeout`/`get_plusargs`/`get_plusdefines`/`get_name`); a `seed` dict; `logging_handler`
for the bad-mode path.

- Default-timeout `ctx`, `get_plusargs()`/`get_plusdefines()` `None` → yields all four ports;
  `argv == [ctx["simv"], *run_time_opts, ]` (matches `VlogSim.execute`), `sim_cmd` carries
  `seed`/`log`/`err`/`randseed_path`/`argv`, `command` carries `argv`/`stdout_path`/`stderr_path`,
  and `("timeout", 60.0)` (the `(60, False)` default).
- `get_timeout()` returns `(300, True)` (per-test override) → `("timeout", 300.0)` (boundary:
  custom timeout emitted as `float`).
- `get_plusargs()` `{"X": 5, "Y": None}` and `get_plusdefines()` `{"D": None}` → `argv`
  contains `"+X=5"`, `"+Y"`, and `"+define+D"` (boundary: `None`-valued plus formats without `=`).
- `logs_dir=Path("/work/custom")` (resolved dir from `ensure-logs-dir`) →
  `command["stdout_path"]`/`stderr_path` and `sim_cmd["log"]`/`["err"]`/`["randseed_path"]` all
  carry the `/work/custom/` prefix (paths joined onto the provided directory; no CWD-relative
  `"logs"` assumption).
- `ctx["run_id"]` set (e.g. `5`) → every path stem includes the `_0005` run suffix (boundary:
  run-id suffix); `sim_cmd["argv"]` equals `command["argv"]` (so `write-randseed` can run the
  `hier_inst_seed` membership check).
- `builder_mode` unknown → `get_run_time_opts` `log.fatal`s → `pytest.raises(SystemExit)`
  (not caught here).

## Acceptance criteria

- Tests pass.
- All four output ports (`ctx`, `sim_cmd`, `command`, `timeout`) are exercised in lockstep:
  `argv` matches rtl_buddy and every log/err/randseed path in `sim_cmd`/`command` carries the
  `logs_dir` prefix.
- No port-routed failure path (the sim `rc` is interpreted downstream by `interpret-sim`).
- The `modules/config.yaml` manifest entry `{ name: build-sim-cmd, class_name: BuildSimCmdMod }`
  validates and the harness resolves `build-sim-cmd` → `BuildSimCmdMod`.

## Constraints

- `get_run_time_opts(builder_mode, seed=seed["seed"])` already appends `sim_rand_prefix +
  str(seed)` internally — **do not add the seed again**.
- Carry the assembled `argv` on **both** `sim_cmd` and `command` so the downstream `keyed_join`
  `write-randseed` can run the `"hier_inst_seed" in argv` membership check (spec
  [08d](08d-write-randseed.md)) — `keyed_join` cannot take a persistent input.
- Emit log/randseed paths on `sim_cmd` (not folded into `ctx`); compose them by joining onto
  the resolved `logs_dir` `Path` persistent input from `ensure-logs-dir` (`logs_dir / name`) —
  do **not** assume a CWD-relative `"logs"` or read the ambient CWD. Do **not** `mkdir(logs_dir)`
  — `ensure-logs-dir` owns it.
- Emit `timeout` as `float | None`. Emit all four ports in lockstep via the generator.
- When `get_timeout()` reports `is_custom` (a per-test `sim_timeout` override), log
  `log.warning("custom_sim_timeout", …)` — rtl_buddy parity (`vlog_sim.py:233-234`).
- Do **not** catch `get_run_time_opts` — it `log.fatal`s on an unknown mode / `None` opts
  (spec [01a](01a-builder-schema.md)); system-wide misconfiguration, not per-test.
