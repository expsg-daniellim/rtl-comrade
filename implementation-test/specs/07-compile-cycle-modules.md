# Spec 07: Compile-cycle modules

**Depends on:** spec 03 (run-process), spec 06 (write-filelist), spec
[01a](01a-builder-schema.md) (`BuildCompileCmdMod` consumes `RtlBuilderConfig` methods),
spec [01b](01b-suite-schema.md) (`BuildCompileCmdMod` reads
`ctx["test"].get_name()`/`get_plusdefines()`).
**References:** [03 — Reusable subprocess core section](../03-module-catalog.md), [04 — keyed_join paragraph](../04-pipeline-and-contracts.md).

## Goal

Build the per-test compile leg: assemble the compile argv (with log paths placed in
`command`), fold `simv` into `ctx`, run the subprocess via `run-process` (spec 03), and
route on the rc.

## Deliverables

In `modules/rtl_test/build.py`:

- `BuildCompileCmdMod` — `(ctx, filelist, builder_cfg, builder_mode:str="debug", logs_dir:str="logs")` →
  assembles the argv as
  `[builder_cfg.get_exe()] + builder_cfg.get_compile_time_opts(builder_mode) + (["--Mdir", build_dir] if is_verilator else []) + plusdefines + ["-f", filelist["filelist"]]`,
  where `is_verilator = os.path.basename(builder_cfg.get_exe()).startswith("verilator")`
  (the caller-side verilator switch documented in spec [01a — Verilator
  quirk](01a-builder-schema.md)). Computes `test_tag = re.sub(r"[^A-Za-z0-9_.-]", "_",
  ctx["test"].get_name())`, `build_dir = f"obj_dir_{test_tag}"`, and `simv =
  f"{build_dir}/simv" if is_verilator else builder_cfg.get_simv()` (mirrors
  `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:61-80`). Folds `simv` into `ctx`
  (`ctx["simv"] = simv`); does not fold `build_dir` (not needed downstream). Does not
  `mkdir(logs_dir)` — `ensure-logs-dir` has already bootstrapped the directory via the
  env_ready chain. `plusdefines` is built from `ctx["test"].get_plusdefines()` (spec
  [01b](01b-suite-schema.md) — returns `dict | None`; when not `None`, format each entry
  as `f"+define+{k}={v}"` or `f"+define+{k}"` for `v is None`, mirroring
  `vlog_sim.py:107-117`). Compile log paths are composed as
  `f"{logs_dir}/{test_tag}.compile.log"` and `.err`.
  Emits:
  - `("ctx", ctx_with_simv)` — ctx now carries `simv`
  - `("command", {"key", "argv", "stdout_path", "stderr_path"})` — log paths under `logs_dir`.
  **Failure handling**: `builder_cfg.get_compile_time_opts(builder_mode)` calls
  `log.critical` (immediate `SystemExit(1)`) if `builder_mode` is not in
  `builder_cfg.opts` or the mode's `compile_time` is `None` — see spec
  [01a](01a-builder-schema.md). No catching; system-wide misconfiguration.
- `InterpretCompileMod` — `(ctx, proc)`, with `keyed_join` contract on the node;
  rc == 0 → `("ok", ctx)` unchanged (`ctx["simv"]` already set by `build-compile-cmd`);
  rc != 0 → reads `proc["stderr_path"]`/`stdout_path` and logs at ERROR, then
  `("fail", {"key": ctx["key"], "result": CompileFailResults()})`.
  **Failure handling**: routing on `proc["rc"]`; no Python exception is caught here. The
  ERROR log at emission carries `rc`, `stderr_path`, and a tail of the stderr file
  (mirrors `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:170-172`). `OSError` /
  `FileNotFoundError` reading `stderr_path` would be surprising; let it propagate.

Manifest entries per [06](../06-graph-yaml.md).

Tests in `modules/tests/test_compile_cycle.py`:
- Argv assembly matches rtl_buddy's `VlogSim.compile` for both verilator and non-verilator
  builders, with and without plusdefines.
- `build_dir` and `simv` paths derived correctly per builder type.
- `logs_dir` is honoured in `command["stdout_path"]` / `stderr_path`: default `"logs"`
  yields `logs/<test>.compile.log`/`.err` (rtl_buddy parity); a custom `logs_dir`
  yields the prefixed path.
- `interpret-compile` ok-path passes ctx through; fail-path emits `CompileFailResults` and
  ERROR-level log entry with stderr content.

## Acceptance criteria

- Tests pass.
- Wiring `build-compile-cmd` → `run-process` (instance #1) → `interpret-compile` (with
  `keyed_join`) end-to-end against a real builder produces a non-zero `rc` on a known
  bad source file and surfaces it correctly.

## Notes

`cc-int` (interpret-compile) is one of the two `keyed_join` nodes. `simv` is set by
`build-compile-cmd` and carried in `ctx` — `build-sim-cmd` reads it directly. `build_dir`
is not in `ctx` (not needed downstream). See
[04 — keyed_join paragraph](../04-pipeline-and-contracts.md).
