# Spec 01b: Suite / Test / UVM schema

**Depends on:** none — runs fully in parallel with 01/01a/01c. Adds **no** entries to the package `__init__.py` — spec 01 owns the sole re-export surface — so it never edits a file another spec touches.
**References:** [idx-01](../idx-01-schema.md) (umbrella), [07 settled 1, 8](../07-ambiguities-and-assumptions.md).
**Source** (this spec owns the runtime/value types only; the raw `SuiteConfigFile`/`TestConfigFile` are ported in [04h](04h-parse-suite-config.md)):
- `rtl_buddy/src/rtl_buddy/config/suite.py:17-86` (`SuiteConfig` runtime).
- `rtl_buddy/src/rtl_buddy/config/test.py:10-302` (`TestbenchConfig`, `TestConfig`).
- `rtl_buddy/src/rtl_buddy/config/uvm.py:1-19` (`UVMConfig`).

## Before you start

These are `@serde`-decorated dataclasses that the harness never loads directly — a faithful port of rtl_buddy's config types, so the authoritative reference is the rtl_buddy `config/*.py` source this spec cites (anchored to `v1.4.0`, commit `a69d962`). The in-repo `@serde` idiom — nested types and `field(rename=...)` for verbatim YAML field names — is shown by the config-bearing example in `docs/modules/implementation.md`; [`02 — payload conventions`](../02-payload-conventions.md) holds the canonical type and `is_pass()` table the port must match. All four schema specs (`01`, `01a`, `01b`, `01c`) build into the shared `modules/rtl_buddy/schema/` package — coordinate the module layout with the others.

## Goal

Reimplement the `tests.yaml` schema natively so consumers (`select-tests`, `filter-reglvl`, `load-model`, `expand-sweep`, `run-preproc`, `write-filelist`, `build-compile-cmd`, `build-sim-cmd`, `route-post`, `parse-uvm-log`) can use the schema by field/method without opening `rtl_buddy`. Preserves the YAML field-name surface so existing `tests.yaml` files load drop-in (see [07 settled 1](../07-ambiguities-and-assumptions.md)).

## Deliverables

Two files in the schema package:

- `modules/rtl_buddy/schema/uvm.py` — `UVMConfig` alone. Kept separate because `parse-uvm-log` (spec [09c](09c-parse-uvm-log.md)) is effectively its only consumer; the rest of the graph touches `TestConfig.uvm` only as an opaque presence/absence flag.
- `modules/rtl_buddy/schema/suite.py` — `TestbenchConfig`, `TestConfig`, `SuiteConfig` (the runtime/value types that ride graph edges). Imports `UVMConfig` from `uvm.py` for the `TestConfig.uvm: UVMConfig | None` annotation. **No** `ModelConfig` import — the resolved model is not a `TestConfig` field (it rides the `model` edge), so `suite.py` does not depend on `model.py`.

The raw `@serde` read-once containers — **`SuiteConfigFile`** and **`TestConfigFile`** (pure serde shapes) — are **not** in the schema package. They are read by `from_yaml` and immediately converted into the runtime types, so they never ride a graph edge; they are defined privately with their sole consumer, `parse-suite-config` (spec [04h](04h-parse-suite-config.md)), along with the raw→runtime conversion (done inline in its `run`, not a method on the raw type). This spec still specifies the **runtime shape** they produce (`TestConfig`/`SuiteConfig` below) so 04h has a target to build against; the raw field tables and the conversion sequence live in 04h.

### `UVMConfig` (`uvm.py`)

Per-test UVM report parsing configuration. Lives on `TestConfig.uvm`; if `None`, the plain `parse-log` path is taken (else `parse-uvm-log`).

| field         | type | YAML rename | default | notes                                                              |
|---------------|------|-------------|---------|--------------------------------------------------------------------|
| `max_warns`   | `int`| (none)      | `0`     | Maximum `UVM_WARNING` count before the test fails.                 |
| `max_errors`  | `int`| (none)      | `0`     | Maximum `UVM_ERROR` count before the test fails. (Fatal must be 0.)|

Validation: `__post_init__` raises `ValueError` if either field is negative. Note this is `ValueError`, not `log.fatal` — UVMConfig is constructed during YAML deserialisation. Under pyserde the `ValueError` propagates **raw** through `from_yaml` (it is not wrapped into a `SerdeError`), so `parse-suite-config` (spec [04h](04h-parse-suite-config.md)) catches it in a dedicated `except ValueError` clause and converts the validation failure into `log.fatal("invalid_uvm_config")`.

Source: `rtl_buddy/src/rtl_buddy/config/uvm.py:1-19`.

### `TestbenchConfig`

One per entry in `tests.yaml`'s top-level `testbenches:` list. Bound by name into each test's `tb` field during `SuiteConfig` initialisation.

| field      | type        | YAML rename | default  | notes                                            |
|------------|-------------|-------------|----------|--------------------------------------------------|
| `name`     | `str`       | (none)      | required | Unique testbench identifier.                     |
| `filelist` | `list[str]` | (none)      | required | Paths (relative to suite dir) for the testbench. |

Methods:

| signature                | returns        | log idiom |
|--------------------------|----------------|-----------|
| `get_name() -> str`      | `self.name`    | none      |
| `get_filelist() -> list[str]` | `self.filelist` | none |

Source: `rtl_buddy/src/rtl_buddy/config/test.py:10-41`.

### `TestConfigFile` (raw) — defined in `parse-suite-config`

The serde-decorated type read straight from `tests.yaml`'s `tests:` list (a pure data shape) is **owned by `parse-suite-config`** (spec [04h](04h-parse-suite-config.md#raw-schema--conversion-owned-here)) — read-once, never on a graph edge. Its raw field table (the `field(rename=...)` YAML surface: `reglvl`, `plusargs`, `plusdefines`, `preproc`/`postproc`/`sweep`, `testbench`, `sim_timeout`) and the raw→runtime conversion (done inline in the node's `run` — rtl_buddy's `TestConfigFile.initialise`, ported as node-owned logic rather than a method) live there. This spec defines only the **runtime `TestConfig`** that conversion produces (below); the raw→runtime field mapping is documented alongside the raw table in 04h.

### `TestConfig` (runtime)

The mutable per-test object carried on the `test` edge for the whole graph. Differs from rtl_buddy's `TestConfig` in two ways (see Notable divergences below).

| field            | type                | default                 | notes                                                                                                |
|------------------|---------------------|-------------------------|------------------------------------------------------------------------------------------------------|
| `name`           | `str`               | required                | From raw.                                                                                            |
| `desc`           | `str`               | required                | From raw.                                                                                            |
| `model`          | `str`               | required                | From raw (`model: str`, name unchanged). The YAML model **name** (a `str`); the resolved `ModelConfig` is **not** stored on `TestConfig` **on any edge** — it rides the separate `model` *edge* (`load-model` → `write-filelist`, spec [05e](05e-load-model.md)/[06b](06b-write-filelist.md)). The field and the edge share the name `model`: the field holds the name string, the edge carries the resolved object (rtl_buddy overwrote the field in place — this plan never does, see divergence 1). The one transient exception: the `sweep`/`preproc` hooks set this field to the resolved `ModelConfig` for the duration of their script `exec` (rtl_buddy parity — see specs [05f](05f-expand-sweep.md)/[06a](06a-run-preproc.md)) and restore the name string **before** emitting the edge, so every `test` edge still carries a `str`. |
| `model_path`     | `str`               | required                | From raw. Path to `models.yaml`, relative to `suite_dir`.                                            |
| `suite_dir`      | `Path`              | required                | Stamped by `parse-suite-config` (spec [04h](04h-parse-suite-config.md)). Resolves `model_path` for `load-model`. |
| `_reglvl`        | `int \| dict \| None`| from raw               | Underlying storage; access via `get_reglvl(builder)`.                                                |
| `pa`             | `dict \| None`      | from raw                | Mutable. `set_plusarg`/`set_plusargs` lazily initialise.                                             |
| `pd`             | `dict \| None`      | from raw                | Mutable. `set_plusdefine`/`set_plusdefines` lazily initialise.                                       |
| `uvm`            | `UVMConfig \| None` | from raw                |                                                                                                      |
| `preproc_path`   | `str \| None`       | from raw                |                                                                                                      |
| `postproc_path`  | `str \| None`       | from raw                |                                                                                                      |
| `sweep_path`     | `str \| None`       | from raw                |                                                                                                      |
| `tb`             | `TestbenchConfig`   | required                | Bound from `tbs[raw.tb]` during conversion (inline in `run`, spec [04h](04h-parse-suite-config.md)). |
| `timeout`        | `int \| None`       | from raw                | Per-test override.                                                                                   |
| `default_timeout`| `int`               | `60`                    | A field on `TestConfig` (default `60`), used by `get_timeout()` when `timeout is None`. Matches rtl_buddy's `default_timeout` field (`config/test.py:81`).            |
| `key`            | `str`               | `""`                    | **Runtime-only** (not from YAML — never deserialized; the raw `TestConfigFile` has no `key`). The scheduled-test instance's own correlation identity, the field `keyed_join` reads (`keyed_field="key"`). **Populated to the test's `name` by `__post_init__`** when left unset, so every `TestConfig` is **born self-keyed** regardless of construction site (the 04h conversion, a sweep script building a fresh one, a unit test) — `select-tests` forwards it untouched. Refined downstream: re-suffixed per variant by `expand-sweep` (spec [05f](05f-expand-sweep.md), `= f"{parent.key}#{i}"`) and per run by `expand-runs` (spec [08a](08a-expand-runs.md), `#run` via `dataclasses.replace`). Distinct from `name`, which collides across sweep variants and run-ids. **Declared last** (with `default_timeout`) so its `= ""` default is legal after the required fields; the `""` is an "unset" sentinel `__post_init__` resolves — never observable post-construction. The `test` edge carries the bare `TestConfig` (no `KeyedValue` envelope) — see [02 — payload conventions](../02-payload-conventions.md). |

`__post_init__`: `if not self.key: self.key = self.name` — populates the correlation key from the test name so every `TestConfig` is born self-keyed. The guard is **load-bearing**: `expand-runs` re-keys per run via `dataclasses.replace(test, key=nk)`, which re-runs `__init__`/`__post_init__` with a truthy `key`; an *unconditional* assignment would clobber `nk` back to `name` and break per-run keying. (This is the only `__post_init__` logic on `TestConfig`; `UVMConfig` has its own, for validation.)

Methods:

| signature                                | returns                                              | notes / log idiom                                                                                                                                         |
|------------------------------------------|------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------|
| `get_name() -> str`                      | `self.name`                                          | trivial getter.                                                                                                                                           |
| `get_testbench() -> TestbenchConfig`     | `self.tb`                                            | trivial getter.                                                                                                                                           |
| `get_plusarg(key) -> Any`                | `self.pa.get(key)`                                   | Raises `AttributeError` if `pa is None` — caller must check `get_plusargs() is not None` first (matches rtl_buddy's `vlog_sim.py:97-104` pattern).        |
| `get_plusargs() -> dict \| None`         | `self.pa`                                            | trivial getter.                                                                                                                                           |
| `set_plusarg(key, value) -> None`        | `None`                                               | Lazily inits `self.pa = {}` if `None`, then sets. Used by preproc scripts.                                                                                |
| `set_plusargs(new_args) -> None`         | `None`                                               | Lazily inits, then `update(new_args)`.                                                                                                                    |
| `get_plusdefine(key)` / `get_plusdefines()` / `set_plusdefine(key, value)` / `set_plusdefines(new_defines)` | symmetric to plusargs                       | same semantics.                                                                                                                                           |
| `get_timeout() -> tuple[int, bool]`      | `(self.timeout, True)` if `timeout is not None` else `(self.default_timeout, False)` | `is_custom` second element flags whether the caller should log a warning (rtl_buddy `vlog_sim.py:233-234` does so).                                       |
| `set_timeout(timeout) -> None`           | `None`                                               | Used by preproc scripts.                                                                                                                                  |
| `get_sweep_path() -> str \| None`        | `self.sweep_path`                                    | trivial getter.                                                                                                                                           |
| `get_preproc_path() -> str \| None`      | `self.preproc_path`                                  | trivial getter.                                                                                                                                           |
| `get_postproc_path() -> str \| None`     | `self.postproc_path`                                 | trivial getter. This plan preserves the field but does not execute postproc ([07 settled 14](../07-ambiguities-and-assumptions.md)).                         |
| `get_reglvl(builder: str) -> int`        | resolved level for the given builder name            | Resolution order: builder-keyed dict entry → `default` dict entry → uniform int → `0` (when `None`). Malformed (`dict` with no builder or default) → `log.fatal`. Mirrors `rtl_buddy/src/rtl_buddy/config/test.py:286-299`. |

Source: `rtl_buddy/src/rtl_buddy/config/test.py:43-302`.

### `SuiteConfigFile` (raw) — defined in `parse-suite-config`

The serde-decorated top-level type read straight from `tests.yaml` (`rtl-buddy-filetype` discriminator, `testbenches: list[TestbenchConfig]`, `tests: list[TestConfigFile]`) is **owned by `parse-suite-config`** (spec [04h](04h-parse-suite-config.md#raw-schema--conversion-owned-here)) — read-once, never on an edge. Its field table and the open→`from_yaml`→bind→convert sequence (inline in `run`) live there.

### `SuiteConfig` (runtime)

Produced by `parse-suite-config` (spec [04h](04h-parse-suite-config.md)) and carried on the `suite_cfg` edge. A plain `@dataclass` holder of the test dict keyed by name plus its source path — **no parsing logic of its own** (the open→bind→convert sequence is `parse-suite-config`'s; that node constructs this holder).

| field   | type                       | notes                                                                                            |
|---------|----------------------------|--------------------------------------------------------------------------------------------------|
| `path`  | `Path`                     | Resolved suite-config path (resolved by `parse-suite-config` from the `test_config` locator).         |
| `tests` | `dict[str, TestConfig]`    | The per-test runtime objects keyed by `name`; built and populated by `parse-suite-config`.       |

Methods:

| signature                              | returns                                                            | log idiom                                                                                                                       |
|----------------------------------------|--------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------|
| `get_tests(test_name: str \| None = None) -> list[TestConfig] \| dict_values[TestConfig]` | one-element list if `test_name` given and present; all tests otherwise | `log.fatal(f"test_name {name} not found in suite {self.path}")` when `test_name` given but not in `self.tests`. Mirrors `suite.py:52-67`. This plan's `select-tests` uses this same idiom (catalog row at line 112 of [03](../03-module-catalog.md)). |
| `get_test_names() -> list[str]`        | `list(self.tests.keys())`                                          | none.                                                                                                                           |
| `get_path() -> Path`                   | `self.path`                                                        | none.                                                                                                                           |

Source: `rtl_buddy/src/rtl_buddy/config/suite.py:17-86`.

## Notable divergences from rtl_buddy

1. **Lazy model loading, off-object** ([07 settled 8](../07-ambiguities-and-assumptions.md)). rtl_buddy `TestConfigFile.initialise` eagerly calls `ModelConfigLoader(model_path).get_model(self.model)` (`test.py:322`), overwriting `TestConfig.model` in place with the loaded `ModelConfig`. This plan defers loading to `load-model` (spec [05e](05e-load-model.md)) **and keeps the resolved `ModelConfig` off `TestConfig` entirely** — it rides its own `model` keyed edge, `keyed_join`ed at `write-filelist`. So `TestConfig.model` keeps the same name as rtl_buddy's field but holds **only** the YAML name string on every edge — it is never overwritten with the resolved `ModelConfig`, and `TestConfig` is never in a "model not yet loaded" state (no `model: ModelConfig | None` field). It carries `model: str`, `model_path: str`, and `suite_dir: Path` so `load-model` can resolve `suite_dir / model_path` and look up `model`. (The `sweep`/`preproc` hooks set the field to the resolved `ModelConfig` *transiently*, only for the span of their script `exec` — so a drop-in hook script sees rtl_buddy's `test_cfg.model` view — and restore the name string before the edge is emitted; specs [05f](05f-expand-sweep.md)/[06a](06a-run-preproc.md). `load-model` is positioned ahead of the hooks precisely so the resolved model exists for that.)
2. **`suite_dir` stamped on each test.** Recorded by `parse-suite-config` (spec [04h](04h-parse-suite-config.md)). Replaces rtl_buddy's `config_dir` argument to `initialise`, propagating the resolution context downstream rather than computing it at parse time.

## Tests (`modules/tests/test_suite_schema.py`)

These exercise the **runtime/value-type behaviour** owned by this spec — each constructs the schema types directly (no YAML parse). The parse-level tests (round-trip load of a real `tests.yaml`, `field(rename=...)` surface, the `preproc`/`postproc`/`sweep` deserialiser, testbench binding, and freshly-parsed lazy-model state) belong to `parse-suite-config`, which owns the raw types and the conversion — they live in `test_setup.py` (spec [04h](04h-parse-suite-config.md#tests)).

- **`get_reglvl` resolution order.** Four cases on a directly-constructed `TestConfig`: int `_reglvl` → that int regardless of builder; dict with builder key → that entry; dict with `default` only → default; `None` → `0`; dict missing both builder and `default` → `log.fatal` (caplog + bubbling-`typer.Exit`).
- **`get_timeout`.** `timeout=None` → `(60, False)`; `timeout=300` → `(300, True)`.
- **Plusarg/plusdefine mutation.** `set_plusarg("FOO", 1)` on a test with `pa is None` produces `pa == {"FOO": 1}`; `set_plusargs({"A": 1, "B": 2})` merges; `get_plusarg` reads back.
- **`key` `__post_init__` and `replace` re-key.** A directly-constructed `TestConfig(name="alu", …)` (no `key` passed) has `key == "alu"` (populated by `__post_init__`); passing `key="x"` explicitly keeps it `"x"` (the guard does not clobber). `dataclasses.replace(test, key="alu#0#1")` returns a fresh object with `key == "alu#0#1"` (the `__post_init__` guard preserves the passed key — **not** reset to `name`) while sharing `pa`/`pd`/`tb` by reference (assert `replaced.tb is test.tb`) and leaving the original's `key` untouched.
- **`UVMConfig` defaults and validation.** YAML `uvm: {}` → `max_warns == 0 == max_errors`; `max_warns: 5, max_errors: 2` round-trips; `max_warns: -1` → `ValueError` at construction (which `parse-suite-config`'s dedicated `except ValueError` clause converts to `log.fatal("invalid_uvm_config")`).
- **`SuiteConfig`/`TestbenchConfig` getters.** A directly-constructed `SuiteConfig` (with a hand-built `tests` dict) answers `get_tests()`/`get_tests(name)`/`get_test_names()`/`get_path()` per the table (incl. the `log.fatal` on an unknown `test_name`); `TestbenchConfig.get_name()`/`get_filelist()` return their fields.

## Acceptance criteria

- Tests pass.
- The runtime types (`TestConfig`, `SuiteConfig`, `TestbenchConfig`, `UVMConfig`) and their `get_*` methods behave per the tables above when constructed directly. (The drop-in load of an unmodified `tests.yaml` into these runtime types — via the raw `SuiteConfigFile`/`TestConfigFile` and the inline conversion — is exercised by `parse-suite-config`, spec [04h](04h-parse-suite-config.md), which owns the raw types and the `from_yaml` call.)
- Every downstream consumer spec (`select-tests`, `filter-reglvl`, `load-model`, `expand-sweep`, `run-preproc`, `write-filelist`, `build-compile-cmd`, `build-sim-cmd`, `route-post`, `parse-uvm-log`) references fields/methods by name (e.g. `test.get_preproc_path()`, `test.uvm.max_warns`, `test.get_timeout()`) without forcing the implementer to open `rtl_buddy/src/rtl_buddy/config/{suite,test,uvm}.py`.

## Constraints

- `model` is the runtime `TestConfig` field holding the YAML model-name string (name unchanged from raw `TestConfigFile.model: str` and from rtl_buddy's field). It holds **only** the name string — the resolved `ModelConfig` never lives on the object; it rides the separate `model` keyed edge (`load-model` → `write-filelist`). The field and the edge share the name `model`; what differs from rtl_buddy is that this plan never overwrites the field with the resolved object (divergence 1).
- The model is resolved off-object: `TestConfig` is never in a "model not yet loaded" state, so it carries no nullable resolved-model field. It carries `model` (the name), `model_path`, and `suite_dir` so `load-model` (spec [05e](05e-load-model.md)) can resolve `suite_dir / model_path` later and emit the `ModelConfig` on its own `model` edge (the conversion that stamps these is `parse-suite-config`'s inline raw→runtime conversion, spec 04h — do **not** eagerly load a model anywhere).
- `get_reglvl(builder)` resolution order is fixed: builder-keyed dict entry → `default` dict entry → uniform int → `0`. A malformed dict (no builder key and no `default`) must `log.fatal`.
- `get_timeout()` returns `(self.timeout, True)` on a per-test override else `(self.default_timeout, False)`; `default_timeout` is a `TestConfig` field defaulting to `60` (rtl_buddy `config/test.py:81`).
- `get_plusarg`/`get_plusdefine` raise `AttributeError` when `pa`/`pd` is `None` — preserve this; callers must guard with `get_plusargs() is not None` first.
- `UVMConfig` validation is `ValueError` at construction (see § `UVMConfig` above), not `log.fatal`. Promoting it to `log.fatal` is `parse-suite-config`'s job (spec [04h](04h-parse-suite-config.md)), not this dataclass's.

## Notes

YAML `field(rename=...)` targets are the **public surface** for downstream rtl_buddy users — do **not** Pythonify them. Preserve hyphens and casing exactly as listed.

`SuiteConfig.get_tests()` returns `dict_values` when `test_name` is omitted (rtl_buddy `suite.py:67`). This plan's `select-tests` (spec [idx-05](../idx-05-selection-expansion.md)) iterates and yields per-test — the type doesn't matter for that use, but if other callers index or `len()` the result, materialise to `list` first.

`TestConfig.get_plusarg(key)` raises `AttributeError` if `pa is None`. Callers should guard with `get_plusargs() is not None` first (matches rtl_buddy `vlog_sim.py:97`). The two getter shapes are kept distinct to match rtl_buddy's public surface.

`TestConfig` is a mutable dataclass, so `expand-runs` (spec [08a](08a-expand-runs.md)) can re-key a test per run with `dataclasses.replace(test, key=nk)` — a shallow copy that overrides `key` only and shares `pa`/`pd`/`tb`/`tb.filelist` by reference (cheap, and safe because the sole in-place mutator, `run-preproc` spec [06a](06a-run-preproc.md), runs strictly upstream). `replace` reconstructs via `__init__`; the underscore field `_reglvl` is a normal init field, so it round-trips. `key` is runtime-only — set to `name` at construction and refined by the fan-outs, never read from or written to YAML (the raw `TestConfigFile`, owned by [04h](04h-parse-suite-config.md), has no `key`).
