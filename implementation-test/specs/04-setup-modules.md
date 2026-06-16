# Spec 04: Setup modules (index)

**Depends on:** spec 01 (schema), spec [01b](01b-suite-schema.md)
(`ParseSuiteConfigMod` produces `SuiteConfig` / `TestConfig` / `TestbenchConfig`).
**References:** [03 — Setup section](../03-module-catalog.md).

## Goal

Implement the run-once setup chain that reimplements rtl_buddy's `RootConfig` /
`SuiteConfig` orchestration as six atomic nodes plus a CWD-convention guard, a
logs-directory bootstrap, and the trivial seed-mode derivation.

This spec is split into one ticket per module — build them as independent units. All live
in `modules/rtl_buddy/setup.py`; tests in `modules/tests/test_setup.py`.

| Ticket | Module | What it does |
|---|---|---|
| [04a](04a-discover-config-file.md) | `DiscoverConfigFileMod` | Walk up from CWD for a named config file. |
| [04b](04b-prepend-cwd-path.md) | `PrependCwdPathMod` | Prepend `.` to `$PATH` for CWD-local tool discovery. |
| [04c](04c-parse-root-config.md) | `ParseRootConfigMod` | Deserialise `root_config.yaml` → `root_cfg`. |
| [04d](04d-select-platform.md) | `SelectPlatformMod` | Match `uname` → `platform_cfg`. |
| [04e](04e-resolve-builder.md) | `ResolveBuilderMod` | Pick active `RtlBuilderConfig` → `builder_cfg`. |
| [04f](04f-check-suite-cwd.md) | `CheckSuiteCwdMod` | Enforce the suite-directory CWD convention; emit `work_dir` (artefact-location provider). |
| [04g](04g-ensure-logs-dir.md) | `EnsureLogsDirMod` | Bootstrap the artefact dir under `work_dir` once; emit its resolved `Path`. |
| [04h](04h-parse-suite-config.md) | `ParseSuiteConfigMod` | Deserialise `tests.yaml` → `suite_cfg`. |
| [04i](04i-derive-seed-mode.md) | `DeriveSeedModeMod` | Map the two CLI booleans → `SeedMode`. |

**Manifest** — these nine modules open the `rtl_buddy/setup.py` block in `modules/config.yaml`
(each child ticket carries its own line). The selection/expansion chain (`05a`–`05f`) and
`git-status` ([`10b`](10b-git-status.md)) append to the **same** block — append, don't re-create:

```yaml
- file: rtl_buddy/setup.py
  plugins:
  - { name: discover-config-file, class_name: DiscoverConfigFileMod }
  - { name: prepend-cwd-path,     class_name: PrependCwdPathMod }
  - { name: parse-root-config,    class_name: ParseRootConfigMod }
  - { name: select-platform,      class_name: SelectPlatformMod }
  - { name: resolve-builder,      class_name: ResolveBuilderMod }
  - { name: check-suite-cwd,      class_name: CheckSuiteCwdMod }
  - { name: ensure-logs-dir,      class_name: EnsureLogsDirMod }
  - { name: parse-suite-config,   class_name: ParseSuiteConfigMod }
  - { name: derive-seed-mode,     class_name: DeriveSeedModeMod }
  # + route-list-mode, list-test-names, select-tests, filter-reglvl, load-model,
  #   expand-sweep (05a-05f) and git-status (10b)
```

## Acceptance criteria

- Each child ticket's tests pass.
- End-to-end "setup-only" graph wiring all nine nodes against the real rtl_buddy reference
  suite `../rtl-buddy-proj-template/design/sandbox(/verif)` (per `rtl_buddy/AGENTS.md`)
  produces correct `root_cfg`/`builder_cfg`/`suite_cfg` values, with `CheckSuiteCwdMod`
  aborting runs invoked from outside the suite directory (and emitting `work_dir`),
  `PrependCwdPathMod` leaving `os.environ["PATH"]` starting with `.` for the duration of the run,
  and `EnsureLogsDirMod` rooting the artefact directory on `work_dir` (default `<work_dir>/logs`,
  i.e. `./logs/` when run from the suite dir) and emitting its resolved `Path` before any later
  main-line node fires.
- Every child's `modules/config.yaml` entry validates and resolves: `discover-config-file`,
  `prepend-cwd-path`, `parse-root-config`, `select-platform`, `resolve-builder`,
  `check-suite-cwd`, `ensure-logs-dir`, `parse-suite-config`, `derive-seed-mode` each map to
  their `*Mod` class (see [11](11-graph-and-manifests.md#acceptance-criteria)).

## Notes

`DiscoverConfigFileMod` is reusable for the harness's own config discovery — see [07
implementation note](../07-ambiguities-and-assumptions.md). `DeriveSeedModeMod` is on the
KIV path (item 18) — keep it small and stateless; future absorbing into `resolve-seed`
should be straightforward. `CheckSuiteCwdMod` is the explicit enforcement of the
user-driven CWD convention documented in [01](../01-cli-and-entry.md) — the regression
graph does **not** wire it (regression `chdir`s per-suite internally; see
[08](../08-sibling-graphs.md)). `EnsureLogsDirMod` is wired in `test`/`randtest` only
for the same reason: regression's per-suite `chdir` means a once-at-startup `logs/`
bootstrap targets the wrong place; the regression equivalent runs **per chdir'd suite**
and is owned by [08](../08-sibling-graphs.md).
