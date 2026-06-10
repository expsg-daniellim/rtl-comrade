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
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:141-159` — `VlogSim.compile` argv assembly; helpers `_get_build_tag`/`_get_build_dir`/`_get_simv_path` at `vlog_sim.py:61-80`, `_get_plusdefines` at `:107-117`.
- `InterpretCompileMod` — `(ctx, proc)`, with `keyed_join` contract on the node;
  rc == 0 → `("ok", ctx)` unchanged (`ctx["simv"]` already set by `build-compile-cmd`);
  rc != 0 → reads `proc["stderr_path"]`/`stdout_path` and logs at ERROR, then
  `("fail", {"key": ctx["key"], "result": CompileFailResults()})`.
  **Failure handling**: routing on `proc["rc"]`; no Python exception is caught here. The
  ERROR log at emission carries `rc`, `stderr_path`, and a tail of the stderr file
  (mirrors `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:170-172`). `OSError` /
  `FileNotFoundError` reading `stderr_path` would be surprising; let it propagate.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/runner/test_runner.py:63-65` — the `compile_returncode != 0 → CompileFailResults` branch; rc check at `tools/vlog_sim.py:168-171`; `CompileFailResults` at `runner/test_results.py:44-51`.

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

**Concurrency note (TODO #30 / item 17).** `build_dir = f"obj_dir_{test_tag}"` and the
verilator `simv = f"{build_dir}/simv"` are already per-tag, so they don't collide across
concurrent tests. The `-f` filelist is per-tag because `write-filelist` writes
`run.{test_tag}.f` (spec 06) and this module passes `filelist["filelist"]` through unchanged —
no edit needed here. **Residual:** for non-verilator builders `simv = builder_cfg.get_simv()`
is a *fixed configured* name with no per-tag prefix, which the graph can't freely redirect; its
isolation waits on the upstream per-invocation-subdir change
([07 item 17](../07-ambiguities-and-assumptions.md)). Do not add a lock for it — the
`serial_acquire` shim was removed (TODO #30); see
[05 — Interim CWD-collision posture](../05-branching-and-results.md#interim-cwd-collision-posture--per-tag-artefact-naming).
