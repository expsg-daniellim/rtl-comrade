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
in `modules/rtl_buddy/setup.py` (continuing from spec 04); tests in
`modules/tests/test_selection.py`.

| Ticket | Module | What it does |
|---|---|---|
| [05a](05a-route-list-mode.md) | `RouteListModeMod` | Route list-mode vs run-mode. |
| [05b](05b-list-test-names.md) | `ListTestNamesMod` | Print test names (list-mode sink). |
| [05c](05c-select-tests.md) | `SelectTestsMod` | Enter the per-test stream. |
| [05d](05d-filter-reglvl.md) | `FilterRegLvlMod` | Keep/skip by regression level. |
| [05e](05e-load-model.md) | `LoadModelMod` | Lazily attach the `ModelConfig`. |
| [05f](05f-expand-sweep.md) | `ExpandSweepMod` | Expand into N sweep variants. |

**Manifest** — these six modules append to the `rtl_buddy/setup.py` block in `modules/config.yaml`
opened by the setup chain ([`04a`](04a-discover-config-file.md)); each child ticket carries its
own line (append, don't re-create the block):

```yaml
  - { name: route-list-mode, class_name: RouteListModeMod }
  - { name: list-test-names, class_name: ListTestNamesMod }
  - { name: select-tests,    class_name: SelectTestsMod }
  - { name: filter-reglvl,   class_name: FilterRegLvlMod }
  - { name: load-model,      class_name: LoadModelMod }
  - { name: expand-sweep,    class_name: ExpandSweepMod }
```

## Acceptance criteria

- Each child ticket's tests pass.
- Streamed end-to-end against the reference suite
  `../rtl-buddy-proj-template/design/sandbox/verif/tests.yaml`: three tests fan out to three
  `ctx`s with correctly-stamped keys, a sweep script multiplies one of them by 4, and the
  `route-list-mode`/`filter-reglvl`/`load-model` diversion ports (`list`/`skip`/`fail`) each
  fire on their respective inputs.
- Every child's `modules/config.yaml` entry validates and resolves: `route-list-mode`,
  `list-test-names`, `select-tests`, `filter-reglvl`, `load-model`, `expand-sweep` each map
  to their `*Mod` class (see [11](11-graph-and-manifests.md#acceptance-criteria)).

## Notes

`expand-sweep` and `run-preproc` (spec [06a](06a-run-preproc.md)) share the same
`exec`-with-namespace pattern via a small `exec_hook(path, namespace)` helper in
`modules/rtl_buddy/_hooks.py`. Its signature and exception-propagation contract are defined
once in spec [05f](05f-expand-sweep.md) Notes; `06a` references it.
