# Spec 05f: expand-sweep (`ExpandSweepMod`)

**Depends on:** spec 01 (schema), spec [01b](01b-suite-schema.md)
(`TestConfig.get_sweep_path`).
**References:** [03 — Selection/expansion section](../03-module-catalog.md). Parent index:
[05 — Selection and expansion modules](05-selection-expansion-modules.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)`
signature, the allowed output forms (plain return / named-port tuple / generator), the
`finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py`
are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry
below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit
`a69d962`). This module appends to `modules/rtl_test/setup.py`, which is created by spec
[`04a`](04a-discover-config-file.md) — append, do not overwrite. The file is shared with the
setup chain (`04a`–`04i`, index [04](04-setup-modules.md)), the selection/expansion chain
(`05a`–`05f`, index [05](05-selection-expansion-modules.md)), and git-status (`10b`);
coordinate shared imports and helpers with those specs.

## Goal

Expand a test into N sweep variants by executing its sweep script, routing a per-test FAIL
on script failure.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry —
the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract:          default
persistent_inputs: [root_cfg]
inputs:            ctx, root_cfg
outputs:           default → ctx   (one per sweep variant; key suffixed #i)
                   fail    → result
```

```python
class ExpandSweepMod:
    def run(self, ctx, root_cfg):
        sweep = ctx["test"].get_sweep_path()
        if sweep is None:
            yield ("default", ctx)
            return
        try:
            variants = exec_hook(sweep, ctx["test"], root_cfg)   # exec the sweep script → out_test_cfgs
        except Exception as e:
            log.error("sweep_failed", key=ctx["key"], exc_info=e)
            yield ("fail", { "key": ctx["key"], "result": ... })
            return
        for i, variant in enumerate(variants):
            yield ("default", { **ctx, "key": f"{ctx['key']}#{i}", "test": variant })
```

## Algorithm

1. Branch on the sweep path: `sweep = ctx["test"].get_sweep_path()` (spec 01b → `str | None`).
   If `None`, yield `("default", ctx)` once and return — no sweep configured.
2. Read the script and execute it in a fresh namespace: `ns = {"logger": logger, "TestConfig":
   TestConfig, "test_cfg": ctx["test"], "root_cfg": root_cfg, "out_test_cfgs": []}`, then
   `exec(compile(code, sweep, "exec"), ns)` (reuse the shared `exec_hook` helper — see Notes;
   matches rtl_buddy's `_expand_tests_with_sweep` namespace).
3. Fan out: for each variant `TestConfig` accumulated in `ns["out_test_cfgs"]`, yield
   `("default", {**ctx, "key": f"{ctx['key']}#{i}", "test": variant})`.
4. **Failure — script error.** Wrap the read + `exec` (step 2) in `try/except Exception`: any
   exception raised inside the user script, plus `FileNotFoundError`/`PermissionError` reading
   the script → emit `("fail", {"key": ctx["key"], "result": <FAIL with str(e) + traceback
   summary>})` and `log.error(..., exc_info=e)`. Notable divergence: per-test FAIL vs
   rtl_buddy's `logger.critical → typer.Abort`.

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

**Manifest** — append to the `- file: rtl_test/setup.py` block in `modules/config.yaml`
(opened by [`04a`](04a-discover-config-file.md); append, don't re-create):

```yaml
  - { name: expand-sweep, class_name: ExpandSweepMod }
```

## Tests

In `modules/tests/test_selection.py`. Fixtures: `tmp_path` sweep scripts (valid, raising,
empty); a `ctx` fixture whose `test.get_sweep_path()` returns the script path or `None`; a
`root_cfg` fixture; `logging_handler` to assert `failure is True` without `SystemExit`.

- `ctx` whose `get_sweep_path()` is `None` → yields `("default", ctx)` exactly once, key
  unchanged (boundary: no sweep configured).
- `ctx` with a sweep script that appends 4 variants to `out_test_cfgs` → yields 4
  `("default", variant_ctx)` with keys `f"{key}#0"`…`#3` and `test` set to each variant.
- `ctx` with a sweep script that raises (e.g. `raise RuntimeError("boom")`) → yields `("fail",
  {"key", "result": <FAIL with str(e)>})`, `logging_handler.failure is True`, no `SystemExit`.
- `ctx` whose sweep path points at a missing file → `FileNotFoundError` reading the script →
  yields `("fail", …)`, `log.error`, no abort (boundary: read error routed like a script error).
- `ctx` with a sweep script that leaves `out_test_cfgs` empty → yields nothing on `default`
  (boundary: zero-variant fan-out).

## Acceptance criteria

- Tests pass.
- Both output ports (`default`, `fail`) are exercised: a sweep script multiplies one fixture
  test by 4 (one `ctx` per variant, key suffixed `#i`); a raising sweep script routes a
  per-test FAIL `result` and logs at ERROR.
- The `modules/config.yaml` manifest entry `{ name: expand-sweep, class_name: ExpandSweepMod }`
  validates and the harness resolves `expand-sweep` → `ExpandSweepMod`.

## Constraints

- No sweep configured (`get_sweep_path()` is `None`) → yield `("default", ctx)` exactly once.
- Fan out one `("default", variant_ctx)` per `TestConfig` in `ns["out_test_cfgs"]`, keys
  suffixed `#i`.
- Catch broad `Exception` around the read + `exec` (user-script errors plus
  `FileNotFoundError`/`PermissionError`) → emit `("fail", {key, result: <FAIL with str(e) +
  traceback>})` on the **unwired** `fail` port and `log.error(..., exc_info=e)`. Per-test FAIL,
  **not** `log.critical`/abort (divergence from rtl_buddy's `typer.Abort`).
- Reuse the shared `exec_hook(path, namespace)` helper — do **not** copy-paste the
  `exec`-with-namespace pattern from `run-preproc`.

## Notes

`expand-sweep` and `run-preproc` (spec [06a](06a-run-preproc.md)) share the same
`exec`-with-namespace pattern. Factor a small `exec_hook(path, namespace)` helper into a
private module rather than copy-pasting.
