# Spec 05: Selection and expansion modules

**Depends on:** spec 01 (schema).
**References:** [03 — Selection/expansion section](../03-module-catalog.md).

## Goal

Implement the list-routing front end, the test stream entry, level filtering, lazy
model loading, and sweep expansion.

## Deliverables

In `modules/rtl_test/setup.py` (continuing from spec 04):

- `RouteListModeMod` — `(suite_cfg, list:bool=False)` → emits `("list", suite_cfg)` if
  `list` else `("run", suite_cfg)`. Pure data classifier.
- `ListTestNamesMod` — `(suite_cfg)` → prints `"  ".join(get_test_names())` and emits
  nothing. Terminal sink.
- `SelectTestsMod` — `(suite_cfg, test_name:str="")` → generator yielding one
  `{"key": test.get_name(), "test": test}` per selected test. No mode logic; `--list` is
  handled upstream.
- `FilterRegLvlMod` — `(ctx, builder_cfg, reg_level=None, start_level=None)` →
  `("keep", ctx)` if level inside `[start_level, reg_level]` window (or both `None`),
  else `("skip", {"key": ctx["key"], "result": SkipResults(desc)})`.
- `LoadModelMod` — `(ctx)` → loads the test's `models.yaml` (resolved relative to the
  suite dir recorded by `parse-suite-config` in spec 04), attaches `ModelConfig` to
  `ctx["test"]`, emits `ctx`.
- `ExpandSweepMod` — `(ctx, root_cfg)` → if `test.sweep_path` set, `exec`s the script
  with `{logger, TestConfig, test_cfg, root_cfg, out_test_cfgs: []}` and yields one
  `ctx` per produced variant (key suffixed `#i`); else yields `ctx` unchanged once.

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
