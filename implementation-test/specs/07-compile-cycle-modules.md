# Spec 07: Compile-cycle modules (index)

**Depends on:** spec 03 (run-process), spec 06 (write-filelist), spec
[01a](01a-builder-schema.md) (`BuildCompileCmdMod` consumes `RtlBuilderConfig` methods),
spec [01b](01b-suite-schema.md) (`BuildCompileCmdMod` reads
`ctx["test"].get_name()`/`get_plusdefines()`).
**References:** [03 — Reusable subprocess core section](../03-module-catalog.md), [04 — keyed_join paragraph](../04-pipeline-and-contracts.md).

## Goal

Build the per-test compile leg: assemble the compile argv (with log paths placed in
`command`), fold `simv` into `ctx`, run the subprocess via `run-process` (spec 03), and
route on the rc.

This spec is split into one ticket per module — build them as independent units. Both live
in `modules/rtl_test/build.py`; tests in `modules/tests/test_compile_cycle.py`.

| Ticket | Module | What it does |
|---|---|---|
| [07a](07a-build-compile-cmd.md) | `BuildCompileCmdMod` | Assemble compile argv; fold `simv` into `ctx`. |
| [07b](07b-interpret-compile.md) | `InterpretCompileMod` | Route on rc (`keyed_join`); emit `CompileFailResults`. |

Manifest entries per [06](../06-graph-yaml.md).

## Acceptance criteria

- Each child ticket's tests pass.
- Wiring `build-compile-cmd` → `run-process` (instance #1) → `interpret-compile` (with
  `keyed_join`) end-to-end against a real builder produces a non-zero `rc` on a known
  bad source file and surfaces it correctly.

## Notes

`cc-int` (interpret-compile) is one of the two `keyed_join` nodes. `simv` is set by
`build-compile-cmd` and carried in `ctx` — `build-sim-cmd` reads it directly. `build_dir`
is not in `ctx` (not needed downstream). See
[04 — keyed_join paragraph](../04-pipeline-and-contracts.md).
