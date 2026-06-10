# Spec 04h: parse-suite-config (`ParseSuiteConfigMod`)

**Depends on:** spec 01 (schema), spec [01b](01b-suite-schema.md)
(`ParseSuiteConfigMod` produces `SuiteConfig` / `TestConfig` / `TestbenchConfig`).
**References:** [03 — Setup section](../03-module-catalog.md). Parent index:
[04 — Setup modules](04-setup-modules.md).

## Goal

Read the resolved `tests.yaml` path, deserialise it into the suite schema, bind testbenches
within-file, stamp `suite_dir`, and emit `suite_cfg`.

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

Manifest entries in `modules/config.yaml` per [06 — Manifest additions](../06-graph-yaml.md).

## Tests

In `modules/tests/test_setup.py`:

- Suite parse handles a real rtl_buddy `tests.yaml` (input now a `Path`, not a `str`).

## Acceptance criteria

- Tests pass.
- Produces a correct `suite_cfg` value (with bound testbenches and stamped `suite_dir`)
  from a real rtl_buddy `tests.yaml` fixture (contributes to the setup-only end-to-end
  graph — see [04 index](04-setup-modules.md#acceptance-criteria)).
