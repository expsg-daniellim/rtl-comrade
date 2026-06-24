# Spec 05f: expand-sweep (`ExpandSweepMod`)

**Depends on:** spec 01 (schema), spec [01b](01b-suite-schema.md) (`TestConfig.get_sweep_path`).
**References:** [03 — Selection/expansion section](../03-module-catalog.md). Parent index: [idx-05 — Selection and expansion modules](../idx-05-selection-expansion.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)` signature, the allowed output forms (plain return / named-port tuple / generator), the `finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py` are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit `a69d962`). This module appends to `modules/rtl_buddy/setup.py`, which is created by spec [`04a`](04a-discover-config-file.md) — append, do not overwrite. The file is shared with the setup chain (`04a`–`04i`, index [idx-04](../idx-04-setup.md)), the selection/expansion chain (`05a`–`05f`, index [idx-05](../idx-05-selection-expansion.md)), and git-status (`10b`); coordinate shared imports and helpers with those specs.

## Goal

Expand a test into N sweep variants by executing its sweep script, routing a per-test FAIL on script failure.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry — the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract:          keyed_join (test, model)
key_field:         key
persistent_inputs: [root_cfg]
inputs:            test, model, root_cfg
outputs:           test  → TestConfig (self-keyed)         (one per sweep variant; .key suffixed #i)
                   model → {key, value: ModelConfig}       (one per variant; re-keyed to the variant)
                   fail  → TestResult (self-keyed)
```

```python
class ExpandSweepMod:
    def run(self, test:TestConfig, model:KeyedValue[ModelConfig], root_cfg:RootConfig):            # test: bare self-keyed TestConfig; model: {key, value} resolved ModelConfig from load-model
        sweep = test.get_sweep_path()
        if sweep is None:
            yield ("test", test)                     # no sweep → forward both edges unchanged
            yield ("model", model)
            return
        name = test.model                            # the model-name string (the test-edge invariant)
        test.model = model.value                     # expose the resolved ModelConfig to the script as test_cfg.model (rtl_buddy parity; restored below)
        ns = {"logger": logger, "TestConfig": TestConfig,
              "test_cfg": test, "root_cfg": root_cfg, "out_test_cfgs": []}
        try:
            with open(sweep) as f:
                code = f.read()
            exec(compile(code, sweep, "exec"), ns)   # read + exec the sweep script; populates ns["out_test_cfgs"]
            for i, variant in enumerate(ns["out_test_cfgs"]):
                variant.key = f"{test.key}#{i}"      # stamp the per-variant instance identity
                variant.model = name                 # name string back on the test edge; the resolved model rides the model edge
                yield ("test", variant)              # bare TestConfig variant, self-keyed (distinct object)
                yield ("model", KeyedValue(variant.key, model.value))   # same ModelConfig, re-keyed to the variant
        except Exception as e:
            result = TestResult.prep(test.key, str(e))
            log.error("sweep_failed", key=test.key, test_name=test.get_name(), exc_info=e,
                      result=result.result, desc=result.desc)   # → SummaryProcessor row
            yield ("fail", result)
        finally:
            test.model = name                        # restore (defensive; the parent test is not emitted on the sweep branch)
```

## Algorithm

1. Branch on the sweep path: `sweep = test.get_sweep_path()` (`test` is the bare `TestConfig`; spec 01b → `str | None`). If `None`, yield `("test", test)` **and** `("model", model)` once (forward **both** joined edges unchanged) and return — no sweep configured.
2. **Expose the resolved model to the script.** Save `name = test.model` (the model-name string), then set `test.model = model.value` (the resolved `ModelConfig` from the joined `model` edge) so the sweep script sees `test_cfg.model` as a `ModelConfig` — the same view rtl_buddy gives it (rtl_buddy resolves the model at suite-load, before sweep; spec [05e](05e-load-model.md), graph [06](../06-graph-yaml.md)). This is a temporary state of the **real** `test` object (not a copy) — identical to what rtl_buddy's `_expand_tests_with_sweep` passes — restored in a `finally`. Then build the namespace `ns = {"logger": logger, "TestConfig": TestConfig, "test_cfg": test, "root_cfg": root_cfg, "out_test_cfgs": []}` (matches rtl_buddy's namespace) and read + `exec` the script into `ns` (`with open(sweep) as f: code = f.read()` then `exec(compile(code, sweep, "exec"), ns)`), populating `ns["out_test_cfgs"]`.
3. Fan out: for each variant `TestConfig` accumulated in `ns["out_test_cfgs"]`, stamp `variant.key = f"{test.key}#{i}"`, restore `variant.model = name` (the name string — the resolved `ModelConfig` rides the `model` edge, not the test object), and yield both `("test", variant)` (the bare variant, self-keyed) **and** `("model", KeyedValue(variant.key, model.value))` (the same resolved `ModelConfig`, re-keyed to the variant). Each variant is a distinct object, so stamping in place is sound — no copy needed (contrast `expand-runs`, which shares one object across runs). All variants inherit the parent test's one resolved model (sweep does not re-resolve — matching rtl_buddy, where the model is fixed before the script runs).
4. **Failure.** Wrap the read + `exec` **and the fan-out loop** (steps 2–3) in a single `try/except Exception`, with a `finally` that restores `test.model = name` (the swap from step 2): any exception raised inside the user script, `FileNotFoundError`/`PermissionError` reading the script, **and** the errors the fan-out can raise on malformed script output (`TypeError` if `ns["out_test_cfgs"]` is non-iterable, `AttributeError` if a "variant" doesn't accept `.key`, `KeyError` if the script deleted `out_test_cfgs` from `ns`) → emit `("fail", TestResult.prep(test.key, str(e)))` (its `desc` carries `str(e)` + a traceback summary; **neither** `test` nor `model` — the pair drops together at the unwired `fail` port) and `log.error("sweep_failed", …, exc_info=e, result=…, desc=…)` (the `result`/`desc` kwargs let `SummaryProcessor`'s watch-list collect the row). Notable divergence: per-test FAIL vs rtl_buddy's `logger.critical → typer.Abort`. The `yield` sits inside the guard deliberately — the harness only *iterates* the module generator (`node.py`: `for r in res: …`); it never `.throw()`s into it, and `GeneratorExit`/`CancelledError` are `BaseException`, so `except Exception` cannot misclassify a control signal as a sweep failure. The `finally` does not `yield`, so it is safe under `GeneratorExit`.

## Deliverables

In `modules/rtl_buddy/setup.py` (continuing from spec 04):

- `ExpandSweepMod` — `(test, model, root_cfg)`, `keyed_join` over `test` + `model` by key (`model` is the `{key, value}` resolved `ModelConfig` from `load-model`, now upstream — graph [06](../06-graph-yaml.md)); `root_cfg` persistent. `test` is the bare self-keyed `TestConfig`. Branches on `test.get_sweep_path()` (spec [01b](01b-suite-schema.md) — returns `str | None`). If `None`, yield `("test", test)` **and** `("model", model)` once (forward both). Else save `name = test.model`, set `test.model = model.value` (expose the resolved `ModelConfig` to the script — rtl_buddy parity), read the file at that path and `exec(code, ns)` with `ns = {"logger": logger, "TestConfig": TestConfig, "test_cfg": test, "root_cfg": root_cfg, "out_test_cfgs": []}`; after the exec, for each `variant` in `ns["out_test_cfgs"]` stamp `variant.key = f"{test.key}#{i}"`, restore `variant.model = name`, and yield `("test", variant)` **and** `("model", KeyedValue(variant.key, model.value))` (key suffixed `#i`). Restore `test.model = name` in a `finally`.
  **Failure handling**: wrap the file-read + `exec(code, ns)` **and the fan-out loop** in one `try/except Exception as e:` (any exception raised inside the user-supplied script, `FileNotFoundError` / `PermissionError` reading the sweep script itself, and the fan-out's own `TypeError`/`AttributeError`/`KeyError` on malformed `out_test_cfgs`; mirrors `rtl_buddy/src/rtl_buddy/rtl_buddy.py:279-281`). Emit `("fail", TestResult.prep(test.key, str(e)))` (its `desc` carries `str(e)` and a traceback summary) and call `log.error("sweep_failed", …)` at emission with `exc_info=e` **and `result`/`desc`** (so the `SummaryProcessor` watch-list, [10c](10c-summary-handler.md), renders the row). The module catches **every** exception its own code can raise per `docs/modules/implementation.md` ("Exception Handling Is The Module's Responsibility"); the read+`exec` and the fan-out are equally its code, so both sit under the guard. **Notable divergence from rtl_buddy**: per-test FAIL vs rtl_buddy's `logger.critical → typer.Abort`.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/rtl_buddy.py:264-283` — `_expand_tests_with_sweep`.

**Manifest** — append to the `- file: rtl_buddy/setup.py` block in `modules/config.yaml` (opened by [`04a`](04a-discover-config-file.md); append, don't re-create):

```yaml
  - { name: expand-sweep, class_name: ExpandSweepMod }
```

## Tests

In `modules/tests/test_selection.py`. Fixtures: `tmp_path` sweep scripts (valid, raising, empty, one that reads `test_cfg.model`); a `test` fixture (a bare self-keyed `TestConfig`) whose `get_sweep_path()` returns the script path or `None`; a `model` edge fixture (`{key, value}` carrying a resolved `ModelConfig`, same key as `test`); a `root_cfg` fixture; `logging_handler` to assert `failure is True` without `typer.Exit`.

- `test` whose `get_sweep_path()` is `None` → yields `("test", test)` **and** `("model", model)` exactly once each, `.key` unchanged (boundary: no sweep configured — both edges forwarded).
- `test` with a sweep script that appends 4 variants to `out_test_cfgs` → yields 4 `("test", variant)` with `variant.key` `f"{key}#0"`…`#3` (each payload the variant `TestConfig` with `variant.model` the **name string**) **and** 4 `("model", KeyedValue(f"{key}#i", <ModelConfig>))` with matching keys.
- **Script sees the resolved model.** A sweep script that reads `test_cfg.model` (e.g. asserts `test_cfg.model.get_model_name() == <expected>` or appends a variant derived from it) runs without `AttributeError` — `test_cfg.model` is the resolved `ModelConfig` during exec — and `test.model` is restored to the name string afterward.
- `test` with a sweep script that raises (e.g. `raise RuntimeError("boom")`) → yields `("fail", TestResult.prep(key, str(e)))`, neither `test` nor `model`, `logging_handler.failure is True`, no `typer.Exit`; `test.model` is restored (the `finally`).
- `test` whose sweep path points at a missing file → `FileNotFoundError` reading the script → yields `("fail", …)`, `log.error`, no abort (boundary: read error routed like a script error).
- `test` with a sweep script that leaves `out_test_cfgs` empty → yields nothing on `test`/`model` (boundary: zero-variant fan-out).
- `test` with a sweep script that sets `out_test_cfgs` to a non-iterable (e.g. an `int`), or appends an object that rejects `.key` assignment → the fan-out raises `TypeError`/`AttributeError`, caught by the same guard → yields `("fail", TestResult.prep(key, str(e)))`, `log.error`, no abort (boundary: malformed script output routed like a script error, not bubbled to the harness).

## Acceptance criteria

- Tests pass.
- All three non-fail/fail ports are exercised: a sweep script multiplies one fixture test by 4 (one `test` edge **and** one re-keyed `model` edge per variant, key suffixed `#i`); a raising sweep script routes a per-test FAIL `result` and logs at ERROR.
- A sweep script reading `test_cfg.model` sees the resolved `ModelConfig` (not the name string, not an `AttributeError`), and `test.model` is the name string again after the module returns.
- The `modules/config.yaml` manifest entry `{ name: expand-sweep, class_name: ExpandSweepMod }` validates and the harness resolves `expand-sweep` → `ExpandSweepMod`.

## Constraints

- `keyed_join` over `test` + `model` by key (`model` is the `{key, value}` resolved `ModelConfig` from `load-model`, now positioned upstream of this node); `root_cfg` persistent.
- No sweep configured (`get_sweep_path()` is `None`) → yield `("test", test)` **and** `("model", model)` exactly once each (forward **both** joined edges).
- Expose the resolved model to the script: save `name = test.model`, set `test.model = model.value` before the `exec`, and restore `test.model = name` in a `finally`. The script sees `test_cfg.model` as a resolved `ModelConfig` (rtl_buddy parity), not a name string. Operate on the **real** `test` object, not a copy (matches rtl_buddy's `_expand_tests_with_sweep`).
- Fan out per `TestConfig` in `ns["out_test_cfgs"]`: stamp `variant.key = f"{test.key}#{i}"`, set `variant.model = name` (name string on the test edge), and yield `("test", variant)` **and** `("model", KeyedValue(variant.key, model.value))` (the same resolved model, re-keyed; bare self-keyed variant, each a distinct object). All variants share the parent's resolved model.
- Catch broad `Exception` around the read + `exec` **and the fan-out loop** (user-script errors, `FileNotFoundError`/`PermissionError`, and the fan-out's `TypeError`/`AttributeError`/`KeyError` on malformed `out_test_cfgs`) → emit `("fail", TestResult.prep(test.key, str(e)))` (its `desc` carries `str(e)` + a traceback summary) on the **unwired** `fail` port (and **neither** `test` nor `model`) and `log.error("sweep_failed", …, exc_info=e)` carrying **`result`/`desc`** (so the `SummaryProcessor` watch-list collects the row). Per-test FAIL, **not** `log.fatal`/abort (divergence from rtl_buddy's `typer.Abort`). The `yield` is inside the guard: the harness only iterates the generator, never `.throw()`s into it, so `except Exception` cannot capture a downstream or control-flow exception. The `finally` restoring `test.model` does not `yield`, so it is `GeneratorExit`-safe.
- Inline the read + `exec` directly (`with open(sweep) as f: code = f.read()` then `exec(compile(code, sweep, "exec"), ns)`); `run-preproc` (spec [06a](06a-run-preproc.md)) inlines the same three lines independently. The pattern is deliberately **not** abstracted into a shared helper.

## Notes

`expand-sweep` and `run-preproc` (spec [06a](06a-run-preproc.md)) run the same three-line read-and-`exec` (`with open(path) as f: code = f.read()` then `exec(compile(code, path, "exec"), ns)`). **Inline it at each site — do not factor it into a shared helper.** It is three trivial lines, and the two call sites build different namespaces anyway (sweep adds `TestConfig` + an `out_test_cfgs` list it reads back out; preproc passes only `logger`/`test_cfg`/`root_cfg` and relies on in-place `test_cfg` mutation), so a wrapper would buy nothing over the literal lines while adding a cross-file dependency between `setup.py` and `build.py`.

- **Exceptions propagate** into the surrounding `try/except Exception` (the code does **not** swallow like rtl_buddy's `_expand_tests_with_sweep`/`VlogSim.pre`, which `logger.critical` and continue). Each site routes a per-test FAIL — the deliberate divergence documented above. `FileNotFoundError`/`PermissionError` from the `open` are caught the same way, as are the fan-out's own `TypeError`/`AttributeError`/`KeyError` on malformed `out_test_cfgs` (the module owns every exception its code can raise; none bubble to the harness backstop).
- **Partial emission on a malformed variant.** Because the `yield`s run inside the loop (not after a materialised list), a script that yields some good variants then a bad one — e.g. `out_test_cfgs = [good0, good1, 5]` — emits the `("test", good0)`/`("model", …)` and `("test", good1)`/`("model", …)` pairs before the `5.key = …` `AttributeError` routes `("fail", …)`. This is accepted: a single inline loop is the chosen shape (no list materialisation, no second loop), and the common cases stay clean — a raising script and a non-iterable `out_test_cfgs` both fail *before* any `test` edge is emitted.
- **Script model-view compatibility (resolved).** The `exec` namespace injects **this plan's reimplemented** `TestConfig`/`root_cfg`, not rtl_buddy's. The one model-field delta that used to break drop-in sweep scripts — rtl_buddy resolves the model at suite-load, so its `test_cfg.model` is a resolved `ModelConfig` by sweep time, whereas this plan keeps the name string on the test edge — is **closed** here: `load-model` runs upstream (graph [06](../06-graph-yaml.md)), and the module sets `test_cfg.model = model.value` for the duration of the `exec` so the script sees exactly the resolved `ModelConfig` rtl_buddy would present (then restores the name string on the test edge). This is why `load-model` was moved ahead of the hooks. **Residual (KIV):** (1) other reimplemented-`TestConfig` surface differences (method/attribute shapes) are still potential deltas — validate real sweep scripts against the reimplemented `TestConfig` before claiming parity; (2) a sweep script that *reassigns* `test_cfg.model` to a different `ModelConfig` has that reassignment dropped (the `finally` restores the name string and the resolved `model` edge is fixed upstream) — in rtl_buddy such a reassignment could change what compiles. Both are narrow; record in [`divergences.md`](../../divergences.md) if a real script trips them. `run-preproc` (spec [06a](06a-run-preproc.md)) uses the same model-exposure mechanism.
