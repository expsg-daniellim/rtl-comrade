# idx-06 — Per-test prep modules (group index)

> Navigation only — not a build ticket. The buildable units are the child specs under [`specs/`](specs/).

**Depends on:** spec 01 (schema), spec [01b](specs/01b-suite-schema.md) (`RunPreprocMod`
reads `test.get_preproc_path()`; `WriteFilelistMod` reads
`test.get_testbench().get_filelist()`), spec [01c](specs/01c-model-schema.md)
(`WriteFilelistMod` reads the joined `model.value.get_filelist()` and `.path`).
**References:** [03 — Per-test preparation section](03-module-catalog.md).

## Goal

Implement the per-test preprocessing hook and filelist generator that sit between sweep
expansion and compile.

This spec is split into one ticket per module — build them as independent units. Both live
in `modules/rtl_buddy/build.py` (continuing from spec 03); tests in
`modules/tests/test_prep.py`.

| Ticket | Module | What it does |
|---|---|---|
| [06a](specs/06a-run-preproc.md) | `RunPreprocMod` | Optional preprocessing hook (mutates `test`). |
| [06b](specs/06b-write-filelist.md) | `WriteFilelistMod` | Generate the per-tag `run.{test_tag}.f`. |

**Manifest** — these two modules open the `rtl_buddy/build.py` block in `modules/config.yaml`; the
compile cycle (`07a`, [`03`](specs/03-run-process.md), `07b`) appends to the same block:

```yaml
- file: rtl_buddy/build.py
  plugins:
  - { name: run-preproc,    class_name: RunPreprocMod }
  - { name: write-filelist, class_name: WriteFilelistMod }
  # + build-compile-cmd (07a), run-process (03), interpret-compile (07b)
```

## Acceptance criteria

- Each child ticket's tests pass.
- Integration coverage lives in the child tickets' own acceptance criteria (`test`/`model` edge
  forward/mutate, byte-for-byte `VlogFilelist` parity, and both `fail` ports); the prep leg is
  wired and exercised end-to-end in [spec 11](specs/11-graph-and-manifests.md) and
  [spec 12](specs/12-end-to-end.md).
- Both children's `modules/config.yaml` entries validate and resolve: `run-preproc` →
  `RunPreprocMod`, `write-filelist` → `WriteFilelistMod` (see
  [11](specs/11-graph-and-manifests.md#acceptance-criteria)).
