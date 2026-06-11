# Spec 04h: parse-suite-config (`ParseSuiteConfigMod`)

**Depends on:** spec 01 (schema), spec [01b](01b-suite-schema.md)
(`ParseSuiteConfigMod` produces `SuiteConfig` / `TestConfig` / `TestbenchConfig`).
**References:** [03 — Setup section](../03-module-catalog.md). Parent index:
[04 — Setup modules](04-setup-modules.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)`
signature, the allowed output forms (plain return / named-port tuple / generator), the
`finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py`
are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry
below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit
`a69d962`). This module appends to `modules/rtl_test/setup.py`, shared with the setup chain
(`04a`–`04i`, index [04](04-setup-modules.md)), the selection/expansion chain (`05a`–`05f`,
index [05](05-selection-expansion-modules.md)), and git-status (`10b`); coordinate shared
imports and helpers with those specs.

## Goal

Read the resolved `tests.yaml` path, deserialise it into the suite schema, bind testbenches
within-file, stamp `suite_dir`, and emit `suite_cfg`.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry —
the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract: unit   (test/randtest; default in regression — see 08)
inputs:   test_config:Path
outputs:  default → suite_cfg
```

```python
class ParseSuiteConfigMod:
    def run(self, test_config:Path):
        try:
            suite_cfg = SuiteConfig(test_config)   # from_yaml + testbench bind + suite_dir stamp
        except Exception as e:   # I/O, parse, UVMConfig ValueError, unknown-testbench KeyError
            log.critical("suite_config_load_failed", path=str(test_config), err=str(e))
        return ("default", suite_cfg)
```

## Algorithm

The skeleton folds steps 1–4 into the `SuiteConfig(test_config)` constructor; the constructor
flow is enumerated in spec [01b — `SuiteConfig`](01b-suite-schema.md) and reproduced here.

1. Open and deserialise `test_config` into the raw `SuiteConfigFile` (spec 01b):
   `from_yaml(SuiteConfigFile, test_config.read_text())`.
2. Bind testbenches within-file: build `tbs = {tb.get_name(): tb for tb in raw.testbenches}`
   and resolve each raw `TestConfigFile.tb` (YAML `testbench`) against it.
3. Stamp `suite_dir = test_config.parent` onto each test so `load-model` (spec 05e) can later
   resolve `suite_dir / model_path`.
4. `initialise` each test into its runtime `TestConfig`, assemble `suite_cfg: SuiteConfig`
   (`tests: dict[str, TestConfig]`, `path: Path`), and emit `("default", suite_cfg)`.
5. **Failure — load/parse/validation.** Wrap steps 1–4 in `try/except Exception`: file I/O +
   parse errors (same family as `parse-root-config`) and `UVMConfig.__post_init__`'s
   `ValueError` on negative `max_warns`/`max_errors` → `log.critical`. A `TestConfigFile.tb`
   that does not resolve in `tbs` (`KeyError` from `tbs[t.tb]`) →
   `log.critical(f"test {test.name} references unknown testbench {test.tb}")`.

## Deliverables

In `modules/rtl_test/setup.py`:

- `ParseSuiteConfigMod` — reads `test_config:Path` (the resolved path from
  `CheckSuiteCwdMod` in test/randtest graphs, or from `parse-reg-config` in regression),
  deserialises into `SuiteConfigFile` (spec [01b](01b-suite-schema.md)), binds each
  raw `TestConfigFile.tb` (YAML `testbench`) to the corresponding `TestbenchConfig`
  in-file via the `tbs = {tb.get_name(): tb for tb in raw.testbenches}` dict, stamps
  `suite_dir = test_config.parent` onto each test (so `load-model` in spec
  [05](05-selection-expansion-modules.md) can resolve `suite_dir / test.model_path`),
  and emits `suite_cfg: SuiteConfig` (`tests: dict[str, TestConfig]`, `path: Path`).
  **Module is contract-agnostic** — pairs with `unit` in test/randtest graphs,
  `default` in regression (see [08](../08-sibling-graphs.md)). The constructor flow
  (open → `from_yaml` → bind testbenches → `initialise` each test) is enumerated in
  spec [01b — `SuiteConfig`](01b-suite-schema.md).
  **Failure handling**: catch broad `Exception` from the YAML load and from
  `UVMConfig.__post_init__`'s `ValueError` on negative `max_warns`/`max_errors` (same
  exception family as `ParseRootConfigMod`) → `log.critical`. After deserialisation, a
  post-check: each `TestConfigFile.tb` must resolve to a defined `TestbenchConfig` —
  unresolved (`KeyError` from `tbs[t.tb]`) → `log.critical(f"test {test.name}
  references unknown testbench {test.tb}")`. Mirrors `rtl_buddy/src/rtl_buddy/config/suite.py:28-50`.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/config/suite.py:26-50` — `SuiteConfig.__init__` (parse + testbench bind); per-test `TestConfigFile.initialise` at `config/test.py:320-323`.

**Manifest** — append to the `- file: rtl_test/setup.py` block in `modules/config.yaml`
(opened by [`04a`](04a-discover-config-file.md); append, don't re-create):

```yaml
  - { name: parse-suite-config, class_name: ParseSuiteConfigMod }
```

## Tests

In `modules/tests/test_setup.py`. Fixtures: a committed rtl_buddy `tests.yaml` fixture for
the happy path; `tmp_path` crafted YAML for the failure cases; `logging_handler` for the
`log.critical` paths.

- A real `tests.yaml` `Path` → emits `("default", suite_cfg)` with `tests:
  dict[str, TestConfig]`, each `test.tb` bound to its `TestbenchConfig` instance, and
  `suite_dir == test_config.parent` stamped on every test.
- Path to a nonexistent file → `FileNotFoundError` caught → `log.critical` →
  `pytest.raises(SystemExit)`.
- Path to malformed-YAML → parse error caught → `log.critical` → `pytest.raises(SystemExit)`.
- A test references a `testbench` name not in the file's `testbenches` → `KeyError` from
  `tbs[t.tb]` → `log.critical("… references unknown testbench …")` → `pytest.raises(SystemExit)`.
- A test's `uvm` block has negative `max_warns` (or `max_errors`) → `UVMConfig.__post_init__`
  `ValueError` caught → `log.critical` → `pytest.raises(SystemExit)` (boundary: validation).

## Acceptance criteria

- Tests pass.
- Produces a correct `suite_cfg` value (with bound testbenches and stamped `suite_dir`)
  from a real rtl_buddy `tests.yaml` fixture (contributes to the setup-only end-to-end
  graph — see [04 index](04-setup-modules.md#acceptance-criteria)).

## Constraints

- Contract-agnostic module: pairs with `unit` in test/randtest, `default` in regression. Emit
  on the string-literal `default` port.
- Stamp `suite_dir = test_config.parent` onto **every** test so `load-model` (spec
  [05e](05e-load-model.md)) can resolve `suite_dir / model_path` later.
- Bind testbenches within-file via `tbs = {tb.get_name(): tb for tb in raw.testbenches}`; an
  unresolved `t.tb` (`KeyError`) → `log.critical`.
- Catch broad `Exception` (file I/O, parse, `UVMConfig.__post_init__`'s `ValueError`,
  unknown-testbench `KeyError`) → `log.critical` (harness exit 1). All setup-domain config
  errors; never a port-routed result.
