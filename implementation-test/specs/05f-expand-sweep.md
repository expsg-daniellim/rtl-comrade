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
`a69d962`). This module appends to `modules/rtl_buddy/setup.py`, which is created by spec
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
        ns = {"logger": logger, "TestConfig": TestConfig,
              "test_cfg": ctx["test"], "root_cfg": root_cfg, "out_test_cfgs": []}
        try:
            exec_hook(sweep, ns)   # read + exec the sweep script; populates ns["out_test_cfgs"]
        except Exception as e:
            result = make_fail_result(desc=str(e))
            log.error("sweep_failed", key=ctx["key"], test_name=ctx["test"].get_name(), exc_info=e,
                      result=result.results["result"], desc=result.results["desc"])   # → SummaryProcessor row
            yield ("fail", { "key": ctx["key"], "result": result })
            return
        for i, variant in enumerate(ns["out_test_cfgs"]):
            yield ("default", { **ctx, "key": f"{ctx['key']}#{i}", "test": variant })
```

## Algorithm

1. Branch on the sweep path: `sweep = ctx["test"].get_sweep_path()` (spec 01b → `str | None`).
   If `None`, yield `("default", ctx)` once and return — no sweep configured.
2. Build a fresh namespace `ns = {"logger": logger, "TestConfig": TestConfig, "test_cfg":
   ctx["test"], "root_cfg": root_cfg, "out_test_cfgs": []}` (matches rtl_buddy's
   `_expand_tests_with_sweep` namespace), then call `exec_hook(sweep, ns)` — the shared helper
   reads the script and `exec`s it into `ns`, populating `ns["out_test_cfgs"]` (see Notes).
3. Fan out: for each variant `TestConfig` accumulated in `ns["out_test_cfgs"]`, yield
   `("default", {**ctx, "key": f"{ctx['key']}#{i}", "test": variant})`.
4. **Failure — script error.** Wrap the read + `exec` (step 2) in `try/except Exception`: any
   exception raised inside the user script, plus `FileNotFoundError`/`PermissionError` reading
   the script → emit `("fail", {"key": ctx["key"], "result": <FAIL with str(e) + traceback
   summary>})` and `log.error("sweep_failed", …, exc_info=e, result=…, desc=…)` (the `result`/`desc`
   kwargs let `SummaryProcessor`'s watch-list collect the row). Notable divergence: per-test FAIL
   vs rtl_buddy's `logger.critical → typer.Abort`.

## Deliverables

In `modules/rtl_buddy/setup.py` (continuing from spec 04):

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
  "result": <FAIL payload with `str(e)` and traceback summary>})` and call
  `log.error("sweep_failed", …)` at emission with `exc_info=e` **and `result`/`desc`** (so the
  `SummaryProcessor` watch-list, [10c](10c-summary-handler.md), renders the row). **Notable
  divergence from rtl_buddy**: per-test FAIL vs
  rtl_buddy's `logger.critical → typer.Abort`.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/rtl_buddy.py:264-283` — `_expand_tests_with_sweep`.

**Manifest** — append to the `- file: rtl_buddy/setup.py` block in `modules/config.yaml`
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
  traceback>})` on the **unwired** `fail` port and `log.error("sweep_failed", …, exc_info=e)`
  carrying **`result`/`desc`** (so the `SummaryProcessor` watch-list collects the row). Per-test
  FAIL, **not** `log.fatal`/abort (divergence from rtl_buddy's `typer.Abort`).
- Reuse the shared `exec_hook(path, namespace)` helper — do **not** copy-paste the
  `exec`-with-namespace pattern from `run-preproc`.

## Notes

`expand-sweep` and `run-preproc` (spec [06a](06a-run-preproc.md)) share the same
`exec`-with-namespace pattern. Factor it into one small helper — **this spec is the canonical
definition; `06a` references it**:

```python
# modules/rtl_buddy/_hooks.py  (private; not a graph-module file)
def exec_hook(path: str, namespace: dict) -> None:
    with open(path) as f:
        code = f.read()
    exec(compile(code, path, "exec"), namespace)   # mutates namespace in place
```

- **Two args, `(path, namespace)`** — the caller builds the namespace because the two call
  sites differ: sweep adds `TestConfig` + `out_test_cfgs` (and reads `out_test_cfgs` back out);
  preproc passes only `logger`/`test_cfg`/`root_cfg` and relies on in-place `test_cfg` mutation.
  A fixed `(path, test, root_cfg)` form cannot express either difference. The helper only does
  read + `exec` into the caller's dict; it returns nothing.
- **Exceptions propagate** to the caller (it does **not** swallow like rtl_buddy's
  `_expand_tests_with_sweep`/`VlogSim.pre`, which `logger.critical` and continue). Each caller
  wraps the call in `try/except Exception` to route a per-test FAIL — the deliberate divergence
  documented above. `FileNotFoundError`/`PermissionError` from the `open` are caught the same way.
