# Spec 06: Per-test prep modules (index)

**Depends on:** spec 01 (schema), spec [01b](01b-suite-schema.md) (`RunPreprocMod`
reads `ctx["test"].get_preproc_path()`; `WriteFilelistMod` reads
`ctx["test"].get_testbench().get_filelist()`), spec [01c](01c-model-schema.md)
(`WriteFilelistMod` reads `ctx["test"].get_model().get_filelist()` and `.path`).
**References:** [03 — Per-test preparation section](../03-module-catalog.md).

## Goal

Implement the per-test preprocessing hook and filelist generator that sit between sweep
expansion and compile.

This spec is split into one ticket per module — build them as independent units. Both live
in `modules/rtl_test/build.py` (continuing from spec 03); tests in
`modules/tests/test_prep.py`.

| Ticket | Module | What it does |
|---|---|---|
| [06a](06a-run-preproc.md) | `RunPreprocMod` | Optional preprocessing hook (mutates `ctx["test"]`). |
| [06b](06b-write-filelist.md) | `WriteFilelistMod` | Generate the per-tag `run.{test_tag}.f`. |

**Manifest** — these two modules open the `rtl_test/build.py` block in `modules/config.yaml`; the
compile cycle (`07a`, [`03`](03-run-process.md), `07b`) appends to the same block:

```yaml
- file: rtl_test/build.py
  plugins:
  - { name: run-preproc,    class_name: RunPreprocMod }
  - { name: write-filelist, class_name: WriteFilelistMod }
  # + build-compile-cmd (07a), run-process (03), interpret-compile (07b)
```

## Acceptance criteria

- Each child ticket's tests pass.
- End-to-end against a real rtl_buddy fixture (the reference suite
  `../rtl-buddy-proj-template/design/sandbox/verif`): `run-preproc` forwards/mutates `ctx`
  and `write-filelist` reproduces the byte-for-byte output of rtl_buddy's `VlogFilelist` on
  the same inputs (modulo ordering if dedup is non-stable), with both modules' `fail` ports
  exercised.
- Both children's `modules/config.yaml` entries validate and resolve: `run-preproc` →
  `RunPreprocMod`, `write-filelist` → `WriteFilelistMod` (see
  [11](11-graph-and-manifests.md#acceptance-criteria)).
