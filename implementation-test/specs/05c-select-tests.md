# Spec 05c: select-tests (`SelectTestsMod`)

**Depends on:** spec 01 (schema), spec [01b](01b-suite-schema.md)
(`SuiteConfig` / `TestConfig`).
**References:** [03 — Selection/expansion section](../03-module-catalog.md). Parent index:
[05 — Selection and expansion modules](05-selection-expansion-modules.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)`
signature, the allowed output forms (plain return / named-port tuple / generator), the
`finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py`
are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry
below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit
`a69d962`). This module appends to `modules/rtl_buddy/setup.py`, which is created by spec
[`04a`](04a-discover-config-file.md) — append, do not overwrite. The file is shared with the
setup chain (`04a`–`04i`, index [04](04-setup-modules.md)), the selection/expansion chain
(`05a`–`05f`, index [05](05-selection-expansion-modules.md)), and git-status (`10b`);
coordinate shared imports and helpers with those specs.

## Goal

Enter the per-test stream: yield one `ctx` per selected `TestConfig`.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry —
the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract: unit
inputs:   suite_cfg, test_name:str = ""
outputs:  default → ctx   (one per selected test)
```

```python
class SelectTestsMod:
    def run(self, suite_cfg, test_name:str = ""):
        for t in suite_cfg.get_tests(test_name or None):
            yield ("default", { "key": t.get_name(), "test": t, "run_id": None })
```

## Algorithm

1. Resolve the selection: `suite_cfg.get_tests(test_name or None)` (spec 01b — a one-element
   list when `test_name` is given, the all-tests view when empty).
2. For each `TestConfig` returned, yield `("default", {"key": test.get_name(), "test": test,
   "run_id": None})` — one `ctx` per selected test. `--list` is handled upstream, so there is
   no mode logic here.
3. **Failure — unknown test name.** No `try/except` at this layer: when `test_name` is supplied
   but absent, `SuiteConfig.get_tests` itself calls `log.critical(f"test_name {test_name} not
   found in suite {self.path}")` (spec 01b).

## Deliverables

In `modules/rtl_buddy/setup.py` (continuing from spec 04):

- `SelectTestsMod` — `(suite_cfg: SuiteConfig, test_name:str="")` → calls
  `suite_cfg.get_tests(test_name or None)` (spec [01b](01b-suite-schema.md) — returns
  one-element list or all-tests view) and yields one
  `{"key": test.get_name(), "test": test, "run_id": None}` per `TestConfig` returned. No mode logic;
  `--list` is handled upstream.
  **Failure handling**: `SuiteConfig.get_tests(test_name)` itself calls
  `log.critical(f"test_name {test_name} not found in suite {self.path}")` when
  `test_name` is supplied and missing (spec [01b — `SuiteConfig`](01b-suite-schema.md)
  — mirrors `rtl_buddy/src/rtl_buddy/config/suite.py:62-63` and `rtl_buddy.py:36`).
  No additional `try/except` needed at the module layer.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/config/suite.py:52-67` — `SuiteConfig.get_tests`.

**Manifest** — append to the `- file: rtl_buddy/setup.py` block in `modules/config.yaml`
(opened by [`04a`](04a-discover-config-file.md); append, don't re-create):

```yaml
  - { name: select-tests, class_name: SelectTestsMod }
```

## Tests

In `modules/tests/test_selection.py`. Fixtures: a 3-test `suite_cfg` fixture (and an empty
one); `logging_handler` for the `log.critical` path.

- `(suite_cfg, test_name="")` over a 3-test suite → yields 3 `("default", ctx)` in declaration
  order, each `ctx == {"key": test.get_name(), "test": test, "run_id": None}`.
- `(suite_cfg, test_name="foo")` where `foo` exists → yields exactly one `("default", ctx)`
  for `foo`.
- `(suite_cfg, test_name="nonexistent")` → `SuiteConfig.get_tests` itself `log.critical`s →
  `pytest.raises(SystemExit)`.
- `(empty_suite_cfg, test_name="")` → yields nothing (boundary: empty suite, generator emits
  zero ctxs).

## Acceptance criteria

- Tests pass.
- Output port `default` exercised: a fixture `tests.yaml` with three tests fans out to three
  `ctx`s with correctly-stamped keys (streamed end-to-end against the reference suite
  `../rtl-buddy-proj-template/design/sandbox/verif/tests.yaml`).
- Failure idiom exercised: a supplied `test_name` absent from the suite →
  `SuiteConfig.get_tests` emits `log.critical` (harness exit 1).
- The `modules/config.yaml` manifest entry `{ name: select-tests, class_name: SelectTestsMod }`
  validates and the harness resolves `select-tests` → `SelectTestsMod`.

## Constraints

- Yield one `ctx` per selected `TestConfig` via the generator: `{"key": test.get_name(),
  "test": test, "run_id": None}`.
- Do **not** add `--list` mode logic here — list-mode is routed upstream by `route-list-mode`.
- Do **not** wrap the lookup in `try/except`: an unknown `test_name` makes
  `SuiteConfig.get_tests` itself `log.critical` (harness exit 1). No port-routed result.
