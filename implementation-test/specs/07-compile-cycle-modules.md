# Spec 07: Compile-cycle modules

**Depends on:** spec 03 (run-process), spec 06 (write-filelist).
**References:** [03 — Reusable subprocess core section](../03-module-catalog.md), [04 — keyed_join paragraph](../04-pipeline-and-contracts.md).

## Goal

Build the per-test compile leg: assemble the compile argv (with log paths and the simv
artifact path pre-folded into `ctx`), run the subprocess via `run-process` (spec 03),
and route on the rc.

## Deliverables

In `modules/rtl_test/build.py`:

- `BuildCompileCmdMod` — `(ctx, filelist, builder_cfg, builder_mode:str="debug")` →
  assembles
  `[exe] + compile_time_opts(mode) + (["--Mdir", obj_dir] if verilator) + plusdefines + ["-f", filelist["filelist"]]`;
  computes prospective `build_dir` and `simv` path; emits:
  - `("ctx", ctx_with_build_dir_and_simv)` (folds them in so the downstream join carries
    no config port)
  - `("command", {"key", "argv", "stdout_path", "stderr_path"})` — log paths are
    `logs/<test>.compile.log`/`.err`.
- `InterpretCompileMod` — `(ctx, proc)`, with `keyed_join` contract on the node;
  rc == 0 → `("ok", ctx)`; rc != 0 → reads `proc["stderr_path"]`/`stdout_path` and logs
  at ERROR, then `("fail", {"key": ctx["key"], "result": CompileFailResults()})`.

Manifest entries per [06](../06-graph-yaml.md).

Tests in `modules/tests/test_compile_cycle.py`:
- Argv assembly matches rtl_buddy's `VlogSim.compile` for both verilator and non-verilator
  builders, with and without plusdefines.
- `build_dir` and `simv` paths derived correctly per builder type.
- `interpret-compile` ok-path passes ctx through; fail-path emits `CompileFailResults` and
  ERROR-level log entry with stderr content.

## Acceptance criteria

- Tests pass.
- Wiring `build-compile-cmd` → `run-process` (instance #1) → `interpret-compile` (with
  `keyed_join`) end-to-end against a real builder produces a non-zero `rc` on a known
  bad source file and surfaces it correctly.

## Notes

`cc-int` (interpret-compile) is one of the two `keyed_join` nodes in the entire graph.
The `keyed_join` contract joins **every** port by key, which is why `simv`/`build_dir`
were folded into `ctx` at `build-compile-cmd` rather than passed as a separate config
port to `interpret-compile`. See [04 — keyed_join paragraph](../04-pipeline-and-contracts.md).
