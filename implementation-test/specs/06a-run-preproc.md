# Spec 06a: run-preproc (`RunPreprocMod`)

**Depends on:** spec 01 (schema), spec [01b](01b-suite-schema.md) (`RunPreprocMod`
reads `ctx["test"].get_preproc_path()`).
**References:** [03 — Per-test preparation section](../03-module-catalog.md). Parent index:
[06 — Per-test prep modules](06-prep-modules.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)`
signature, the allowed output forms (plain return / named-port tuple / generator), the
`finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py`
are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry
below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit
`a69d962`). This module **creates** `modules/rtl_test/build.py` — it is the first spec to write the
file, so establish the shared imports and module-level helpers here. The file then receives
further additions from run-process (`03`), the rest of the prep modules (`06b`, index
[06](06-prep-modules.md)), and the compile-cycle modules (`07a`–`07b`, index
[07](07-compile-cycle-modules.md)); coordinate shared imports and helpers with those specs.

## Goal

Run the optional per-test preprocessing hook that mutates `ctx["test"]` in place before
filelist generation.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry —
the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract:          default
persistent_inputs: [root_cfg]
inputs:            ctx, root_cfg
outputs:           default → ctx
                   fail    → result
```

```python
class RunPreprocMod:
    def run(self, ctx, root_cfg):
        preproc = ctx["test"].get_preproc_path()
        if preproc is None:
            return ("default", ctx)
        try:
            exec_hook(preproc, ctx["test"], root_cfg)   # mutates ctx["test"] in place
        except Exception as e:
            log.error("preproc_failed", key=ctx["key"], exc_info=e)
            return ("fail", { "key": ctx["key"], "result": ... })
        return ("default", ctx)
```

## Algorithm

1. Branch on the preproc path: `preproc = ctx["test"].get_preproc_path()` (spec 01b → `str |
   None`). If `None`, emit `("default", ctx)` once and return (rtl_buddy short-circuits the same
   way).
2. Read the script and execute it in a fresh namespace: `ns = {"logger": logger, "test_cfg":
   ctx["test"], "root_cfg": root_cfg}`, then `exec(compile(code, preproc, "exec"), ns)`. The
   script mutates `ctx["test"]` in place via setters (`set_plusarg`/`set_plusdefine`/
   `set_timeout`, spec 01b). Reuse the shared `exec_hook` helper (see Notes).
3. Emit `("default", ctx)` with the mutated test.
4. **Failure — script error.** Wrap the read + `exec` (step 2) in `try/except Exception` (user
   script exceptions plus `FileNotFoundError`/`PermissionError` reading the script) → emit
   `("fail", {"key": ctx["key"], "result": <FAIL with str(e) + traceback summary>})` and
   `log.error(..., exc_info=e)`. Notable divergence: per-test FAIL vs rtl_buddy's
   `logger.critical → typer.Abort`.

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

**Manifest** — this module opens the `rtl_test/build.py` block in `modules/config.yaml`
(later appended to by `06b`, `07a`, `03`, `07b`):

```yaml
- file: rtl_test/build.py
  plugins:
  - { name: run-preproc, class_name: RunPreprocMod }
```

## Tests

In `modules/tests/test_prep.py`. Fixtures: `tmp_path` preproc scripts (mutating, raising,
missing); a `ctx` fixture whose `test.get_preproc_path()` returns the script path or `None`;
a `root_cfg` fixture; `logging_handler` to assert `failure is True` without `SystemExit`.

- `ctx` whose `get_preproc_path()` is `None` → emits `("default", ctx)` exactly once, `ctx`
  unchanged (boundary: no preproc configured).
- `ctx` with a script that calls `test_cfg.set_plusarg`/`set_plusdefine`/`set_timeout` →
  emits `("default", ctx)` with `ctx["test"].pa`/`pd`/`timeout` reflecting the in-place
  mutations.
- `ctx` with a script that raises (e.g. `raise ValueError("boom")`) → emits `("fail", {"key",
  "result": <FAIL with str(e)>})`, `logging_handler.failure is True`, no `SystemExit`.
- `ctx` whose preproc path points at a missing file → `FileNotFoundError` reading the script →
  emits `("fail", …)`, `log.error`, no abort (boundary: read error routed like a script error).

## Acceptance criteria

- Tests pass.
- Both output ports (`default`, `fail`) are exercised: the no-script path passes `ctx`
  through unchanged, a script-set mutation is reflected on `ctx["test"]`, and a raising
  preproc script (or read error) routes a per-test FAIL `result` and logs at ERROR.
- The `modules/config.yaml` manifest entry `{ name: run-preproc, class_name: RunPreprocMod }`
  validates and the harness resolves `run-preproc` → `RunPreprocMod`.

## Constraints

- No preproc configured (`get_preproc_path()` is `None`) → emit `("default", ctx)` exactly once.
- The script mutates `ctx["test"]` **in place** via setters (`set_plusarg`/`set_plusdefine`/
  `set_timeout`); pass the mutated `ctx` through on `default`.
- Catch broad `Exception` around the read + `exec` (user-script errors plus
  `FileNotFoundError`/`PermissionError`) → emit `("fail", {key, result: <FAIL with str(e) +
  traceback>})` on the **unwired** `fail` port and `log.error(..., exc_info=e)`. Per-test FAIL,
  **not** `log.critical`/abort.
- Reuse the shared `exec_hook` helper (spec [05f](05f-expand-sweep.md)) — do **not** copy-paste.

## Notes

`run-preproc` and `expand-sweep` (spec [05f](05f-expand-sweep.md)) share the same
`exec`-with-namespace pattern — reuse the `exec_hook(path, namespace)` helper rather than
copy-pasting.
