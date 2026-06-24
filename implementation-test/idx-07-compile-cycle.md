# idx-07 — Compile-cycle modules (group index)

> Navigation only — not a build ticket. The buildable units are the child specs under [`specs/`](specs/).

**Depends on:** spec 03 (run-process), spec 06 (write-filelist), spec
[01a](specs/01a-builder-schema.md) (`BuildCompileCmdMod` consumes `RtlBuilderConfig` methods),
spec [01b](specs/01b-suite-schema.md) (`BuildCompileCmdMod` reads
`test.get_name()`/`get_plusdefines()`).
**References:** [03 — Reusable subprocess core section](03-module-catalog.md), [04 — keyed_join paragraph](04-pipeline-and-contracts.md).

## Goal

Build the per-test compile leg: assemble the compile argv (with log paths placed in
`command`), fold `simv` into `ctx`, run the subprocess via `run-process` (spec 03), and
route on the rc.

This spec is split into one ticket per module — build them as independent units. Both live
in `modules/rtl_buddy/build.py`; tests in `modules/tests/test_compile_cycle.py`.

| Ticket | Module | What it does |
|---|---|---|
| [07a](specs/07a-build-compile-cmd.md) | `BuildCompileCmdMod` | Assemble compile argv; fold `simv` into `ctx`. |
| [07b](specs/07b-interpret-compile.md) | `InterpretCompileMod` | Route on rc (`keyed_join`); emit `CompileFailResults`. |

**Manifest** — these modules append to the `rtl_buddy/build.py` block in `modules/config.yaml`
opened by the prep chain ([`06a`](specs/06a-run-preproc.md)). `run-process` is registered by its own
spec [`03`](specs/03-run-process.md):

```yaml
  - { name: build-compile-cmd, class_name: BuildCompileCmdMod }
  - { name: run-process,       class_name: RunProcessMod }   # spec 03
  - { name: interpret-compile, class_name: InterpretCompileMod }
```

## Acceptance criteria

- Each child ticket's tests pass.
- Integration coverage lives in the child tickets' own acceptance criteria (bad source →
  `CompileFailResults` on `fail`; clean source → `ok`); the `build-compile-cmd` →
  `run-process` (#1) → `interpret-compile` leg is wired and exercised end-to-end in
  [spec 11](specs/11-graph-and-manifests.md) and [spec 12](specs/12-end-to-end.md).
- Each child's `modules/config.yaml` entry validates and resolves: `build-compile-cmd` →
  `BuildCompileCmdMod`, `interpret-compile` → `InterpretCompileMod`, reusing the shared
  `run-process` → `RunProcessMod` instance (see
  [11](specs/11-graph-and-manifests.md#acceptance-criteria)).
