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
`01a`, `01b`, `01c`) build into the shared `modules/rtl_buddy/schema/` package — coordinate the
module layout with the others.

## Goal

Reimplement the configuration dataclasses and shared types — preserving rtl_buddy's YAML
field names/structure so existing `root_config.yaml`, `tests.yaml`, `models.yaml`, and
`regressions.yaml` files load drop-in. This is the foundation every setup/post module
depends on.

## Deliverables

A new package, `modules/rtl_buddy/schema/`:

- `root.py` — `RootConfigFile`, `RootRtlField`, `PlatformConfigFile` (raw `@serde`
  dataclasses) and the runtime wrapper `RootConfig`. **Field tables in
  [§ `root.py` schema](#rootpy-schema-detailed) below** — this umbrella spec owns these types
  outright (no `01d`), so they are specified here to 01a/01b/01c depth. `field(rename=...)`
  matches rtl_buddy names exactly (`rtl-buddy-filetype`, `cfg-rtl-builder`, `cfg-platforms`,
  `cfg-rtl-reg`). **Verible is dropped** (settled, R3): no `VeribleConfigFile`/`VeribleConfig`,
  and the `cfg-verible` (root) / `verible` (per-platform) keys are left **unparsed** — pyserde
  silently ignores unknown keys, so a real `root_config.yaml` still loads drop-in. The resolved
  runtime `PlatformConfig` is also **not** built: Plan B never calls rtl_buddy's
  `platform.initialise`; platform selection and builder resolution are graph nodes
  ([04d](04d-select-platform.md) / [04e](04e-resolve-builder.md)).
- `builder.py` — `RtlBuilderConfig`, `RtlBuilderConfigOpts`, `process_opts`. Owned by
  spec [01a](01a-builder-schema.md); listed here only so this umbrella spec stays
  complete. Build 01a in parallel with the rest of 01.
- `suite.py` — `SuiteConfigFile`, `SuiteConfig`, `TestbenchConfig`, `TestConfigFile` (raw),
  `TestConfig` (runtime); and `uvm.py` — `UVMConfig` (kept separate: `parse-uvm-log` is its
  only consumer). Owned by spec [01b](01b-suite-schema.md). Build 01b in parallel with the rest
  of 01.
- `model.py` — `ModelConfig`, `ModelConfigFile`, `ModelConfigLoader`. Owned by spec
  [01c](01c-model-schema.md). Build 01c in parallel with the rest of 01.
- `results.py` — `TestResults` base + `TestPassResults`, `CompileFailResults`,
  `EarlyStopResults(desc)`, `SimTimeoutResults`, `SkipResults(desc)`. `is_pass()` returns
  `True` for `PASS`/`SKIP` only. Also a module-level factory
  `make_fail_result(desc: str) -> TestResults` returning a base `TestResults` with
  `results={"result": "FAIL", "desc": desc}` — the generic per-test FAIL used by the modules
  that have no dedicated subclass (`load-model`, `expand-sweep`, `run-preproc`,
  `write-filelist`, `resolve-seed`, `parse-log`, `parse-uvm-log`; mirrors rtl_buddy's
  direct `TestResults(... {"result": "FAIL", ...})` construction in `vlog_post.py`).
- `seed_mode.py` — `SeedMode` enum with `NEW`/`REPLAY`/`DEFAULT`.

## `root.py` schema (detailed)

These types are owned by this spec (no child ticket). Raw `@serde` dataclasses are faithful
ports of rtl_buddy's `config/root.py` + `config/platform.py`; `RootConfig` is a **Plan-B
redesign** (detailed in its subsection below). Source pin: `v1.4.0` / `a69d962`.

### `RootRtlField` (raw, `@serde`)

| field  | type  | YAML rename    | default  | notes                                                                          |
|--------|-------|----------------|----------|--------------------------------------------------------------------------------|
| `path` | `str` | `reg-cfg-path` | required | Reg-config path, relative to the root-config dir. Read by the regression sibling graph ([08](../08-sibling-graphs.md)). |

Source: `rtl_buddy/src/rtl_buddy/config/root.py:38-40`.

### `RootConfigFile` (raw, `@serde`)

| field         | type                          | YAML rename          | default               | notes                                                                 |
|---------------|-------------------------------|----------------------|-----------------------|-----------------------------------------------------------------------|
| `filetype`    | `Literal['project_root_config']` | `rtl-buddy-filetype` | required           | Tag literal.                                                          |
| `cfg_rtl_reg` | `RootRtlField`                | `cfg-rtl-reg`        | required              | Reg-path holder.                                                      |
| `builders`    | `list[RtlBuilderConfig]`      | `cfg-rtl-builder`    | required              | Builder list (`RtlBuilderConfig` owned by [01a](01a-builder-schema.md)). |
| `platforms`   | `list[PlatformConfigFile]`    | `cfg-platforms`      | required              | Platform list.                                                        |

The `cfg-verible` key is **not** a field — left unparsed (pyserde ignores it). Source:
`rtl_buddy/src/rtl_buddy/config/root.py:42-48` (minus the `veribles` field).

### `PlatformConfigFile` (raw, `@serde`)

| field    | type          | YAML rename | default  | notes                                                              |
|----------|---------------|-------------|----------|--------------------------------------------------------------------|
| `os`     | `str`         | (none)      | required | OS label.                                                          |
| `unames` | `list[str]`   | (none)      | required | Matched against `uname` output by [`select-platform`](04d-select-platform.md). |
| `builder`| `str \| None` | (none)      | required | Builder **name** (not an object); resolved by [`resolve-builder`](04e-resolve-builder.md) against `RootConfig.rtl_builder_cfgs`. |

The per-platform `verible` key is **not** a field — left unparsed. No `initialise`/`get_*`
methods are ported (platform selection + builder resolution are nodes). Source:
`rtl_buddy/src/rtl_buddy/config/platform.py:56-61` (raw fields only).

### `RootConfig` (runtime wrapper) — Plan-B redesign

rtl_buddy's `RootConfig.__init__(name, builder_override=None)` discovers + loads the YAML and
selects the platform/builder/verible/reg in one constructor (`root.py:50-231`). Plan B has
already split every one of those into nodes (discover = [04a](04a-discover-config-file.md),
load/parse = [04c](04c-parse-root-config.md), platform-match = [04d](04d-select-platform.md),
builder-resolve = [04e](04e-resolve-builder.md)), so Plan B's `RootConfig` is a **thin wrapper
over an already-parsed `RootConfigFile`** whose only transform is precomputing the builders
dict (mirrors `root.py:94`).

| member                              | type                            | source / body                                  | notes                                                                  |
|-------------------------------------|---------------------------------|------------------------------------------------|------------------------------------------------------------------------|
| `__init__(self, raw: RootConfigFile)` | —                             | store/derive the members below                 | Wrap only — no discovery, no `uname`, no reg/verible resolution.       |
| `platforms`                         | `list[PlatformConfigFile]`      | `raw.platforms`                                | Passthrough; read by `select-platform`.                                |
| `rtl_builder_cfgs`                  | `dict[str, RtlBuilderConfig]`   | `{c.get_name(): c for c in raw.builders}`      | The builders dict (keyed by name); read by `resolve-builder`. Mirrors `root.py:94`. |
| `cfg_rtl_reg`                       | `RootRtlField`                  | `raw.cfg_rtl_reg`                              | Passthrough; reg path for the regression sibling graph ([08](../08-sibling-graphs.md)). |

**Dropped vs rtl_buddy's `RootConfig`** (each is now a node or unused): `name`,
`root_cfg_path`, `builder_override`, `platform_cfg`, `verible_cfgs`, `reg_cfg`, and all the
`get_*` / `discover_rtl_builder_names` methods. The resolved runtime `PlatformConfig` and both
`VeribleConfig*` types are not deliverables.

## Acceptance criteria

- Loading an unmodified rtl_buddy `root_config.yaml` and `tests.yaml` (e.g. from
  `rtl-buddy-proj-template/design/sandbox`) into the new dataclasses succeeds and produces
  field-equivalent objects to rtl_buddy's — **including** files carrying `cfg-verible` and
  per-platform `verible` keys, which load (ignored) without error.
- `RootConfig(raw)` exposes `platforms`, `rtl_builder_cfgs` (keyed by builder name), and
  `cfg_rtl_reg`; `rtl_builder_cfgs` contains every `cfg-rtl-builder` entry keyed by `get_name()`.
- `TestResults.is_pass()` matches rtl_buddy semantics exactly (table in [02](../02-payload-conventions.md)).
- `UVMConfig` rejects negative `max_warns`/`max_errors` at construction.

## Constraints

- Preserve rtl_buddy's YAML field names exactly as `field(rename=...)` targets — keep
  hyphens and unusual casing (`rtl-buddy-filetype`, `cfg-rtl-builder`, `cfg-platforms`,
  `cfg-rtl-reg`). Do **not** Pythonify them. `cfg-verible` (and the per-platform `verible`)
  are deliberately **not** declared as fields — pyserde ignores the unknown keys, so the
  drop-in file still loads (settled, R3).
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
