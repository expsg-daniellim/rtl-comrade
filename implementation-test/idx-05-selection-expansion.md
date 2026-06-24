# idx-05 — Selection and expansion modules (group index)

> Navigation only — not a build ticket. The buildable units are the child specs under [`specs/`](specs/).

**Depends on:** spec 01 (schema), spec [01a](specs/01a-builder-schema.md) (builder schema —
`FilterRegLvlMod` consumes `RtlBuilderConfig`), spec [01b](specs/01b-suite-schema.md)
(`SuiteConfig` / `TestConfig` / `UVMConfig` — every module here reads from
`test`), spec [01c](specs/01c-model-schema.md) (the runtime `ModelConfig` —
`LoadModelMod` **defines** the raw `ModelConfigFileItem`/`ModelConfigFile` it reads and
unrolls the read/name-lookup (rtl_buddy's `ModelConfigLoader`) into its `run`, constructing
the frozen `ModelConfig` from the matched item, since neither rides a graph edge; see
[idx-01](idx-01-schema.md)).
**References:** [03 — Selection/expansion section](03-module-catalog.md).

## Goal

Implement the list-routing front end, the test stream entry, level filtering, lazy
model loading, and sweep expansion.

This spec is split into one ticket per module — build them as independent units. All live
in `modules/rtl_buddy/setup.py` (continuing from spec 04); tests in
`modules/tests/test_selection.py`.

| Ticket | Module | What it does |
|---|---|---|
| [05a](specs/05a-route-list-mode.md) | `RouteListModeMod` | Route list-mode vs run-mode. |
| [05b](specs/05b-list-test-names.md) | `ListTestNamesMod` | Print test names (list-mode sink). |
| [05c](specs/05c-select-tests.md) | `SelectTestsMod` | Enter the per-test stream. |
| [05d](specs/05d-filter-reglvl.md) | `FilterRegLvlMod` | Keep/skip by regression level. |
| [05e](specs/05e-load-model.md) | `LoadModelMod` | Lazily resolve the `ModelConfig` onto its own `model` edge. |
| [05f](specs/05f-expand-sweep.md) | `ExpandSweepMod` | Expand into N sweep variants. |

**Manifest** — these six modules append to the `rtl_buddy/setup.py` block in `modules/config.yaml`
opened by the setup chain ([`04a`](specs/04a-discover-config-file.md)); each child ticket carries its
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
- Integration coverage lives in the child tickets' own acceptance criteria (test fan-out and
  key stamping, sweep multiplication, and the `list`/`skip`/`fail` diversion ports); the full
  selection/expansion stream is wired and exercised end-to-end in
  [spec 11](specs/11-graph-and-manifests.md) and [spec 12](specs/12-end-to-end.md).
- Every child's `modules/config.yaml` entry validates and resolves: `route-list-mode`,
  `list-test-names`, `select-tests`, `filter-reglvl`, `load-model`, `expand-sweep` each map
  to their `*Mod` class (see [11](specs/11-graph-and-manifests.md#acceptance-criteria)).
