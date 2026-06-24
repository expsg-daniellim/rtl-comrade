# Spec 01: Core schema (root config, results, seed-mode)

**Depends on:** none.
**References:** [07 settled 1](../07-ambiguities-and-assumptions.md). Schema family overview: [idx-01 — Schema](../idx-01-schema.md).

## Before you start

These are `@serde`-decorated dataclasses that the harness never loads directly — a faithful port of rtl_buddy's config types, so the authoritative reference is the rtl_buddy `config/*.py` source this spec cites (anchored to `v1.4.0`, commit `a69d962`). The in-repo `@serde` idiom — nested types and `field(rename=...)` for verbatim YAML field names — is shown by the config-bearing example in `docs/modules/implementation.md`; [`02 — payload conventions`](../02-payload-conventions.md) holds the canonical type and `is_pass()` table the port must match. This spec owns six files of the shared `modules/rtl_buddy/schema/` package — `root.py`, `results.py`, `seed_mode.py`, `run_depth.py`, `payloads.py`, and the package `__init__.py` (the sole re-export surface); its sibling specs `01a`/`01b`/`01c` own the rest and contribute **no** entries to `__init__.py`, so all four specs write disjoint files (family overview: [idx-01](../idx-01-schema.md)).

## Goal

Reimplement the core/shared schema — the root-config types, the `TestResults` hierarchy, the `SeedMode` enum, the `RunDepth` phase enum, and the **edge-payload dataclasses** every module produces/consumes — preserving rtl_buddy's YAML field names/structure so existing `root_config.yaml` files load drop-in. These are the foundation every setup/post module depends on (the builder/suite/model dataclasses are split into [01a](01a-builder-schema.md) / [01b](01b-suite-schema.md) / [01c](01c-model-schema.md)).

## Deliverables

Six files in the shared `modules/rtl_buddy/schema/` package (its `builder.py`/`suite.py`/ `uvm.py`/`model.py` are owned by 01a/01b/01c — see [idx-01](../idx-01-schema.md)):

- `root.py` — `RootRtlField`, `PlatformConfig` (raw `@serde` nested value types that ride inside the runtime `RootConfig` and are read downstream by `select-platform`/`resolve-builder`/the regression sibling) and the runtime `RootConfig` holder. **Field tables in [§ `root.py` schema](#rootpy-schema-detailed) below** — this spec owns these types outright (no `01d`), so they are specified here to 01a/01b/01c depth. The top-level **`RootConfigFile`** container is **not** here: it is read once by `from_yaml` and immediately unwrapped, so it never rides a graph edge — it is defined with its sole consumer, `parse-root-config` (spec [04c](04c-parse-root-config.md)). `RootRtlField`'s `field(rename=...)` matches rtl_buddy exactly (`reg-cfg-path`); `PlatformConfig` has no renames. **Verible is dropped**: no `VeribleConfigFile`/`VeribleConfig`, and the per-platform `verible` key is left **unparsed** on `PlatformConfig` (pyserde silently ignores unknown keys, so a real `root_config.yaml` still loads drop-in); the root `cfg-verible` key is likewise dropped on `RootConfigFile` (spec 04c). rtl_buddy's **resolved** runtime platform object (the value `platform.initialise` returns, named `PlatformConfig` upstream) is **not** built: this plan never calls `platform.initialise`; the raw `PlatformConfig` above rides the edge directly, and platform selection and builder resolution are graph nodes ([04d](04d-select-platform.md) / [04e](04e-resolve-builder.md)).
- `results.py` — `TestResults` base + `TestPassResults`, `CompileFailResults`, `EarlyStopResults(desc)`, `SimTimeoutResults`, `SkipResults(desc)`. Each subclass's `results` dict is a faithful port of rtl_buddy `runner/test_results.py:10-78` — the **exact** `{result, desc}` per class (no `name` key in this plan; the key rides the edge, not the object):

  | class | `result` | `desc` |
  |---|---|---|
  | base `TestResults` (default) | `"NA"` | `"NA"` |
  | `TestPassResults` | `"PASS"` | `"Generic test pass"` |
  | `CompileFailResults` | `"FAIL"` | `"Compile failed"` |
  | `SimTimeoutResults` | `"FAIL"` | `"Sim hit timeout"` |
  | `EarlyStopResults(desc)` | `"NA"` | caller's `desc` (gate passes `f"Stopped early at {phase}"`, spec [10a](10a-early-stop-gate.md)) |
  | `SkipResults(desc)` | `"SKIP"` | caller's `desc` (filter passes the `lvl … cmd …level …` string, spec [05d](05d-filter-reglvl.md)) |

  `is_pass()` returns `True` for `PASS`/`SKIP` only. Also a module-level factory `make_fail_result(desc: str) -> TestResults` returning a base `TestResults` with `results={"result": "FAIL", "desc": desc}` — the generic per-test FAIL used by the modules that have no dedicated subclass (`load-model`, `expand-sweep`, `run-preproc`, `write-filelist`, `resolve-seed`, `parse-log`, `parse-uvm-log`; mirrors rtl_buddy's direct `TestResults(... {"result": "FAIL", ...})` construction in `vlog_post.py`).
- `seed_mode.py` — `SeedMode` enum with `NEW`/`REPLAY`/`DEFAULT`.
- `run_depth.py` — `RunDepth` enum with `PRE = "pre"`, `COMP = "comp"`, `SIM = "sim"`, `POST = "post"`, in that declaration order (a faithful port of rtl_buddy's `RunDepth` at `runner/test_runner.py:14-18`). This is the **single source** of the early-stop phase ordering: `early-stop-gate` (spec [10a](10a-early-stop-gate.md)) derives its `order` from `[d.value for d in RunDepth]` (`pre < comp < sim < post`) rather than re-listing the tokens. Pure enum — no methods, no graph awareness.
- `payloads.py` — the edge-payload dataclasses [`02 — payload conventions`](../02-payload-conventions.md) catalogues as Shapes 1/2/3. The correlation field `keyed_join` matches on is named by the contract's `keyed_field` (default `"key"`, which the test graph uses throughout); `contracts/keyed_join.py::_key_of` reads it attribute-first, falling back to a dict entry. A payload carries its **own** `key` field exactly when the key is its own identity: the **multi-field messages** (cohesive, key is one of their fields) and **`TestConfig`** (its `key` *is* the scheduled-test instance — it rides the `test` edge bare, [01b](01b-suite-schema.md)). The other single-value edges ride the generic `KeyedValue[T]` envelope because the key is *not* the value's own identity — a primitive (`int`/`Path`/`str`) has no identity, and `model` is keyed by the **test's** identity (so `write-filelist` can join it back), foreign to the `ModelConfig`. The set:

  | class | fields | `frozen` | shape | edges |
  |---|---|---|---|---|
  | `KeyedValue[T]` | `key: str`, `value: T` | yes | Shape 1 (generic single-value envelope) | `model`, `simv`, `run_id`, `seed`, `timeout`, `filelist` — the edge name conveys what `T` is (`test` is **not** here — it rides the bare self-keyed `TestConfig`) |
  | `Command` | `key: str`, `argv: list[str]`, `stdout_path: Path`, `stderr_path: Path` | yes | Shape 2 (cohesive message) | `build-*-cmd` → `run-process` |
  | `Proc` | `key: str`, `rc: int \| None`, `stdout_path: Path`, `stderr_path: Path` | yes | Shape 2 | `run-process` → `interpret-*` / post-sim (`rc is None` ⟺ timed out) |
  | `RandSeed` | `key: str`, `seed: int`, `randseed_path: Path`, `argv: list[str]` | yes | Shape 2 | `build-sim-cmd` → `write-randseed` / `link-latest` |
  | `RandSeedDone` | `key: str` | yes | Shape 2 (ordering signal) | `write-randseed` → `link-latest` |
  | `Result` | `key: str`, `result: TestResults` | yes | Shape 3 (terminal) | every terminal port |

  `KeyedValue` is `Generic[T]` so the single envelope stays typed per enveloped edge (`KeyedValue[ModelConfig]`, `KeyedValue[float | None]`, …) without a named class per single-value edge — the design point [02](../02-payload-conventions.md) records as "the edge name conveys the type." Like all payload types here it is `frozen=True`: freezing blocks rebinding `.key`/`.value` (which no node does), but not mutating the object `.value` points at. The `test` edge is **not** enveloped — `run-preproc` mutates the bare `TestConfig` directly (it is unfrozen, [01b](01b-suite-schema.md)), and `expand-runs` re-keys it via `dataclasses.replace`; the still-enveloped `model` edge is a frozen `KeyedValue` around a frozen `ModelConfig`. `Result.result` holds the `TestResults` built in this spec; `result` the field is distinct from `Result` the class. No `__init__` logic on any of them — plain frozen value holders. **Non-keyed payloads are not here:** the broadcast config singletons (`RootConfig`, `RtlBuilderConfig`, `logs_dir`/`Path`) and pure ordering tokens (`env_ready: bool`) ride as their own schema types or bare values, carry no key, and reach their consumers as `persistent_inputs` rather than through keyed correlation (the persistent branch of `keyed_join._store` handles keyless payloads via broadcast).
- `__init__.py` — the package's **public re-export surface**, owned solely by this spec. It enumerates every schema class up front so consumers import from the package root (`from modules.rtl_buddy.schema import …`): `RootConfig`, `RootRtlField`, `PlatformConfig`, the `TestResults` hierarchy + `make_fail_result`, `SeedMode`, `RunDepth`, the payload dataclasses (`KeyedValue`, `Command`, `Proc`, `RandSeed`, `RandSeedDone`, `Result`) (this spec), plus `RtlBuilderConfig`/`RtlBuilderConfigOpts` (01a), `SuiteConfig`/`TestConfig`/`TestbenchConfig`/`UVMConfig` (01b), and `ModelConfig` (01c). The raw read-once serde types (`RootConfigFile`, `SuiteConfigFile`/`TestConfigFile`, `ModelConfigFileItem`/`ModelConfigFile`) are **deliberately not re-exported** — they never ride a graph edge and are defined privately with their consuming modules (`parse-root-config` [04c], `parse-suite-config` [04h], `load-model` [05e]; `load-model` reads `ModelConfigFileItem`s and constructs `ModelConfig`, unrolling rtl_buddy's `ModelConfigLoader`). Sibling specs add **no** entries here and never edit this file, so the four specs touch disjoint files and can run in parallel safely. The re-exported names are agreed up front (this list + [idx-01](../idx-01-schema.md)); each name resolves once its owning spec lands.

## `root.py` schema (detailed)

These types are owned by this spec (no child ticket). The raw `@serde` value types are faithful ports of rtl_buddy's `config/root.py` + `config/platform.py`; `RootConfig` is a **redesign in this plan** (detailed in its subsection below). Source pin: `v1.4.0` / `a69d962`. The top-level `RootConfigFile` container that wraps these is **not** owned here — it is parse-internal and specified in spec [04c](04c-parse-root-config.md); `from_yaml(RootConfigFile, …)` there deserialises the `RootRtlField`/`PlatformConfig` defined below as nested members.

### `RootRtlField` (raw, `@serde`)

| field  | type  | YAML rename    | default  | notes                                                                          |
|--------|-------|----------------|----------|--------------------------------------------------------------------------------|
| `path` | `str` | `reg-cfg-path` | required | Reg-config path, relative to the root-config dir. Read by the regression sibling graph ([08](../08-sibling-graphs.md)). |

Source: `rtl_buddy/src/rtl_buddy/config/root.py:38-40`.

### `PlatformConfig` (raw, `@serde`)

| field    | type          | YAML rename | default  | notes                                                              |
|----------|---------------|-------------|----------|--------------------------------------------------------------------|
| `os`     | `str`         | (none)      | required | OS label.                                                          |
| `unames` | `list[str]`   | (none)      | required | Matched against `uname` output by [`select-platform`](04d-select-platform.md). |
| `builder`| `str \| None` | (none)      | required | Builder **name** (not an object); resolved by [`resolve-builder`](04e-resolve-builder.md) against `RootConfig.rtl_builder_cfgs`. |

The per-platform `verible` key is **not** a field — left unparsed. No `initialise`/`get_*` methods are ported (platform selection + builder resolution are nodes). Source: `rtl_buddy/src/rtl_buddy/config/platform.py:56-61` (raw fields only).

### `RootConfig` (runtime wrapper) — redesign in this plan

rtl_buddy's `RootConfig.__init__(name, builder_override=None)` discovers + loads the YAML and selects the platform/builder/verible/reg in one constructor (`root.py:50-231`). This plan has already split every one of those into nodes (discover = [04a](04a-discover-config-file.md), load/parse = [04c](04c-parse-root-config.md), platform-match = [04d](04d-select-platform.md), builder-resolve = [04e](04e-resolve-builder.md)), so this plan's `RootConfig` is a **plain runtime holder** of the three already-derived members below. The one transform — precomputing the builders dict (mirrors `root.py:94`) — happens in `parse-root-config` (spec [04c](04c-parse-root-config.md)), which constructs this holder from the raw `RootConfigFile` it just loaded; `RootConfig` itself takes the derived members directly (it does **not** import or reference `RootConfigFile`, which keeps the schema package free of the parse-internal container).

| member             | type                            | source / body (filled by `parse-root-config`)  | notes                                                                  |
|--------------------|---------------------------------|------------------------------------------------|------------------------------------------------------------------------|
| `platforms`        | `list[PlatformConfig]`      | `raw.platforms`                                | Passthrough; read by `select-platform`.                                |
| `rtl_builder_cfgs` | `dict[str, RtlBuilderConfig]`   | `{c.get_name(): c for c in raw.builders}`      | The builders dict (keyed by name); read by `resolve-builder`. Mirrors `root.py:94`. |
| `cfg_rtl_reg`      | `RootRtlField`                  | `raw.cfg_rtl_reg`                              | Passthrough; reg path for the regression sibling graph ([08](../08-sibling-graphs.md)). |

`RootConfig` is a `@dataclass` over exactly these three fields — a plain value holder with no `__init__` logic of its own; `parse-root-config` derives the members and constructs it.

**Dropped vs rtl_buddy's `RootConfig`** (each is now a node or unused): `name`, `root_cfg_path`, `builder_override`, `platform_cfg`, `verible_cfgs`, `reg_cfg`, and all the `get_*` / `discover_rtl_builder_names` methods. rtl_buddy's resolved runtime platform object (the `PlatformConfig` returned by `platform.initialise`) and both `VeribleConfig*` types are not deliverables.

## Acceptance criteria

- `RootConfig` is a `@dataclass` exposing `platforms`, `rtl_builder_cfgs`, and `cfg_rtl_reg`; a hand-constructed instance round-trips its members. (The end-to-end drop-in YAML load — that an unmodified `root_config.yaml` deserialises into these nested types and produces a field-equivalent `RootConfig`, `cfg-verible`/per-platform `verible` keys ignored — is exercised by `parse-root-config`, spec [04c](04c-parse-root-config.md), which owns `RootConfigFile` and the `from_yaml` call.)
- The nested value types `RootRtlField` and `PlatformConfig` deserialise from their rtl_buddy YAML shapes (the per-platform `verible` key ignored on `PlatformConfig`).
- `TestResults.is_pass()` matches rtl_buddy semantics exactly (table in [02](../02-payload-conventions.md)).
- Every payload dataclass here is `frozen=True` (`KeyedValue` included — frozen blocks rebinding `.value`, not mutating the `TestConfig` it points at) and exposes the correlation field `keyed_join` reads via `_key_of` (default `keyed_field="key"`, attribute-first). `KeyedValue` is `Generic[T]`. A hand-constructed instance of each round-trips its fields, and `run-preproc`-style in-place mutation of a wrapped `TestConfig` succeeds through the frozen envelope.

## Constraints

- Preserve rtl_buddy's YAML field names exactly as `field(rename=...)` targets — keep hyphens and unusual casing. For the types this spec owns that means `reg-cfg-path` (`RootRtlField`); `PlatformConfig` has no renames. Do **not** Pythonify them. The per-platform `verible` key is deliberately **not** declared as a field on `PlatformConfig` — pyserde ignores the unknown key, so the drop-in file still loads. (The `rtl-buddy-filetype`/`cfg-rtl-builder`/`cfg-platforms`/`cfg-rtl-reg` renames and the root `cfg-verible` drop live on `RootConfigFile`, spec [04c](04c-parse-root-config.md).)
- `TestResults.is_pass()` must return `True` for `PASS`/`SKIP` only — never for FAIL / NA / timeout / compile-fail / early-stop.
- The `@serde`/value types here are pure value objects: no `run()`, no ports, no graph awareness, no logging. The harness never loads them directly. (`RootConfig` is likewise a plain holder — the parse/derive logic lives in `parse-root-config`.)

## Notes

Drop-in field-name compatibility is the contract with downstream users. Do **not** rename fields to be more Pythonic — preserve hyphens and unusual cases as serde rename targets.
