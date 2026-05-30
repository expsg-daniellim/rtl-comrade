# Spec 01: Shared schema

**Depends on:** spec 00.
**References:** [07 settled 1](../07-ambiguities-and-assumptions.md).

## Goal

Reimplement the configuration dataclasses and shared types — preserving rtl_buddy's YAML
field names/structure so existing `root_config.yaml`, `tests.yaml`, `models.yaml`, and
`regressions.yaml` files load drop-in. This is the foundation every setup/post module
depends on.

## Deliverables

A new package, e.g. `modules/rtl_test/schema/`:

- `root.py` — `RootConfigFile`, `RootRtlField`, `PlatformConfigFile`, `PlatformConfig`,
  `RtlBuilderConfig`, `RtlBuilderConfigOpts`, `VeribleConfigFile`, `VeribleConfig`.
  Serde-decorated dataclasses with `field(rename=...)` matching rtl_buddy field names
  exactly (`rtl-buddy-filetype`, `cfg-rtl-builder`, `cfg-platforms`, `cfg-rtl-reg`,
  `cfg-verible`, `builder-opts`, `compile-time`, `run-time`, `sim-rand-seed`,
  `sim-rand-seed-prefix`, `builder-simv`).
- `suite.py` — `SuiteConfigFile`, `TestbenchConfig`, `TestConfigFile` (raw, with
  `reglvl`, `plusargs` → `pa`, `plusdefines` → `pd`, `preproc`/`postproc`/`sweep` path
  extraction, `testbench` → `tb`, `sim_timeout` → `timeout`), runtime `TestConfig` with
  getters/setters and `get_reglvl(builder)`/`get_timeout()` semantics.
- `model.py` — `ModelConfig`, `ModelConfigFile`, `ModelConfigLoader`.
- `uvm.py` — `UVMConfig` with `max_warns`/`max_errors` (`__post_init__` raising on
  negatives).
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

## Notes

Drop-in field-name compatibility is the contract with downstream users. Do **not** rename
fields to be more Pythonic — preserve hyphens and unusual cases as serde rename targets.
