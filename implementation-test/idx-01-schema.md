# idx-01 — Schema (group index)

> Navigation only — not a build ticket. The buildable units are the child specs under [`specs/`](specs/).

**References:** [02 — payload conventions](02-payload-conventions.md) (canonical type +
`is_pass()` table), [07 settled 1](07-ambiguities-and-assumptions.md).

## Goal

Reimplement rtl_buddy's configuration dataclasses and shared value types, preserving the YAML
field names/structure so existing `root_config.yaml`, `tests.yaml`, `models.yaml`, and
`regressions.yaml` files load drop-in. This is the foundation every setup/post module depends on.

All four specs are `@serde` value objects the harness never loads directly, and they build into
one shared package, `modules/rtl_buddy/schema/` — coordinate the package layout across them. They
have no logic dependency on each other and can run in parallel from the start (01b carries a
type-annotation-only dependency on 01c for `TestConfig.model`).

| Spec | File(s) | Owns |
|---|---|---|
| [01 core](specs/01-shared-schema.md) | `root.py`, `results.py`, `seed_mode.py` | `RootConfigFile`/`RootRtlField`/`PlatformConfigFile` + the `RootConfig` runtime wrapper; the `TestResults` hierarchy + `make_fail_result`; the `SeedMode` enum. |
| [01a builder](specs/01a-builder-schema.md) | `builder.py` | `RtlBuilderConfig`, `RtlBuilderConfigOpts`, `process_opts`. |
| [01b suite](specs/01b-suite-schema.md) | `suite.py`, `uvm.py` | `SuiteConfigFile`/`SuiteConfig`/`TestbenchConfig`/`TestConfigFile`/`TestConfig`; `UVMConfig` (kept separate — `parse-uvm-log` is its only consumer). |
| [01c model](specs/01c-model-schema.md) | `model.py` | `ModelConfig`, `ModelConfigFile`, `ModelConfigLoader`. |

## Schema fan-in

Downstream consumers, by owning spec:

- **01 core** → every setup/post module (`RootConfig` via 04, `TestResults` everywhere, `SeedMode` via 04i/08b).
- **01a** → 05 (`filter-reglvl`), 07/08 (`build-compile-cmd`/`build-sim-cmd`).
- **01b** → 04/05/06/07/08/09 (`SuiteConfig`/`TestConfig` read from `ctx["test"]`; `UVMConfig` → 09c).
- **01c** → 05 (`load-model`), 06 (`write-filelist`).

## Constraints (shared)

Preserve rtl_buddy's YAML field names exactly as `field(rename=...)` targets — keep hyphens and
unusual casing; do **not** Pythonify them. These are pure `@serde` value objects: no `run()`, no
ports, no graph awareness, no logging. Each spec carries its own field tables and validation
rules.
