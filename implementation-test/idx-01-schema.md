# idx-01 — Schema (group index)

> Navigation only — not a build ticket. The buildable units are the child specs under [`specs/`](specs/).

**References:** [02 — payload conventions](02-payload-conventions.md) (canonical type +
`is_pass()` table), [07 settled 1](07-ambiguities-and-assumptions.md).

## Goal

Reimplement rtl_buddy's configuration dataclasses and shared value types, preserving the YAML
field names/structure so existing `root_config.yaml`, `tests.yaml`, `models.yaml`, and
`regressions.yaml` files load drop-in. This is the foundation every setup/post module depends on.

All four specs define `@serde`/value objects the harness never loads directly. The
**edge-borne runtime/value types** build into one shared package, `modules/rtl_buddy/schema/`;
the **raw read-once containers and loaders** are defined privately with their consuming module
(see the note under the table below). The schema package's `__init__.py` — the public re-export
surface, enumerating every edge-borne schema class up front — is owned **solely by spec 01**;
01a/01b/01c add no exports and never edit it, so the four specs write disjoint files. Consumers
import from the package root (`from modules.rtl_buddy.schema import …`). They have no logic
dependency on each other and can all run in parallel from the start. (01b no longer depends on
01c even for a type annotation: under the split-edge model the resolved `ModelConfig` rides its
own `model` edge rather than living on `TestConfig`, so `suite.py` never references `model.py`.)

| Spec | File(s) | Owns |
|---|---|---|
| [01 core](specs/01-shared-schema.md) | `root.py`, `results.py`, `seed_mode.py`, `run_depth.py`, `__init__.py` | `RootRtlField`/`PlatformConfig` + the `RootConfig` runtime holder; the single `TestResult` value object (with `@classmethod` constructors `compile_fail`/`sim_timeout`/`early_stop`/`skip`/`prep`/`parse`) + the `ResultType` enum; the `SeedMode` and `RunDepth` enums; the package `__init__.py` re-export surface (sole owner). |
| [01a builder](specs/01a-builder-schema.md) | `builder.py` | `RtlBuilderConfig`, `RtlBuilderConfigOpts`, `process_opts`. |
| [01b suite](specs/01b-suite-schema.md) | `suite.py`, `uvm.py` | `SuiteConfig`/`TestbenchConfig`/`TestConfig`; `UVMConfig` (kept separate — `parse-uvm-log` is its only consumer). |
| [01c model](specs/01c-model-schema.md) | `model.py` | `ModelConfig`. |

**Raw read-once containers live with their consuming module, not here.** The top-level `@serde` types that are deserialised and immediately unwrapped (`RootConfigFile`), or used only to answer a lookup (`SuiteConfigFile`/`TestConfigFile` + their inline raw→runtime conversion, `ModelConfigFileItem`/`ModelConfigFile` from which `load-model` constructs `ModelConfig`, unrolling rtl_buddy's `ModelConfigLoader`), never ride a graph edge. They are defined privately with their sole consumer — `parse-root-config` ([04c](specs/04c-parse-root-config.md)), `parse-suite-config` ([04h](specs/04h-parse-suite-config.md)), `load-model` ([05e](specs/05e-load-model.md)) — and are **not** re-exported from the schema package. The schema package holds only the runtime/value types that cross `ctx` edges.

## Schema fan-in

Downstream consumers, by owning spec:

- **01 core** → every setup/post module (`RootConfig` via 04, `TestResult` everywhere, `SeedMode` via 04i/08b).
- **01a** → 05 (`filter-reglvl`), 07/08 (`build-compile-cmd`/`build-sim-cmd`).
- **01b** → 04/05/06/07/08/09 (`SuiteConfig`/`TestConfig` read from `test`; `UVMConfig` → 09c).
- **01c** → 05 (`load-model`), 06 (`write-filelist`).

## Constraints (shared)

Preserve rtl_buddy's YAML field names exactly as `field(rename=...)` targets — keep hyphens and
unusual casing; do **not** Pythonify them. These are pure `@serde` value objects: no `run()`, no
ports, no graph awareness, no logging. Each spec carries its own field tables and validation
rules.
