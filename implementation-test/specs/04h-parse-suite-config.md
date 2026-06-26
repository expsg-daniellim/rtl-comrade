# Spec 04h: parse-suite-config (`ParseSuiteConfigMod`)

**Depends on:** spec 01 (schema), spec [01b](01b-suite-schema.md) (the runtime targets this module produces — `SuiteConfig` / `TestConfig` / `TestbenchConfig` — and `UVMConfig` from [01b](01b-suite-schema.md)/`uvm.py`).
**References:** [03 — Setup section](../03-module-catalog.md). Parent index: [idx-04 — Setup modules](../idx-04-setup.md).

This module **owns the raw `SuiteConfigFile`/`TestConfigFile` serde containers (pure data shapes) and the raw→runtime conversion** (tables below): they are read once by `from_yaml` and immediately converted into the runtime `SuiteConfig`/`TestConfig`, so they never ride a graph edge and live here with their sole consumer rather than in the schema package ([idx-01](../idx-01-schema.md)). The conversion happens inline in `run`, **not** as a method on the raw type (unlike rtl_buddy's `TestConfigFile.initialise`). Spec [01b](01b-suite-schema.md) defines the runtime shape they produce.

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)` signature, the allowed output forms (plain return / named-port tuple / generator), the `finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py` are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit `a69d962`). This module appends to `modules/rtl_buddy/setup.py`, which is created by spec [`04a`](04a-discover-config-file.md) — append, do not overwrite. The file is shared with the setup chain (`04a`–`04i`, index [idx-04](../idx-04-setup.md)), the selection/expansion chain (`05a`–`05f`, index [idx-05](../idx-05-selection-expansion.md)), and git-status (`10b`); coordinate shared imports and helpers with those specs.

## Goal

Resolve the `tests.yaml` locator against CWD, read it, deserialise into the suite schema, bind testbenches within-file, stamp `suite_dir`, and emit `suite_cfg`. (This node owns the path resolution and the missing-file failure — it has to open the file and derive `suite_dir = path.parent` anyway.)

## Raw schema & conversion (owned here)

The raw `@serde` containers read straight from `tests.yaml`, plus the raw→runtime conversion. Defined as module-private dataclasses in `setup.py` — **not** re-exported from the schema package (they never ride an edge). They construct the runtime `TestConfig`/`SuiteConfig`/`TestbenchConfig`/`UVMConfig` owned by spec [01b](01b-suite-schema.md). Faithful port of `rtl_buddy/src/rtl_buddy/config/suite.py:11-15` (`SuiteConfigFile`) and `config/test.py:304-323` (`TestConfigFile` + `initialise`).

### `SuiteConfigFile` (raw)

| field         | type                       | YAML rename          | default  | notes                                                                                  |
|---------------|----------------------------|----------------------|----------|----------------------------------------------------------------------------------------|
| `filetype`    | `Literal['test_config']`   | `rtl-buddy-filetype` | required | Discriminator; serde raises `SerdeError` on mismatch (caught by the `serde_error` clause below). |
| `testbenches` | `list[TestbenchConfig]`    | (none)               | required | `TestbenchConfig` ([01b](01b-suite-schema.md)).                                         |
| `tests`       | `list[TestConfigFile]`     | (none)               | required |                                                                                        |

### `TestConfigFile` (raw)

The serde-decorated type read straight from `tests.yaml`'s `tests:` list — a **pure deserialization shape, no methods**. `field(rename=...)` bridges YAML names to Pythonic attribute names. It is converted into a runtime `TestConfig` inline in `run` (below); this plan drops rtl_buddy's eager `ModelConfigLoader.get_model(...)` call (lazy model loading — see spec [01b — Notable divergences](01b-suite-schema.md#notable-divergences-from-rtl_buddy)).

| field           | type                 | YAML rename | default  | notes                                                                                                          |
|-----------------|----------------------|-------------|----------|----------------------------------------------------------------------------------------------------------------|
| `name`          | `str`                | (none)      | required | Unique test identifier within the suite.                                                                       |
| `desc`          | `str`                | (none)      | required | Human-readable description.                                                                                    |
| `model`         | `str`                | (none)      | required | Model name to look up in `models.yaml`. Carried into runtime `TestConfig.model` (same field name).             |
| `model_path`    | `str`                | (none)      | required | Path to `models.yaml` (relative to suite dir). Resolved by `load-model` (spec [05e](05e-load-model.md)).        |
| `reglvl`        | `int \| dict \| None`| (none)      | (none)   | Regression level — uniform int, builder-keyed dict (with optional `default`), or omitted (→ `0`).              |
| `pa`            | `dict \| None`       | `plusargs`  | `None`   | Plusargs dict (`{key: value}`); value may be `None` for bare-flag plusargs.                                    |
| `pd`            | `dict \| None`       | `plusdefines`| `None`  | Plusdefines dict; same `None`-value semantics.                                                                 |
| `uvm`           | `UVMConfig \| None`  | (none)      | `None`   | UVM config ([01b](01b-suite-schema.md)/`uvm.py`); presence triggers `parse-uvm-log` post path.                 |
| `preproc_path`  | `str \| None`        | `preproc`   | `None`   | Path to preproc script. Deserialiser: `lambda data: data.get('path') if data is not None else None`.           |
| `postproc_path` | `str \| None`        | `postproc`  | `None`   | Path to postproc script. Same deserialiser. **Not executed by this plan** ([07 settled 14](../07-ambiguities-and-assumptions.md)). |
| `sweep_path`    | `str \| None`        | `sweep`     | `None`   | Path to sweep script. Same deserialiser.                                                                       |
| `tb`            | `str`                | `testbench` | required | Testbench name; resolved to `TestbenchConfig` during conversion (inline in `run`).                             |
| `timeout`       | `int \| None`        | `sim_timeout`| `None`  | Per-test override of the default sim timeout (seconds).                                                        |

`preproc_path`/`postproc_path`/`sweep_path` use a custom serde deserialiser that extracts `.path` from a YAML mapping (the YAML shape is `preproc: { path: foo.py }`, not `preproc: foo.py`). A YAML omission leaves the field `None`. Preserve every `field(rename=...)` target exactly (keep hyphens/underscores as listed) — these are the public on-disk surface.

Conversion — done inline in `run`'s test-dict comprehension, per raw test:

1. `tb = tbs[raw.tb]` — raise `KeyError` if testbench unknown (caught per-test in `run` → `log.fatal("unknown_testbench", …)`).
2. Construct a runtime `TestConfig` (spec [01b](01b-suite-schema.md)) with all fields plus `tb`, `suite_dir=suite_dir`, `model=raw.model`, `model_path=raw.model_path`. Do **not** pass `key` — `TestConfig.__post_init__` defaults it to `name` (the base instance identity; the test is born self-keyed, refined `#i`/`#run` downstream by `expand-sweep`/`expand-runs`, spec [01b](01b-suite-schema.md)). The `model` field holds the **name string**; the resolved `ModelConfig` rides its own `model` edge from `load-model` and never lives on the `TestConfig` object (the field is not overwritten).

This is built directly in `run`, **not** as a method on `TestConfigFile` (which stays a pure serde shape) and **not** factored into a single-use helper — rtl_buddy hangs the equivalent `initialise` off the raw type only because it has no node to own the transform; this plan does, so the transform belongs to the node. Mirrors `parse-root-config`, which likewise builds its runtime `RootConfig` inline in `run`.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry — the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract: unit   (test/randtest; default in regression — see 08)
inputs:   test_config:str = "tests.yaml"   (the raw locator: CLI in test/randtest, parse-reg-config's suite path in regression)
outputs:  default → suite_cfg
```

```python
class ParseSuiteConfigMod:
    def run(self, test_config:str = "tests.yaml"):
        path = Path(test_config).resolve()   # resolve against CWD (test: CLI; regression: parse-reg-config); collapses symlinks
        try:
            raw = from_yaml(SuiteConfigFile, path.read_text())   # read_text() I/O + serde + YAML errors + UVMConfig.__post_init__ ValueError
        except UnicodeDecodeError as e:        # config not valid UTF-8
            log.fatal("invalid_unicode", path=str(path), reason=e.reason, exc_info=e)
        except FileNotFoundError as e:         # missing config
            log.fatal("not_found", path=str(path), exc_info=e)
        except IsADirectoryError as e:         # locator points at a directory
            log.fatal("is_directory", path=str(path), exc_info=e)
        except PermissionError as e:           # unreadable
            log.fatal("permission_denied", path=str(path), exc_info=e)
        except OSError as e:                    # remaining I/O (after the OSError subclasses above)
            log.fatal("os_error", path=str(path), err=e.strerror, errno=e.errno, exc_info=e)
        except SerdeError as e:                 # deserialise / schema / discriminator / type mismatch
            log.fatal("serde_error", path=str(path), message=str(e), exc_info=e)
        except MarkedYAMLError as e:            # YAML syntax error with position
            log.fatal("yaml_invalid", path=str(path), problem=e.problem, exc_info=e)
        except ReaderError as e:                # YAML reader / encoding error
            log.fatal("yaml_unreadable", path=str(path), reason=e.reason, exc_info=e)
        except ValueError as e:                 # UVMConfig.__post_init__: negative max_warns/max_errors (after UnicodeDecodeError, its subclass)
            log.fatal("invalid_uvm_config", path=str(path), reason=str(e), exc_info=e)
        tbs = {tb.get_name(): tb for tb in raw.testbenches}
        tests = {}
        for t in raw.tests:
            try:
                tb = tbs[t.tb]                  # bind testbench within-file
            except KeyError as e:               # testbench name not declared in this file's testbenches
                log.fatal("unknown_testbench", path=str(path), test=t.name, testbench=t.tb, exc_info=e)
            tests[t.name] = TestConfig(name=t.name, desc=t.desc, model=t.model, model_path=t.model_path, reglvl=t.reglvl, pa=t.pa, pd=t.pd, uvm=t.uvm, preproc_path=t.preproc_path, postproc_path=t.postproc_path, sweep_path=t.sweep_path, tb=tb, timeout=t.timeout, suite_dir=path.parent)   # key defaults to name via TestConfig.__post_init__ (born self-keyed); stamp suite_dir; no model field — resolved on its own edge by load-model
        suite_cfg = SuiteConfig(path=path, tests=tests)
        return ("default", suite_cfg)
```

The `from_yaml` block mirrors the harness's own per-type config-load ladder (`loader_utils.load_config_file`, `src/rtl_comrade/loader_utils.py:38-61`): one `except` per category with a category-specific event and fields, never a blanket `Exception` (so an unexpected error propagates rather than being demoted to a config-load failure). Ordering matters — `UnicodeDecodeError` precedes `ValueError` (it is a subclass), and `FileNotFoundError`/`IsADirectoryError`/`PermissionError` precede `OSError`. Imports (`SerdeError` from `serde`, `from_yaml` from `serde.yaml`, `MarkedYAMLError` from `yaml.error`, `ReaderError` from `yaml.reader`) are shared with the setup chain — coordinate per [§ Before you start](#before-you-start). Empirically (pyserde 0.31.2): missing-field / wrong-type / `rtl-buddy-filetype` discriminator mismatch all surface as `SerdeError`; YAML syntax errors as `MarkedYAMLError`; the UVM limit `ValueError` propagates **raw** through `from_yaml` (not wrapped), so it needs its own clause.

`SuiteConfig` (spec [01b](01b-suite-schema.md)) is a plain `@dataclass` holder — this module performs the open→bind→convert sequence and constructs it (rtl_buddy folds the same sequence into `SuiteConfig.__init__` and `TestConfigFile.initialise`; this plan keeps the holder and the raw shape pure and owns the conversion in the node, inline in `run`).

## Algorithm

1. Resolve the locator against CWD: `path = Path(test_config).resolve()`. `test_config` is the raw CLI string in test/randtest (default `"tests.yaml"`, resolved relative to CWD) or the suite path emitted by `parse-reg-config` in regression; `.resolve()` collapses symlinks. This node opens the file and derives `suite_dir` from it.
2. Open and deserialise `path` into the raw `SuiteConfigFile` ([§ Raw schema](#raw-schema--conversion-owned-here)): `from_yaml(SuiteConfigFile, path.read_text())`.
3. Bind testbenches within-file: build `tbs = {tb.get_name(): tb for tb in raw.testbenches}` and resolve each raw `TestConfigFile.tb` (YAML `testbench`) against it inline in the test-dict comprehension.
4. Stamp `suite_dir=path.parent` onto each test (inline in the comprehension) so `load-model` (spec [05e](05e-load-model.md)) can later resolve `suite_dir / model_path`.
5. Convert each raw test into its runtime `TestConfig` inline, assemble `suite_cfg = SuiteConfig(path=path, tests={...})`, and emit `("default", suite_cfg)`.
6. **Failure — load/parse/validation.** Wrap the `from_yaml(SuiteConfigFile, path.read_text())` call (step 2) in a per-type `except` ladder — one clause per category, never a blanket `Exception` — each → `log.fatal` with a category-specific event: `UnicodeDecodeError` (`invalid_unicode`); the file-I/O family `FileNotFoundError`/`IsADirectoryError`/`PermissionError`/`OSError` (the **missing config** is `FileNotFoundError` from `read_text()`); the parse family `SerdeError` (deserialise/schema/discriminator), `MarkedYAMLError`/`ReaderError` (YAML syntax); and `ValueError` from `UVMConfig.__post_init__` on negative `max_warns`/`max_errors` (raw, after the `UnicodeDecodeError` clause — its subclass). Order the OSError subclasses before `OSError`. The testbench bind (step 3) is separate: a `TestConfigFile.tb` that does not resolve in `tbs` (`KeyError` from `tbs[t.tb]`, caught per-test so `t` is in scope) → `log.fatal("unknown_testbench", test=t.name, testbench=t.tb)`.

## Deliverables

In `modules/rtl_buddy/setup.py`:

- The module-private raw `SuiteConfigFile`/`TestConfigFile` serde containers (pure data shapes, no methods) — defined in `setup.py`, not exported from the schema package — and the raw→runtime conversion ([§ Raw schema & conversion](#raw-schema--conversion-owned-here) above), performed inline in `run`.
- `ParseSuiteConfigMod` — takes the raw `test_config:str = "tests.yaml"` locator (the CLI string in test/randtest, or the suite path from `parse-reg-config` in regression), **resolves it against CWD** (`path = Path(test_config).resolve()`), deserialises into `SuiteConfigFile`, binds each raw `TestConfigFile.tb` (YAML `testbench`) to the corresponding `TestbenchConfig` in-file via the `tbs = {tb.get_name(): tb for tb in raw.testbenches}` dict, stamps `suite_dir=path.parent` onto each test (so `load-model` in spec [05e](05e-load-model.md) can resolve `suite_dir / test.model_path`), and constructs `suite_cfg = SuiteConfig(path=path, tests={...})` (`SuiteConfig` is the plain holder from [01b](01b-suite-schema.md)). This module owns the path resolution and missing-file failure: it opens the file and derives `suite_dir` from it. **Module is contract-agnostic** — pairs with `unit` in test/randtest graphs, `default` in regression (see [08](../08-sibling-graphs.md)). The resolve → `from_yaml` → bind testbenches → convert each test sequence is enumerated in [§ Algorithm](#algorithm).
  **Failure handling**: catch the YAML load failures **per type, not as a blanket `Exception`** — one `except` clause per category, each → `log.fatal` with a category-specific event, mirroring the harness's own `loader_utils.load_config_file` ladder (`src/rtl_comrade/loader_utils.py:38-61`). File I/O: `UnicodeDecodeError`, `FileNotFoundError` (the **missing config** — `-c` pointing at a nonexistent file), `IsADirectoryError`, `PermissionError`, then `OSError` (subclasses first). Parse: `SerdeError` (deserialise/schema/discriminator), `MarkedYAMLError`, `ReaderError`. Validation: `ValueError` from `UVMConfig.__post_init__` on negative `max_warns`/`max_errors` — placed **after** `UnicodeDecodeError` (its subclass) and surfacing **raw** through `from_yaml` (pyserde does not wrap it). After deserialisation, the testbench bind: each `TestConfigFile.tb` must resolve to a defined `TestbenchConfig` — unresolved `KeyError` from `tbs[t.tb]`, caught **per-test** (inside the build loop, so `t.name`/`t.tb` are in scope) → `log.fatal("unknown_testbench", test=t.name, testbench=t.tb)`. Mirrors `rtl_buddy/src/rtl_buddy/config/suite.py:28-50`.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/config/suite.py:26-50` — `SuiteConfig.__init__` (parse + testbench bind); per-test `TestConfigFile.initialise` at `config/test.py:320-323`.

**Manifest** — append to the `- file: rtl_buddy/setup.py` block in `modules/config.yaml` (opened by [`04a`](04a-discover-config-file.md); append, don't re-create):

```yaml
  - { name: parse-suite-config, class_name: ParseSuiteConfigMod }
```

## Tests

In `modules/tests/test_setup.py`. Fixtures: a committed rtl_buddy `tests.yaml` fixture for the happy path; `tmp_path` + `monkeypatch.chdir` crafted YAML for the failure/resolution cases; `logging_handler` for the `log.fatal` paths.

- A `test_config` string naming a real `tests.yaml` → emits `("default", suite_cfg)` with `tests: dict[str, TestConfig]`, each `test.tb` bound to its `TestbenchConfig` instance, `test.key == test.name` (born self-keyed), and `suite_dir == Path(test_config).resolve().parent` stamped on every test.
- **Relative locator resolves against CWD.** `test_config="tests.yaml"` with the file in CWD, and `test_config="sub/tests.yaml"` with the file in `<cwd>/sub/` → both load, and `suite_cfg.path` / `suite_dir` are the resolved absolute path / its parent (boundary: relative `-c sub/tests.yaml` is accepted, not rejected).
- **Round-trip (raw schema).** Loading an unmodified rtl_buddy `tests.yaml` (e.g. `rtl-buddy-proj-template/design/sandbox/verif/tests.yaml`) yields runtime `TestConfig`s whose name, desc, testbench, plusargs, plusdefines, reglvl, uvm, preproc/postproc/sweep paths, and timeout equal rtl_buddy's `SuiteConfig(path).tests[name]` (modulo `get_model()` being `None` — lazy).
- **YAML renames.** Each `field(rename=...)` in the `TestConfigFile` table produces the documented runtime attribute (a hand-written YAML hitting each rename loads into the expected `TestConfig` field).
- **`preproc`/`postproc`/`sweep` path deserialiser.** YAML `preproc: { path: foo.py }` → `preproc_path == "foo.py"`; omitting `preproc:` → `preproc_path is None`; YAML `preproc: null` → `preproc_path is None`.
- **Lazy model.** A freshly-parsed `TestConfig` has `model` holding the model **name** string (not a resolved `ModelConfig`), `model_path` populated, and `suite_dir == Path(test_config).resolve().parent`.
Failure cases — each exercises a distinct `except` clause; assert the **specific** `log.fatal` event (not just that some fatal fired) and `pytest.raises(typer.Exit)` under `logging_handler`:

- `test_config` naming a nonexistent file (missing config) → `FileNotFoundError` from `read_text()` → `log.fatal("not_found")`.
- `test_config` naming a directory → `IsADirectoryError` → `log.fatal("is_directory")` (boundary: I/O-class).
- `test_config` naming a non-UTF-8 file → `UnicodeDecodeError` → `log.fatal("invalid_unicode")` (boundary: precedes the `ValueError` clause despite being a subclass).
- `test_config` naming a malformed-YAML file (bad indentation / unbalanced bracket) → `MarkedYAMLError` → `log.fatal("yaml_invalid")`.
- `test_config` whose YAML is well-formed but schema-invalid (missing required field, wrong type, or a bad `rtl-buddy-filetype` discriminator) → `SerdeError` → `log.fatal("serde_error")`.
- A test's `uvm` block has negative `max_warns` (or `max_errors`) → `UVMConfig.__post_init__` `ValueError` (raw through `from_yaml`) → `log.fatal("invalid_uvm_config")` (boundary: validation; confirms it is **not** swallowed by the parse clauses).
- A test references a `testbench` name not in the file's `testbenches` → per-test `KeyError` from `tbs[t.tb]` → `log.fatal("unknown_testbench", test=…, testbench=…)` (assert the offending `test`/`testbench` are in the event).

## Acceptance criteria

- Tests pass.
- Output port `default` exercised: produces a correct `suite_cfg` value (with bound testbenches and stamped `suite_dir`) from a real rtl_buddy `tests.yaml` fixture (the reference suite `../rtl-buddy-proj-template/design/sandbox/verif`, per `rtl_buddy/AGENTS.md`)
 .
- Failure idioms exercised **per exception type**, each with its category-specific `log.fatal` event: file I/O (`not_found`/`is_directory`/`permission_denied`/`os_error`/`invalid_unicode`), parse (`serde_error`/`yaml_invalid`/`yaml_unreadable`), validation (`invalid_uvm_config` on negative `max_warns`/`max_errors`), and unknown testbench (`unknown_testbench`) → `log.fatal` (harness exit 1). No blanket `Exception` catch.
- The `modules/config.yaml` manifest entry `{ name: parse-suite-config, class_name: ParseSuiteConfigMod }` validates and the harness resolves `parse-suite-config` → `ParseSuiteConfigMod`.

## Constraints

- Contract-agnostic module: pairs with `unit` in test/randtest, `default` in regression. Emit on the string-literal `default` port.
- The raw `SuiteConfigFile`/`TestConfigFile` types are module-private (`setup.py`), pure serde shapes with **no methods**, and **not** added to the schema package's `__init__.py`. Preserve every `field(rename=...)` target exactly (`plusargs`, `plusdefines`, `preproc`/`postproc`/`sweep`, `testbench`, `sim_timeout`, `rtl-buddy-filetype`); do **not** Pythonify the on-disk names.
- The raw→runtime conversion is done inline in `run`'s test-dict comprehension — **not** as a method on `TestConfigFile` (rtl_buddy's `initialise` is deliberately not ported as a method; the transform belongs to the node) and **not** factored into a single-use helper. It builds the runtime `TestConfig` with `model=raw.model`, `model_path=raw.model_path` (the `model` field holds the name string; the resolved `ModelConfig` rides its own edge and never overwrites the field) — do **not** eagerly read `models.yaml` here (`load-model`, spec [05e](05e-load-model.md), does the deferred read + lookup).
- Resolve the locator against CWD up front (`path = Path(test_config).resolve()`); the input is the raw `test_config:str` (CLI default `"tests.yaml"` in test/randtest, `parse-reg-config`'s suite path in regression). A missing file surfaces here as a caught `FileNotFoundError` → `log.fatal`.
- Stamp `suite_dir=path.parent` onto **every** test so `load-model` (spec [05e](05e-load-model.md)) can resolve `suite_dir / model_path` later.
- Bind testbenches within-file via `tbs = {tb.get_name(): tb for tb in raw.testbenches}`; an unresolved `t.tb` (`KeyError`) → `log.fatal`.
- Catch the load/parse/validation failures **per exception type** — one `except` clause each, never a blanket `Exception` (so an unexpected error propagates rather than being demoted to a config-load failure) — mirroring `loader_utils.load_config_file`: `UnicodeDecodeError`, `FileNotFoundError`, `IsADirectoryError`, `PermissionError`, `OSError` (subclasses first), `SerdeError`, `MarkedYAMLError`, `ReaderError`, then `ValueError` (UVM limits; after `UnicodeDecodeError`). The unknown-testbench `KeyError` is caught per-test in the build loop. Each → `log.fatal` with a category-specific event (harness exit 1). All setup-domain config errors; never a port-routed result.
