# Spec 05c: select-tests (`SelectTestsMod`)

**Depends on:** spec 01 (schema), spec [01b](01b-suite-schema.md)
(`SuiteConfig` / `TestConfig`).
**References:** [03 — Selection/expansion section](../03-module-catalog.md). Parent index:
[05 — Selection and expansion modules](05-selection-expansion-modules.md).

## Goal

Enter the per-test stream: yield one `ctx` per selected `TestConfig`.

## Deliverables

In `modules/rtl_test/setup.py` (continuing from spec 04):

- `SelectTestsMod` — `(suite_cfg: SuiteConfig, test_name:str="")` → calls
  `suite_cfg.get_tests(test_name or None)` (spec [01b](01b-suite-schema.md) — returns
  one-element list or all-tests view) and yields one
  `{"key": test.get_name(), "test": test}` per `TestConfig` returned. No mode logic;
  `--list` is handled upstream.
  **Failure handling**: `SuiteConfig.get_tests(test_name)` itself calls
  `log.critical(f"test_name {test_name} not found in suite {self.path}")` when
  `test_name` is supplied and missing (spec [01b — `SuiteConfig`](01b-suite-schema.md)
  — mirrors `rtl_buddy/src/rtl_buddy/config/suite.py:62-63` and `rtl_buddy.py:36`).
  No additional `try/except` needed at the module layer.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/config/suite.py:52-67` — `SuiteConfig.get_tests`.

Manifest entries per [06](../06-graph-yaml.md).

## Tests

In `modules/tests/test_selection.py`:

- `select` yields all tests in declaration order.
- `test_name="foo"` yields only `foo`.
- Unknown name critical-logs.

## Acceptance criteria

- Tests pass.
- Streamed end-to-end: a fixture `tests.yaml` with three tests fans out to three `ctx`s
  with correctly-stamped keys.
