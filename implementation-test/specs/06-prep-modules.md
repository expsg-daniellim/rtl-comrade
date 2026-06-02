# Spec 06: Per-test prep modules

**Depends on:** spec 01 (schema), spec [01b](01b-suite-schema.md) (`RunPreprocMod`
reads `ctx["test"].get_preproc_path()`; `WriteFilelistMod` reads
`ctx["test"].get_testbench().get_filelist()`), spec [01c](01c-model-schema.md)
(`WriteFilelistMod` reads `ctx["test"].get_model().get_filelist()` and `.path`).
**References:** [03 — Per-test preparation section](../03-module-catalog.md).

## Goal

Implement the per-test preprocessing hook and filelist generator that sit between sweep
expansion and compile.

## Deliverables

In `modules/rtl_test/build.py` (continuing from spec 03):

- `RunPreprocMod` — `(ctx, root_cfg)` → branches on
  `ctx["test"].get_preproc_path()` (spec [01b](01b-suite-schema.md) — returns `str |
  None`). If `None`, yield `("default", ctx)` once (rtl_buddy `vlog_sim.py:120-122`
  short-circuits the same way). Else read the file and `exec(code, ns)` with `ns =
  {"logger": logger, "test_cfg": ctx["test"], "root_cfg": root_cfg}`; the script
  mutates `ctx["test"]` in place (using setters like
  `test_cfg.set_plusarg(k, v)`, `set_plusdefine(k, v)`, `set_timeout(t)` per spec
  [01b](01b-suite-schema.md)). Reuses the `exec_hook` helper from spec 05.
  **Failure handling**: wrap `exec(code, ns)` in `try/except Exception as e:` (any
  exception from the user script, plus `FileNotFoundError` / `PermissionError` reading the
  preproc script itself; mirrors `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:134-137`).
  Emit `("fail", {"key": ctx["key"], "result": <FAIL payload with `str(e)` and traceback
  summary>})` and call `log.error` at emission with `exc_info=e`. **Notable divergence
  from rtl_buddy**: per-test FAIL vs rtl_buddy's `logger.critical → typer.Abort`.
- `WriteFilelistMod` — `(ctx)` → reimplements `VlogFilelist.write_output(unroll=True,
  flatten=False, strip=False, deduplicate=True,
  test_filelist=ctx["test"].get_testbench().get_filelist())` using
  `ctx["test"].get_model()` (the `ModelConfig` populated by `load-model` upstream,
  with `.filelist: list[str]` and `.path: str` per spec [01c](01c-model-schema.md))
  for `-F` include resolution. Writes the filelist file; emits two named outputs on
  success:
  - `("ctx", ctx)` (passthrough)
  - `("filelist", {"key": ctx["key"], "filelist": <Path>})` (consumed in lockstep by
    `build-compile-cmd` in spec 07).
  **Failure handling**: catch `Exception` from the filelist resolution / write
  (`FileNotFoundError`, `IsADirectoryError`, `OSError` / `PermissionError` for write
  errors; `KeyError` / `AttributeError` from a missing testbench filelist, or model-path
  resolution failure during `-F` recursion — e.g. `ctx["test"].get_model() is None`,
  meaning `load-model` did not fire upstream). Emit `("fail", {"key": ctx["key"],
  "result": <FAIL payload with `str(e)` in `desc`>})` and call `log.error` at emission
  with the attempted filelist path and the chain of `-F` includes the resolver was
  processing.

Manifest entries per [06](../06-graph-yaml.md).

Tests in `modules/tests/test_prep.py`:
- `run-preproc` no-op when no script.
- `run-preproc` mutates `test.pa`/`test.pd`/`test.timeout` when script sets them.
- `write-filelist` produces a syntactically valid `.f` file from a real `models.yaml` +
  testbench filelist; round-trip parse matches expected entries; `+incdir+` consolidation
  works.

## Acceptance criteria

- Tests pass.
- The filelist module reproduces the byte-for-byte output of rtl_buddy's `VlogFilelist`
  on the same inputs (modulo ordering if dedup is non-stable).

## Notes

`write-filelist` is one of the few modules reimplementing nontrivial rtl_buddy logic
(`VlogFilelist`). Port it carefully — the option-parsing regex, `-F` recursion with
unroll, `+incdir+`/`+libext+` handling, dedup, and the existence checks are all
behaviour worth replicating. See `rtl_buddy/src/rtl_buddy/tools/vlog_filelist.py` for
the reference.

Filename caveat from [07 settled 13 / KIV 17]: rtl_buddy writes a single `run.f` in CWD
per compile; concurrent compiles collide. The upstream rtl_buddy change (per-invocation
subdirs) will resolve this. Until then, `write-filelist` writes `run.f` literally.
