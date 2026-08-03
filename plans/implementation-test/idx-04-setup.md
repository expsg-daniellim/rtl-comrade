# idx-04 — Setup modules (group index)

> Navigation only — not a build ticket. The buildable units are the child specs under [`specs/`](specs/).

**Depends on:** spec 01 (schema), spec [01b](specs/01b-suite-schema.md)
(`ParseSuiteConfigMod` produces `SuiteConfig` / `TestConfig` / `TestbenchConfig`).
**References:** [03 — Setup section](03-module-catalog.md).

## Goal

Implement the run-once setup chain that reimplements rtl_buddy's `RootConfig` /
`SuiteConfig` orchestration as six atomic nodes plus a CWD-convention guard, a
logs-directory bootstrap, and the trivial seed-mode derivation.

This spec is split into one ticket per module — build them as independent units. All live
in `modules/rtl_buddy/setup.py`; tests in `modules/tests/test_setup.py`.

`parse-root-config` ([04c](specs/04c-parse-root-config.md)) and `parse-suite-config`
([04h](specs/04h-parse-suite-config.md)) each **define the raw `@serde` container they read** —
`RootConfigFile`, and `SuiteConfigFile`/`TestConfigFile` respectively (pure serde shapes, no
methods). These are read-once and never ride a graph edge, so they live with their consuming node
rather than in the schema package ([idx-01](idx-01-schema.md)); the raw→runtime conversion happens
inline in each node's `run`, and the runtime types
it produces (`RootConfig`, `SuiteConfig`/`TestConfig`/`TestbenchConfig`) are owned by the schema specs.

| Ticket | Module | What it does |
|---|---|---|
| [04a](specs/04a-discover-config-file.md) | `DiscoverConfigFileMod` | Walk up from CWD for a named config file. |
| [04b](specs/04b-prepend-cwd-path.md) | `PrependCwdPathMod` | Prepend `.` to `$PATH` for CWD-local tool discovery. |
| [04c](specs/04c-parse-root-config.md) | `ParseRootConfigMod` | Deserialise `root_config.yaml` → `root_cfg`. |
| [04d](specs/04d-select-platform.md) | `SelectPlatformMod` | Match `uname` → `platform_cfg`. |
| [04e](specs/04e-resolve-builder.md) | `ResolveBuilderMod` | Pick active `RtlBuilderConfig` → `builder_cfg`. |
| [04f](specs/04f-work-dir.md) | `WorkDirMod` | Zero-input artefact-base provider; emit `work_dir = Path.cwd().resolve()` (regression swaps in per-suite `suite_dir`). |
| [04g](specs/04g-ensure-logs-dir.md) | `EnsureLogsDirMod` | Bootstrap the artefact dir under `work_dir` once; emit its resolved `Path`. |
| [04h](specs/04h-parse-suite-config.md) | `ParseSuiteConfigMod` | Deserialise `tests.yaml` → `suite_cfg`. |
| [04i](specs/04i-derive-seed-mode.md) | `DeriveSeedModeMod` | Map the two CLI booleans → `SeedMode`. |

**Manifest** — these nine modules open the `rtl_buddy/setup.py` block in `modules/config.yaml`
(each child ticket carries its own line). The selection/expansion chain (`05a`–`05f`) and
`git-status` ([`10b`](specs/10b-git-status.md)) append to the **same** block — append, don't re-create:

```yaml
- file: rtl_buddy/setup.py
  plugins:
  - { name: discover-config-file, class_name: DiscoverConfigFileMod }
  - { name: prepend-cwd-path,     class_name: PrependCwdPathMod }
  - { name: parse-root-config,    class_name: ParseRootConfigMod }
  - { name: select-platform,      class_name: SelectPlatformMod }
  - { name: resolve-builder,      class_name: ResolveBuilderMod }
  - { name: work-dir,             class_name: WorkDirMod }
  - { name: ensure-logs-dir,      class_name: EnsureLogsDirMod }
  - { name: parse-suite-config,   class_name: ParseSuiteConfigMod }
  - { name: derive-seed-mode,     class_name: DeriveSeedModeMod }
  # + route-list-mode, list-test-names, select-tests, filter-reglvl, load-model,
  #   expand-sweep (05a-05f) and git-status (10b)
```

## Acceptance criteria

- Each child ticket's tests pass.
- Integration coverage lives in the child tickets' own acceptance criteria (each node's ports,
  failure idioms, and `root_cfg`/`builder_cfg`/`suite_cfg`/`work_dir`/`PATH`/`logs_dir`
  behaviour); the full "setup-only" graph is wired and exercised end-to-end in
  [spec 11](specs/11-graph-and-manifests.md) and [spec 12](specs/12-end-to-end.md).
- Every child's `modules/config.yaml` entry validates and resolves: `discover-config-file`,
  `prepend-cwd-path`, `parse-root-config`, `select-platform`, `resolve-builder`,
  `work-dir`, `ensure-logs-dir`, `parse-suite-config`, `derive-seed-mode` each map to
  their `*Mod` class (see [11](specs/11-graph-and-manifests.md#acceptance-criteria)).
