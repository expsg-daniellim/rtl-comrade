# Spec 05: Selection and expansion modules

**Depends on:** spec 01 (schema), spec [01a](01a-builder-schema.md) (builder schema —
`FilterRegLvlMod` consumes `RtlBuilderConfig`), spec [01b](01b-suite-schema.md)
(`SuiteConfig` / `TestConfig` / `UVMConfig` — every module here reads from
`ctx["test"]`), spec [01c](01c-model-schema.md) (`LoadModelMod` constructs
`ModelConfigLoader`).
**References:** [03 — Selection/expansion section](../03-module-catalog.md).

## Goal

Implement the list-routing front end, the test stream entry, level filtering, lazy
model loading, and sweep expansion.

## Deliverables

In `modules/rtl_test/setup.py` (continuing from spec 04):

- `RouteListModeMod` — `(suite_cfg, list:bool=False)` → emits `("list", suite_cfg)` if
  `list` else `("run", suite_cfg)`. Pure data classifier.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/rtl_buddy.py:182-184` — the `if list_tests:` branch in `do_cmd_test`.
- `ListTestNamesMod` — `(suite_cfg)` → prints `"  ".join(suite_cfg.get_test_names())`
  (spec [01b](01b-suite-schema.md) — returns `list[str]` of test names in declaration
  order) and emits nothing. Terminal sink.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/rtl_buddy.py:183` — the `typer.echo` of `get_test_names()`; `get_test_names` at `config/suite.py:69-76`.
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
- `FilterRegLvlMod` — `(ctx, builder_cfg, reg_level=None, start_level=None)` →
  `("keep", ctx)` if level inside `[start_level, reg_level]` window (or both `None`),
  else `("skip", {"key": ctx["key"], "result": SkipResults(desc)})`. The per-test
  level comes from `ctx["test"].get_reglvl(builder_cfg.get_name())` (mirrors
  `rtl_buddy/src/rtl_buddy/rtl_buddy.py:350`) — only the builder *name* is needed,
  not the full config object, but the persistent port carries the whole
  `RtlBuilderConfig` (see spec [01a](01a-builder-schema.md)) because the same
  payload feeds `cc-build`, `seed`, and `sim-build` downstream. No failure path
  (SKIP is a routing decision and is pass-like; no log call).
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/rtl_buddy.py:349-357` — `_do_test_suite` level filter; `get_reglvl` at `config/test.py:287-299`; `SkipResults` at `runner/test_results.py:71-78`.
- `LoadModelMod` — `(ctx)` → resolves `resolved = ctx["test"].suite_dir /
  ctx["test"].model_path` (fields per spec [01b](01b-suite-schema.md)), constructs
  `ModelConfigLoader(str(resolved))` (spec [01c](01c-model-schema.md)), calls
  `loader.get_model(ctx["test"].model_name)`, assigns
  `ctx["test"].model = the_model`, emits `("default", ctx)`.
  **Failure handling**: catch broad `Exception` from both `ModelConfigLoader.__init__`
  (I/O / parse / schema mismatch — Plan B's loader **raises rather than
  `log.critical`s**, see spec [01c — Notable divergences](01c-model-schema.md)) and
  `loader.get_model(name)` (model not in file). Specific classes in play:
  `FileNotFoundError`, `PermissionError`, `IsADirectoryError` (file I/O);
  `serde.SerdeError` / `yaml.YAMLError` (parse); `TypeError` / `KeyError` (schema
  mismatch); `KeyError` or custom `ModelNotFoundError` (lookup miss). Emit
  `("fail", {"key": ctx["key"], "result": <FAIL payload with `str(e)` in `desc`>})`
  and call `log.error` at emission with the resolved `model_path`. **Notable
  divergence from rtl_buddy**: per-test FAIL preserves run continuity; rtl_buddy
  aborts the whole run via `logger.critical` inside `ModelConfigLoader`
  (`rtl_buddy/src/rtl_buddy/config/model.py:78-81,100`; [07 settled
  10](../07-ambiguities-and-assumptions.md)).
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/config/model.py:66-100` — `ModelConfigLoader.__init__` + `get_model`.
- `ExpandSweepMod` — `(ctx, root_cfg)` → branches on
  `ctx["test"].get_sweep_path()` (spec [01b](01b-suite-schema.md) — returns `str |
  None`). If `None`, yield `("default", ctx)` once. Else read the file at that path
  and `exec(code, ns)` with `ns = {"logger": logger, "TestConfig": TestConfig,
  "test_cfg": ctx["test"], "root_cfg": root_cfg, "out_test_cfgs": []}`; after the
  exec, yield one `("default", ctx_with_test=variant)` per `TestConfig` in
  `ns["out_test_cfgs"]` (key suffixed `#i`).
  **Failure handling**: wrap the file-read + `exec(code, ns)` in `try/except
  Exception as e:` (any exception raised inside the user-supplied script, plus
  `FileNotFoundError` / `PermissionError` reading the sweep script itself; mirrors
  `rtl_buddy/src/rtl_buddy/rtl_buddy.py:279-281`). Emit `("fail", {"key": ctx["key"],
  "result": <FAIL payload with `str(e)` and traceback summary>})` and call `log.error` at
  emission with `exc_info=e`. **Notable divergence from rtl_buddy**: per-test FAIL vs
  rtl_buddy's `logger.critical → typer.Abort`.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/rtl_buddy.py:264-283` — `_expand_tests_with_sweep`.

Manifest entries per [06](../06-graph-yaml.md).

Tests in `modules/tests/test_selection.py`:
- `select` yields all tests in declaration order; `test_name="foo"` yields only `foo`;
  unknown name critical-logs.
- `list-names` prints expected names.
- `filter` keep/skip routing matches rtl_buddy `_do_test_suite` level-filter logic.
- `load-model` attaches model from a real `models.yaml`.
- `expand-sweep` with no sweep yields once; with a sweep script yields N.

## Acceptance criteria

- Tests pass.
- Streamed end-to-end: a fixture `tests.yaml` with three tests fans out to three `ctx`s
  with correctly-stamped keys, and a sweep script multiplies one of them by 4.

## Notes

`expand-sweep` and `run-preproc` (spec 06) share the same `exec`-with-namespace pattern.
Factor a small `exec_hook(path, namespace)` helper into a private module rather than
copy-pasting.
