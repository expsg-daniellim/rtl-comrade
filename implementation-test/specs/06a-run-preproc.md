# Spec 06a: run-preproc (`RunPreprocMod`)

**Depends on:** spec 01 (schema), spec [01b](01b-suite-schema.md) (`RunPreprocMod`
reads `ctx["test"].get_preproc_path()`).
**References:** [03 — Per-test preparation section](../03-module-catalog.md). Parent index:
[06 — Per-test prep modules](06-prep-modules.md).

## Goal

Run the optional per-test preprocessing hook that mutates `ctx["test"]` in place before
filelist generation.

## Deliverables

In `modules/rtl_test/build.py` (continuing from spec 03):

- `RunPreprocMod` — `(ctx, root_cfg)` → branches on
  `ctx["test"].get_preproc_path()` (spec [01b](01b-suite-schema.md) — returns `str |
  None`). If `None`, yield `("default", ctx)` once (rtl_buddy `vlog_sim.py:120-122`
  short-circuits the same way). Else read the file and `exec(code, ns)` with `ns =
  {"logger": logger, "test_cfg": ctx["test"], "root_cfg": root_cfg}`; the script
  mutates `ctx["test"]` in place (using setters like
  `test_cfg.set_plusarg(k, v)`, `set_plusdefine(k, v)`, `set_timeout(t)` per spec
  [01b](01b-suite-schema.md)). Reuses the `exec_hook` helper from spec
  [05f](05f-expand-sweep.md).
  **Failure handling**: wrap `exec(code, ns)` in `try/except Exception as e:` (any
  exception from the user script, plus `FileNotFoundError` / `PermissionError` reading the
  preproc script itself; mirrors `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:134-137`).
  Emit `("fail", {"key": ctx["key"], "result": <FAIL payload with `str(e)` and traceback
  summary>})` and call `log.error` at emission with `exc_info=e`. **Notable divergence
  from rtl_buddy**: per-test FAIL vs rtl_buddy's `logger.critical → typer.Abort`.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:119-139` — `VlogSim.pre`.

Manifest entries per [06](../06-graph-yaml.md).

## Tests

In `modules/tests/test_prep.py`:

- `run-preproc` no-op when no script.
- `run-preproc` mutates `test.pa`/`test.pd`/`test.timeout` when script sets them.
- A preproc script that raises → emits `("fail", ...)` with `str(e)` in `desc` and
  `log.error`.

## Acceptance criteria

- Tests pass.
- Both output ports (`default`, `fail`) are exercised; the no-script path passes `ctx`
  through and a script-set mutation is reflected on `ctx["test"]`.

## Notes

`run-preproc` and `expand-sweep` (spec [05f](05f-expand-sweep.md)) share the same
`exec`-with-namespace pattern — reuse the `exec_hook(path, namespace)` helper rather than
copy-pasting.
