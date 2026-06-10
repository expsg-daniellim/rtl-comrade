# Spec 05f: expand-sweep (`ExpandSweepMod`)

**Depends on:** spec 01 (schema), spec [01b](01b-suite-schema.md)
(`TestConfig.get_sweep_path`).
**References:** [03 — Selection/expansion section](../03-module-catalog.md). Parent index:
[05 — Selection and expansion modules](05-selection-expansion-modules.md).

## Goal

Expand a test into N sweep variants by executing its sweep script, routing a per-test FAIL
on script failure.

## Deliverables

In `modules/rtl_test/setup.py` (continuing from spec 04):

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

## Tests

In `modules/tests/test_selection.py`:

- `expand-sweep` with no sweep yields once; with a sweep script yields N (keys suffixed
  `#i`).
- A sweep script that raises → emits `("fail", ...)` with `str(e)` in `desc` and
  `log.error`.

## Acceptance criteria

- Tests pass.
- Both output ports (`default`, `fail`) are exercised; a sweep script multiplies one
  fixture test by 4, and a raising script routes a per-test FAIL.

## Notes

`expand-sweep` and `run-preproc` (spec [06a](06a-run-preproc.md)) share the same
`exec`-with-namespace pattern. Factor a small `exec_hook(path, namespace)` helper into a
private module rather than copy-pasting.
