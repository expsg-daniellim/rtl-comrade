# Spec 01b: Suite / Test / UVM schema

**Depends on:** spec [01c](01c-model-schema.md) (`TestConfig.model: ModelConfig | None`
references the model type). Can run mostly in parallel — only the type annotation needs
01c's name.
**References:** [01-shared-schema](01-shared-schema.md) (umbrella), [07 settled 1, 8](../07-ambiguities-and-assumptions.md), TODO #10 (resolution).
**Source:**
- `rtl_buddy/src/rtl_buddy/config/suite.py:1-88` (`SuiteConfigFile`, `SuiteConfig`).
- `rtl_buddy/src/rtl_buddy/config/test.py:1-323` (`TestbenchConfig`, `TestConfig`, `TestConfigFile`).
- `rtl_buddy/src/rtl_buddy/config/uvm.py:1-19` (`UVMConfig`).

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

Reimplement the `tests.yaml` schema natively so consumers (`select-tests`,
`filter-reglvl`, `load-model`, `expand-sweep`, `run-preproc`, `write-filelist`,
`build-compile-cmd`, `build-sim-cmd`, `route-post`, `parse-uvm-log`) can use the
schema by field/method without opening `rtl_buddy`. Preserves the YAML field-name
surface so existing `tests.yaml` files load drop-in (see [07 settled
1](../07-ambiguities-and-assumptions.md)).

## Deliverables

A single file, e.g. `modules/rtl_test/schema/suite.py` (with `uvm.py` and `testbench`
either inlined or split for taste; tests treat them as one surface).

### `UVMConfig`

Per-test UVM report parsing configuration. Lives on `TestConfig.uvm`; if `None`, the
plain `parse-log` path is taken (else `parse-uvm-log`).

| field         | type | YAML rename | default | notes                                                              |
|---------------|------|-------------|---------|--------------------------------------------------------------------|
| `max_warns`   | `int`| (none)      | `0`     | Maximum `UVM_WARNING` count before the test fails.                 |
| `max_errors`  | `int`| (none)      | `0`     | Maximum `UVM_ERROR` count before the test fails. (Fatal must be 0.)|

Validation: `__post_init__` raises `ValueError` if either field is negative. Note this
is `ValueError`, not `log.critical` — UVMConfig is constructed during YAML deserialisation,
where rtl_buddy's serde wraps the `ValueError` into its own error path. In Plan B, the
broad-`Exception` catch in `parse-suite-config` (spec [04](04-setup-modules.md))
converts the validation failure into `log.critical`.

Source: `rtl_buddy/src/rtl_buddy/config/uvm.py:1-19`.

### `TestbenchConfig`

One per entry in `tests.yaml`'s top-level `testbenches:` list. Bound by name into each
test's `tb` field during `SuiteConfig` initialisation.

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

### `TestConfigFile` (raw)

The serde-decorated type read straight from `tests.yaml`'s `tests:` list. Fields use
`field(rename=...)` to bridge YAML names to Pythonic attribute names. Converted into a
runtime `TestConfig` via `initialise(suite_dir)` (Plan B drops rtl_buddy's eager
`ModelConfigLoader.get_model(...)` call — see Notable divergence below).

| field           | type                 | YAML rename | default  | notes                                                                                                          |
|-----------------|----------------------|-------------|----------|----------------------------------------------------------------------------------------------------------------|
| `name`          | `str`                | (none)      | required | Unique test identifier within the suite.                                                                       |
| `desc`          | `str`                | (none)      | required | Human-readable description.                                                                                    |
| `model`         | `str`                | (none)      | required | Model name to look up in `models.yaml`. Carried into runtime `TestConfig.model_name`.                          |
| `model_path`    | `str`                | (none)      | required | Path to `models.yaml` (relative to suite dir). Resolved by `load-model` (spec [05](05-selection-expansion-modules.md)). |
| `_reglvl`       | `int \| dict \| None`| `reglvl`    | (none)   | Regression level — uniform int, builder-keyed dict (with optional `default`), or omitted (→ `0`).              |
| `pa`            | `dict \| None`       | `plusargs`  | `None`   | Plusargs dict (`{key: value}`); value may be `None` for bare-flag plusargs.                                    |
| `pd`            | `dict \| None`       | `plusdefines`| `None`  | Plusdefines dict; same `None`-value semantics.                                                                 |
| `uvm`           | `UVMConfig \| None`  | (none)      | `None`   | UVM config (see above); presence triggers `parse-uvm-log` post path.                                           |
| `preproc_path`  | `str \| None`        | `preproc`   | `None`   | Path to preproc script. Deserialiser: `lambda data: data.get('path') if data is not None else None`.           |
| `postproc_path` | `str \| None`        | `postproc`  | `None`   | Path to postproc script. Same deserialiser. **Not executed by Plan B** ([07 settled 14](../07-ambiguities-and-assumptions.md)). |
| `sweep_path`    | `str \| None`        | `sweep`     | `None`   | Path to sweep script. Same deserialiser.                                                                       |
| `tb`            | `str`                | `testbench` | required | Testbench name; resolved to `TestbenchConfig` in `initialise()`.                                               |
| `timeout`       | `int \| None`        | `sim_timeout`| `None`  | Per-test override of the default sim timeout (seconds).                                                        |

`preproc_path`/`postproc_path`/`sweep_path` use a custom serde deserialiser that
extracts `.path` from a YAML mapping (the YAML shape is `preproc: { path: foo.py }`,
not `preproc: foo.py`). A YAML omission leaves the field `None`.

`initialise(suite_dir, tbs) -> TestConfig`:

1. `tb = tbs[self.tb]` — raise `KeyError` if testbench unknown (caught by
   `SuiteConfig.__init__` → `log.critical`).
2. Construct a `TestConfig` with all fields plus `suite_dir=suite_dir`,
   `model_name=self.model`, `model_path=self.model_path`, `model=None` (lazy —
   `load-model` fills it in later).

Source: `rtl_buddy/src/rtl_buddy/config/test.py:304-323`.

### `TestConfig` (runtime)

The mutable per-test object that flows through `ctx["test"]` for the whole graph.
Differs from rtl_buddy's `TestConfig` in three ways (see Notable divergences below).

| field            | type                | default                 | notes                                                                                                |
|------------------|---------------------|-------------------------|------------------------------------------------------------------------------------------------------|
| `name`           | `str`               | required                | From raw.                                                                                            |
| `desc`           | `str`               | required                | From raw.                                                                                            |
| `model_name`     | `str`               | required                | From raw (`model: str`). Renamed to avoid clash with the loaded `model` field below.                 |
| `model_path`     | `str`               | required                | From raw. Path to `models.yaml`, relative to `suite_dir`.                                            |
| `suite_dir`      | `Path`              | required                | Stamped by `parse-suite-config` (spec [04](04-setup-modules.md)). Resolves `model_path` for `load-model`. |
| `model`          | `ModelConfig \| None`| `None`                 | Filled in by `load-model` (spec [05](05-selection-expansion-modules.md)). `None` until then.         |
| `_reglvl`        | `int \| dict \| None`| from raw               | Underlying storage; access via `get_reglvl(builder)`.                                                |
| `pa`             | `dict \| None`      | from raw                | Mutable. `set_plusarg`/`set_plusargs` lazily initialise.                                             |
| `pd`             | `dict \| None`      | from raw                | Mutable. `set_plusdefine`/`set_plusdefines` lazily initialise.                                       |
| `uvm`            | `UVMConfig \| None` | from raw                |                                                                                                      |
| `preproc_path`   | `str \| None`       | from raw                |                                                                                                      |
| `postproc_path`  | `str \| None`       | from raw                |                                                                                                      |
| `sweep_path`     | `str \| None`       | from raw                |                                                                                                      |
| `tb`             | `TestbenchConfig`   | required                | Bound from `tbs[raw.tb]` during `initialise()`.                                                      |
| `timeout`        | `int \| None`       | from raw                | Per-test override.                                                                                   |
| `default_timeout`| `int`               | `60`                    | Used by `get_timeout()` when `timeout is None`. Module-level constant; matches rtl_buddy.            |

Methods:

| signature                                | returns                                              | notes / log idiom                                                                                                                                         |
|------------------------------------------|------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------|
| `get_name() -> str`                      | `self.name`                                          | trivial getter.                                                                                                                                           |
| `get_model() -> ModelConfig \| None`     | `self.model`                                         | Returns `None` until `load-model` has run; callers in compile/sim paths can rely on it being set (filter happens upstream of those).                      |
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
| `get_postproc_path() -> str \| None`     | `self.postproc_path`                                 | trivial getter. Plan B preserves the field but does not execute postproc ([07 settled 14](../07-ambiguities-and-assumptions.md)).                         |
| `get_reglvl(builder: str) -> int`        | resolved level for the given builder name            | Resolution order: builder-keyed dict entry → `default` dict entry → uniform int → `0` (when `None`). Malformed (`dict` with no builder or default) → `log.critical`. Mirrors `rtl_buddy/src/rtl_buddy/config/test.py:286-299`. |

Source: `rtl_buddy/src/rtl_buddy/config/test.py:43-302`.

### `SuiteConfigFile` (raw)

The serde-decorated type read straight from `tests.yaml`.

| field         | type                       | YAML rename          | default  | notes                                                                                  |
|---------------|----------------------------|----------------------|----------|----------------------------------------------------------------------------------------|
| `filetype`    | `Literal['test_config']`   | `rtl-buddy-filetype` | required | Discriminator; serde raises on mismatch (caught by `parse-suite-config`'s broad catch).|
| `testbenches` | `list[TestbenchConfig]`    | (none)               | required |                                                                                        |
| `tests`       | `list[TestConfigFile]`     | (none)               | required |                                                                                        |

Source: `rtl_buddy/src/rtl_buddy/config/suite.py:11-15`.

### `SuiteConfig` (runtime)

Constructed by `parse-suite-config` (spec [04](04-setup-modules.md)) from a resolved
`Path`. Holds the test dict keyed by name.

| field   | type                       | notes                                                                                            |
|---------|----------------------------|--------------------------------------------------------------------------------------------------|
| `path`  | `Path`                     | Resolved suite-config path (the one `check-suite-cwd` passed in).                                |
| `tests` | `dict[str, TestConfig]`    | Built as `{test.name: test.initialise(suite_dir, tbs) for test in raw.tests}` where `suite_dir = path.parent`. |

Constructor behaviour (`__init__(path)` in rtl_buddy, `parse-suite-config.run(path)` in Plan B):

1. Open + `from_yaml(SuiteConfigFile, ...)`. Any exception → `log.critical(f'failed to load {path}: {e}')`. Mirrors `suite.py:28-32`.
2. Build `tbs = {tb.get_name(): tb for tb in raw.testbenches}`. Any exception → `log.critical(f'{path}: Testbench section malformed: {e}')`. Mirrors `suite.py:39-42`.
3. Build `self.tests = {t.name: t.initialise(config_dir, tbs) for t in raw.tests}`. `KeyError` (unknown testbench in `t.tb`) → `log.critical(f'{path}: Requested testbench missing')`. Any other exception → `log.critical(f'{path}: Tests section malformed: {e}')`. Mirrors `suite.py:44-50`.

Methods:

| signature                              | returns                                                            | log idiom                                                                                                                       |
|----------------------------------------|--------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------|
| `get_tests(test_name: str \| None = None) -> list[TestConfig] \| dict_values[TestConfig]` | one-element list if `test_name` given and present; all tests otherwise | `log.critical(f"test_name {name} not found in suite {self.path}")` when `test_name` given but not in `self.tests`. Mirrors `suite.py:52-67`. Plan B's `select-tests` uses this same idiom (catalog row at line 112 of [03](../03-module-catalog.md)). |
| `get_test_names() -> list[str]`        | `list(self.tests.keys())`                                          | none.                                                                                                                           |
| `get_path() -> Path`                   | `self.path`                                                        | none.                                                                                                                           |

Source: `rtl_buddy/src/rtl_buddy/config/suite.py:17-86`.

## Notable divergences from rtl_buddy

1. **Lazy model loading** ([07 settled 8](../07-ambiguities-and-assumptions.md)). rtl_buddy
   `TestConfigFile.initialise` eagerly calls
   `ModelConfigLoader(model_path).get_model(self.model)` (`test.py:322`). Plan B defers
   this to `load-model` (spec [05](05-selection-expansion-modules.md)), so
   `TestConfig.model` is `None` until that node fires. Consequence: the runtime
   `TestConfig` carries `model_name: str`, `model_path: str`, and `suite_dir: Path` so
   `load-model` can later resolve `suite_dir / model_path` and call
   `ModelConfigLoader(...).get_model(model_name)`.
2. **Field rename `model` → `model_name`** on runtime `TestConfig` (raw stays `model`
   for YAML compat). Avoids the rtl_buddy name collision where `TestConfigFile.model:
   str` becomes `TestConfig.model: ModelConfig` after `initialise`.
3. **`suite_dir` stamped on each test.** Recorded by `parse-suite-config` (spec
   [04](04-setup-modules.md) — see the existing "binding testbenches within-file,
   recording the suite directory" prose). Replaces rtl_buddy's `config_dir` argument
   to `initialise`, propagating the resolution context downstream rather than
   computing it at parse time.

## Tests (`modules/tests/test_suite_schema.py`)

- **Round-trip.** Load an unmodified rtl_buddy `tests.yaml` (e.g. from
  `rtl-buddy-proj-template/design/sandbox/verif/tests.yaml`); every test's name, desc,
  testbench, plusargs, plusdefines, reglvl, uvm, preproc/postproc/sweep paths, and
  timeout round-trip equal to rtl_buddy's `SuiteConfig(path).tests[name]`.
- **YAML renames.** Each rename in the `TestConfigFile` table above produces a runtime
  field with the documented Pythonic name (a hand-written YAML hitting each rename
  produces the expected attribute).
- **`preproc`/`postproc`/`sweep` path deserialiser.** YAML `preproc: { path: foo.py }`
  → `preproc_path == "foo.py"`; omitting `preproc:` → `preproc_path is None`; YAML
  `preproc: null` → `preproc_path is None`.
- **`get_reglvl` resolution order.** Four cases: int `_reglvl` → that int regardless of
  builder; dict with builder key → that entry; dict with `default` only → default;
  `None` → `0`; dict missing both builder and `default` → `log.critical` (caplog +
  bubbling-`SystemExit`).
- **`get_timeout`.** `timeout=None` → `(60, False)`; `timeout=300` → `(300, True)`.
- **Plusarg/plusdefine mutation.** `set_plusarg("FOO", 1)` on a test with `pa is None`
  produces `pa == {"FOO": 1}`; `set_plusargs({"A": 1, "B": 2})` merges; `get_plusarg`
  reads back.
- **`UVMConfig` defaults and validation.** YAML `uvm: {}` → `max_warns == 0 == max_errors`;
  `max_warns: 5, max_errors: 2` round-trips; `max_warns: -1` → `ValueError` at
  construction (which `parse-suite-config`'s broad-exception catch converts to
  `log.critical`).
- **Testbench binding.** A `tests.yaml` with a test referencing a known testbench
  produces `test.tb` as that `TestbenchConfig` instance; referencing an unknown
  testbench → `parse-suite-config` calls `log.critical`.
- **Lazy model.** A freshly-`initialise`d `TestConfig` has `model is None`,
  `model_name` and `model_path` populated, `suite_dir` set to the parent of the
  loaded YAML path.

## Acceptance criteria

- Tests pass.
- Loading an unmodified rtl_buddy `tests.yaml` (e.g. from
  `rtl-buddy-proj-template/design/sandbox/verif`) produces `TestConfig` instances
  whose `get_*` methods return values equal to rtl_buddy's on the same input
  (modulo `get_model()` returning `None` instead of a `ModelConfig` — Plan B is
  lazy).
- Every downstream consumer spec (`select-tests`, `filter-reglvl`, `load-model`,
  `expand-sweep`, `run-preproc`, `write-filelist`, `build-compile-cmd`,
  `build-sim-cmd`, `route-post`, `parse-uvm-log`) references fields/methods by
  name (e.g. `ctx["test"].get_preproc_path()`, `ctx["test"].uvm.max_warns`,
  `ctx["test"].get_timeout()`) without forcing the implementer to open
  `rtl_buddy/src/rtl_buddy/config/{suite,test,uvm}.py`.

## Constraints

- Preserve the YAML renames exactly (`reglvl`, `plusargs`→`pa`, `plusdefines`→`pd`,
  `preproc`/`postproc`/`sweep`→`*_path`, `testbench`→`tb`, `sim_timeout`→`timeout`,
  `rtl-buddy-filetype`). Do **not** Pythonify the on-disk names.
- Rename `model` → `model_name` on the **runtime** `TestConfig` only; the raw `TestConfigFile`
  keeps `model: str` for YAML compatibility.
- Load the model lazily: `TestConfig.model` is `None` until `load-model` (spec
  [05e](05e-load-model.md)) fires — do **not** eagerly construct a `ModelConfigLoader` here
  (the rtl_buddy `initialise`-time `get_model` call is deliberately dropped).
- `get_reglvl(builder)` resolution order is fixed: builder-keyed dict entry → `default` dict
  entry → uniform int → `0`. A malformed dict (no builder key and no `default`) must
  `log.critical`.
- `get_timeout()` returns `(self.timeout, True)` on a per-test override else
  `(self.default_timeout, False)`; `default_timeout` is the module-level constant `60`.
- `get_plusarg`/`get_plusdefine` raise `AttributeError` when `pa`/`pd` is `None` — preserve
  this; callers must guard with `get_plusargs() is not None` first.
- `UVMConfig` validation is `ValueError` at construction (see [01](01-shared-schema.md)
  constraints), not `log.critical`.

## Notes

YAML `field(rename=...)` targets are the **public surface** for downstream rtl_buddy
users — do **not** Pythonify them. Preserve hyphens and casing exactly as listed.

`SuiteConfig.get_tests()` returns `dict_values` when `test_name` is omitted (rtl_buddy
`suite.py:67`). Plan B's `select-tests` (spec [05](05-selection-expansion-modules.md))
iterates and yields per-test — the type doesn't matter for that use, but if other
callers index or `len()` the result, materialise to `list` first.

`TestConfig.get_plusarg(key)` raises `AttributeError` if `pa is None`. Callers should
guard with `get_plusargs() is not None` first (matches rtl_buddy `vlog_sim.py:97`).
The two getter shapes are kept distinct to match rtl_buddy's public surface.
