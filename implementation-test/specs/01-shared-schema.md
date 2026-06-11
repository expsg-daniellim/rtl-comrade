# Spec 01: Shared schema

**Depends on:** none.
**References:** [07 settled 1](../07-ambiguities-and-assumptions.md).

## Before you start

These are `@serde`-decorated dataclasses that the harness never loads directly — a faithful port
of rtl_buddy's config types, so the authoritative reference is the rtl_buddy `config/*.py` source
this spec cites (anchored to `v1.4.0`, commit `a69d962`). The in-repo `@serde` idiom — nested
types and `field(rename=...)` for verbatim YAML field names — is shown by the config-bearing
example in `docs/modules/implementation.md`; [`02 — payload conventions`](../02-payload-conventions.md)
holds the canonical type and `is_pass()` table the port must match. All four schema specs (`01`,
`01a`, `01b`, `01c`) build into the shared `modules/rtl_test/schema/` package — coordinate the
module layout with the others.

## Goal

Reimplement the configuration dataclasses and shared types — preserving rtl_buddy's YAML
field names/structure so existing `root_config.yaml`, `tests.yaml`, `models.yaml`, and
`regressions.yaml` files load drop-in. This is the foundation every setup/post module
depends on.

## Deliverables

A new package, e.g. `modules/rtl_test/schema/`:

- `root.py` — `RootConfigFile`, `RootRtlField`, `PlatformConfigFile`, `PlatformConfig`,
  `VeribleConfigFile`, `VeribleConfig`. Serde-decorated dataclasses with
  `field(rename=...)` matching rtl_buddy field names exactly (`rtl-buddy-filetype`,
  `cfg-rtl-builder`, `cfg-platforms`, `cfg-rtl-reg`, `cfg-verible`).
- `builder.py` — `RtlBuilderConfig`, `RtlBuilderConfigOpts`, `process_opts`. Owned by
  spec [01a](01a-builder-schema.md); listed here only so this umbrella spec stays
  complete. Build 01a in parallel with the rest of 01.
- `suite.py` / `uvm.py` — `SuiteConfigFile`, `SuiteConfig`, `TestbenchConfig`,
  `TestConfigFile` (raw), `TestConfig` (runtime), `UVMConfig`. Owned by spec
  [01b](01b-suite-schema.md). Build 01b in parallel with the rest of 01.
- `model.py` — `ModelConfig`, `ModelConfigFile`, `ModelConfigLoader`. Owned by spec
  [01c](01c-model-schema.md). Build 01c in parallel with the rest of 01.
- `results.py` — `TestResults` base + `TestPassResults`, `CompileFailResults`,
  `EarlyStopResults(desc)`, `SimTimeoutResults`, `SkipResults(desc)`. `is_pass()` returns
  `True` for `PASS`/`SKIP` only.
- `seed_mode.py` — `SeedMode` enum with `NEW`/`REPLAY`/`DEFAULT`.

## Acceptance criteria

- Loading an unmodified rtl_buddy `root_config.yaml` and `tests.yaml` (e.g. from
  `rtl-buddy-proj-template/design/sandbox`) into the new dataclasses succeeds and produces
  field-equivalent objects to rtl_buddy's.
- `TestResults.is_pass()` matches rtl_buddy semantics exactly (table in [02](../02-payload-conventions.md)).
- `UVMConfig` rejects negative `max_warns`/`max_errors` at construction.

## Constraints

- Preserve rtl_buddy's YAML field names exactly as `field(rename=...)` targets — keep
  hyphens and unusual casing (`rtl-buddy-filetype`, `cfg-rtl-builder`, `cfg-platforms`,
  `cfg-rtl-reg`, `cfg-verible`). Do **not** Pythonify them.
- `TestResults.is_pass()` must return `True` for `PASS`/`SKIP` only — never for FAIL / NA /
  timeout / compile-fail / early-stop.
- `UVMConfig.__post_init__` must raise `ValueError` (not `log.critical`) on a negative
  `max_warns`/`max_errors`; promoting that to `log.critical` is `parse-suite-config`'s job
  (spec [04h](04h-parse-suite-config.md)), not this dataclass's.
- These are pure `@serde` value objects: no `run()`, no ports, no graph awareness, no logging.
  The harness never loads them directly.

## Notes

Drop-in field-name compatibility is the contract with downstream users. Do **not** rename
fields to be more Pythonic — preserve hyphens and unusual cases as serde rename targets.
