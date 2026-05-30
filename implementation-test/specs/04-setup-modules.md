# Spec 04: Setup modules

**Depends on:** spec 01 (schema).
**References:** [03 — Setup section](../03-module-catalog.md).

## Goal

Implement the run-once setup chain that reimplements rtl_buddy's `RootConfig` /
`SuiteConfig` orchestration as six atomic nodes, plus the trivial seed-mode derivation.

## Deliverables

In `modules/rtl_test/setup.py`:

- `DiscoverConfigFileMod` — walks up the dir tree from CWD for a filename (config:
  `filename:str`, `max_levels:int = 8`); stops at git root or filesystem root; emits the
  resolved `Path`. Zero input ports; runs once via `unit`.
- `ParseRootConfigMod` — reads the path, deserialises into the schema (spec 01); emits
  `root_cfg`.
- `SelectPlatformMod` — runs `uname` (subprocess), matches against each platform's
  `unames`, picks one; critical-logs if no match; emits `platform_cfg`.
- `ResolveBuilderMod` — picks the active `RtlBuilderConfig` from `platform_cfg` honouring
  the CLI `builder` override; critical-logs on unknown override; emits `builder_cfg`.
- `ParseSuiteConfigMod` — reads `test_config:str = "tests.yaml"`, deserialises, binds
  testbenches within-file, records the suite directory on each test for later
  `load-model` (spec 05) resolution; emits `suite_cfg`. **Module is contract-agnostic** —
  pairs with `unit` in test graph, `default` in regression (see [08](../08-sibling-graphs.md)).
- `DeriveSeedModeMod` — `(rnd_new:bool=False, rnd_last:bool=False)` → `SeedMode` (`rnd_new`
  wins, else `REPLAY` if `rnd_last`, else `DEFAULT`).

Manifest entries in `modules/config.yaml` per [06 — Manifest additions](../06-graph-yaml.md).

Tests in `modules/tests/test_setup.py`:
- Discovery walks up to find a fixture `root_config.yaml`; stops at depth limit.
- Parse round-trips an unmodified rtl_buddy `root_config.yaml`.
- Platform select picks correctly under controlled `uname` (mock or skip-if).
- Builder resolve honours override; critical on bad name.
- Suite parse handles a real rtl_buddy `tests.yaml`.

## Acceptance criteria

- Tests pass.
- An end-to-end "setup-only" graph that wires these six nodes produces correct
  `root_cfg`/`builder_cfg`/`suite_cfg` values from real rtl_buddy fixtures.

## Notes

`DiscoverConfigFileMod` is reusable for the harness's own config discovery — see [07
implementation note](../07-ambiguities-and-assumptions.md). `DeriveSeedModeMod` is on the
KIV path (item 18) — keep it small and stateless; future absorbing into `resolve-seed`
should be straightforward.
