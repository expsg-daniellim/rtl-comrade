# Spec 05: Selection and expansion modules (index)

**Depends on:** spec 01 (schema), spec [01a](01a-builder-schema.md) (builder schema —
`FilterRegLvlMod` consumes `RtlBuilderConfig`), spec [01b](01b-suite-schema.md)
(`SuiteConfig` / `TestConfig` / `UVMConfig` — every module here reads from
`ctx["test"]`), spec [01c](01c-model-schema.md) (`LoadModelMod` constructs
`ModelConfigLoader`).
**References:** [03 — Selection/expansion section](../03-module-catalog.md).

## Goal

Implement the list-routing front end, the test stream entry, level filtering, lazy
model loading, and sweep expansion.

This spec is split into one ticket per module — build them as independent units. All live
in `modules/rtl_test/setup.py` (continuing from spec 04); tests in
`modules/tests/test_selection.py`.

| Ticket | Module | What it does |
|---|---|---|
| [05a](05a-route-list-mode.md) | `RouteListModeMod` | Route list-mode vs run-mode. |
| [05b](05b-list-test-names.md) | `ListTestNamesMod` | Print test names (list-mode sink). |
| [05c](05c-select-tests.md) | `SelectTestsMod` | Enter the per-test stream. |
| [05d](05d-filter-reglvl.md) | `FilterRegLvlMod` | Keep/skip by regression level. |
| [05e](05e-load-model.md) | `LoadModelMod` | Lazily attach the `ModelConfig`. |
| [05f](05f-expand-sweep.md) | `ExpandSweepMod` | Expand into N sweep variants. |

Manifest entries per [06](../06-graph-yaml.md).

## Acceptance criteria

- Each child ticket's tests pass.
- Streamed end-to-end: a fixture `tests.yaml` with three tests fans out to three `ctx`s
  with correctly-stamped keys, and a sweep script multiplies one of them by 4.

## Notes

`expand-sweep` and `run-preproc` (spec [06a](06a-run-preproc.md)) share the same
`exec`-with-namespace pattern. Factor a small `exec_hook(path, namespace)` helper into a
private module rather than copy-pasting.
