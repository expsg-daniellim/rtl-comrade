# Spec 06a: run-preproc (`RunPreprocMod`)

**Depends on:** spec 01 (schema), spec [01b](01b-suite-schema.md) (`RunPreprocMod` reads `test.get_preproc_path()`), spec [01c](01c-model-schema.md) / [05e](05e-load-model.md) (`load-model` runs upstream and supplies the joined `model` edge whose `ModelConfig` this module exposes to the script).
**References:** [03 — Per-test preparation section](../03-module-catalog.md). Parent index: [idx-06 — Per-test prep modules](../idx-06-prep.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)` signature, the allowed output forms (plain return / named-port tuple / generator), the `finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py` are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit `a69d962`). This module **creates** `modules/rtl_buddy/build.py` — it is the first spec to write the file, so establish the shared imports and module-level helpers here. The file then receives further additions from run-process (`03`), the rest of the prep modules (`06b`, index [idx-06](../idx-06-prep.md)), and the compile-cycle modules (`07a`–`07b`, index [idx-07](../idx-07-compile-cycle.md)); coordinate shared imports and helpers with those specs.

## Goal

Run the optional per-test preprocessing hook that mutates `test` (the bare `TestConfig`) in place before filelist generation.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry — the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract:          keyed_join (test, model)
key_field:         key
persistent_inputs: [root_cfg]
inputs:            test, model, root_cfg
outputs:           test  → TestConfig (self-keyed; mutated in place)
                   model → {key, value: ModelConfig}   (forwarded unchanged)
                   fail  → {key, result}
```

```python
class RunPreprocMod:
    def run(self, test, model, root_cfg):         # test: bare self-keyed TestConfig; model: {key, value} resolved ModelConfig from load-model
        preproc = test.get_preproc_path()
        if preproc is None:
            yield ("test", test)                  # no preproc → forward both edges unchanged
            yield ("model", model)
            return
        name = test.model                         # the model-name string (the test-edge invariant)
        test.model = model.value                  # expose the resolved ModelConfig to the script as test_cfg.model (rtl_buddy parity; restored below)
        ns = {"logger": logger, "test_cfg": test, "root_cfg": root_cfg}
        try:
            with open(preproc) as f:
                code = f.read()
            exec(compile(code, preproc, "exec"), ns)   # read + exec the script; mutates test in place
            yield ("test", test)                  # mutated test; test.model restored in the finally below
            yield ("model", model)                # forward the resolved model edge unchanged
        except Exception as e:
            result = make_fail_result(desc=str(e))
            log.error("preproc_failed", key=test.key, test_name=test.get_name(), exc_info=e,
                      result=result.results["result"], desc=result.results["desc"])   # → SummaryProcessor row
            yield ("fail", Result(test.key, result))
        finally:
            test.model = name                     # restore the name string on the test edge (mutations from the script persist)
```

## Algorithm

1. Branch on the preproc path: `preproc = test.get_preproc_path()` (`test` is the bare `TestConfig`; spec 01b → `str | None`). If `None`, emit `("test", test)` **and** `("model", model)` once (forward **both** joined edges) and return (rtl_buddy short-circuits the same way).
2. **Expose the resolved model to the script.** Save `name = test.model` (the model-name string), then set `test.model = model.value` (the resolved `ModelConfig` from the joined `model` edge) so the preproc script sees `test_cfg.model` as a `ModelConfig` — the same view rtl_buddy gives it (it resolves the model at suite-load, before `pre()`; spec [05e](05e-load-model.md), graph [06](../06-graph-yaml.md)). Build the namespace `ns = {"logger": logger, "test_cfg": test, "root_cfg": root_cfg}`, then read + `exec` the script into `ns` (`with open(preproc) as f: code = f.read()` then `exec(compile(code, preproc, "exec"), ns)`). The script mutates `test` in place via setters (`set_plusarg`/`set_plusdefine`/`set_timeout`, spec 01b) — those mutations land on the **real** `test`, so a copy is **not** usable here (it would lose them); the model swap is on the real object and restored in a `finally`.
3. Emit `("test", test)` (the mutated test) **and** `("model", model)` (the resolved model edge, forwarded unchanged) inside the `try`, after the `exec`; `test.model` is restored to the name string in a `finally`.
4. **Failure — script error.** Wrap the read + `exec` (step 2) in `try/except Exception` (user script exceptions plus `FileNotFoundError`/`PermissionError` reading the script), with the `finally` that restores `test.model` → emit `("fail", Result(test.key, <FAIL with str(e) + traceback summary>))` (and **neither** `test` nor `model` — the pair drops together) and `log.error("preproc_failed", …, exc_info=e, result=…, desc=…)` (the `result`/`desc` kwargs let `SummaryProcessor`'s watch-list collect the row). Notable divergence: per-test FAIL vs rtl_buddy's `logger.critical → typer.Abort`.

## Deliverables

In `modules/rtl_buddy/build.py` (continuing from spec 03):

- `RunPreprocMod` — `(test, model, root_cfg)`, `keyed_join` over `test` + `model` by key (`model` is the `{key, value}` resolved `ModelConfig` from `load-model`, now upstream — graph [06](../06-graph-yaml.md)); `root_cfg` persistent. A **generator** (it forwards two edges). Branches on `test.get_preproc_path()` (spec [01b](01b-suite-schema.md) — returns `str | None`). If `None`, yield `("test", test)` **and** `("model", model)` once (rtl_buddy `vlog_sim.py:120-122` short-circuits the same way). Else save `name = test.model`, set `test.model = model.value` (expose the resolved `ModelConfig` to the script — rtl_buddy parity), read the file and `exec(compile(code, preproc, "exec"), ns)` with `ns = {"logger": logger, "test_cfg": test, "root_cfg": root_cfg}`; the script mutates `test` in place (using setters like `test_cfg.set_plusarg(k, v)`, `set_plusdefine(k, v)`, `set_timeout(t)` per spec [01b](01b-suite-schema.md)) — mutate the **real** `test`, not a copy. Yield `("test", test)` **and** `("model", model)` inside the `try` after the `exec`, and restore `test.model = name` in a `finally`. Inlines the three-line read-and-`exec` directly — `expand-sweep` (spec [05f](05f-expand-sweep.md)) inlines the same lines and uses the same model-exposure swap, deliberately not shared.
  **Failure handling**: wrap `exec(code, ns)` in `try/except Exception as e:` (any exception from the user script, plus `FileNotFoundError` / `PermissionError` reading the preproc script itself; mirrors `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:134-137`). Emit `("fail", Result(test.key, <FAIL payload with `str(e)` and traceback summary>))` and call `log.error("preproc_failed", …)` at emission with `exc_info=e` **and `result`/`desc`** (so the `SummaryProcessor` watch-list, [10c](10c-summary-handler.md), renders the row). **Notable divergence from rtl_buddy**: per-test FAIL vs rtl_buddy's `logger.critical → typer.Abort`.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:119-139` — `VlogSim.pre`.

**Manifest** — this module opens the `rtl_buddy/build.py` block in `modules/config.yaml` (later appended to by `06b`, `07a`, `03`, `07b`):

```yaml
- file: rtl_buddy/build.py
  plugins:
  - { name: run-preproc, class_name: RunPreprocMod }
```

## Tests

In `modules/tests/test_prep.py`. Fixtures: `tmp_path` preproc scripts (mutating, raising, missing, one that reads `test_cfg.model`); a `test` fixture (a bare self-keyed `TestConfig`) whose `get_preproc_path()` returns the script path or `None`; a `model` edge fixture (`{key, value}` carrying a resolved `ModelConfig`, same key as `test`); a `root_cfg` fixture; `logging_handler` to assert `failure is True` without `typer.Exit`.

- `test` whose `get_preproc_path()` is `None` → emits `("test", test)` **and** `("model", model)` exactly once each, edges unchanged (boundary: no preproc configured — both forwarded).
- `test` with a script that calls `test_cfg.set_plusarg`/`set_plusdefine`/`set_timeout` → emits `("test", test)` with `test.pa`/`pd`/`timeout` reflecting the in-place mutations, **and** `("model", model)`; assert `test.model` is the **name string** afterward (the swap was restored).
- **Script sees the resolved model.** A preproc script that reads `test_cfg.model` (e.g. `test_cfg.set_plusdefine("MODEL", test_cfg.model.get_model_name())`) runs without `AttributeError` — `test_cfg.model` is the resolved `ModelConfig` during exec — and the mutation it derived persists on the emitted `test`, while `test.model` is restored to the name string.
- `test` with a script that raises (e.g. `raise ValueError("boom")`) → emits `("fail", Result(key, <FAIL with str(e)>))`, neither `test` nor `model`, `logging_handler.failure is True`, no `typer.Exit`; `test.model` is restored (the `finally`).
- `test` whose preproc path points at a missing file → `FileNotFoundError` reading the script → emits `("fail", …)`, `log.error`, no abort (boundary: read error routed like a script error).

## Acceptance criteria

- Tests pass.
- All three of `test`/`model`/`fail` are exercised: the no-script path forwards both `test` and `model` unchanged, a script-set mutation is reflected on the emitted `test` (with `model` forwarded), and a raising preproc script (or read error) routes a per-test FAIL `result` and logs at ERROR.
- A preproc script reading `test_cfg.model` sees the resolved `ModelConfig` (not the name string, not an `AttributeError`), and `test.model` is the name string again after the module returns.
- The `modules/config.yaml` manifest entry `{ name: run-preproc, class_name: RunPreprocMod }` validates and the harness resolves `run-preproc` → `RunPreprocMod`.

## Constraints

- `keyed_join` over `test` + `model` by key (`model` is the `{key, value}` resolved `ModelConfig` from the now-upstream `load-model`); `root_cfg` persistent.
- No preproc configured (`get_preproc_path()` is `None`) → emit `("test", test)` **and** `("model", model)` exactly once each (forward **both** joined edges).
- Expose the resolved model to the script: save `name = test.model`, set `test.model = model.value` before the `exec`, restore `test.model = name` in a `finally`. Operate on the **real** `test` (a copy would lose the script's in-place mutations) — the script sees `test_cfg.model` as a resolved `ModelConfig` (rtl_buddy parity).
- The script mutates `test` **in place** via setters (`set_plusarg`/`set_plusdefine`/`set_timeout`); after restoring `test.model`, forward the mutated test on the `test` port **and** the resolved model on the `model` port (the original `{key, value}`, unchanged).
- Catch broad `Exception` around the read + `exec` (user-script errors plus `FileNotFoundError`/`PermissionError`) → emit `("fail", {key, result: <FAIL with str(e) + traceback>})` on the **unwired** `fail` port (and **neither** `test` nor `model`) and `log.error("preproc_failed", …, exc_info=e)` carrying **`result`/`desc`** (so the `SummaryProcessor` watch-list collects the row). Per-test FAIL, **not** `log.fatal`/abort.
- Inline the read + `exec` directly (`with open(preproc) as f: code = f.read()` then `exec(compile(code, preproc, "exec"), ns)`); `expand-sweep` (spec [05f](05f-expand-sweep.md)) inlines the same three lines and uses the same `test.model` swap. Deliberately **not** a shared helper.

## Notes

`run-preproc` and `expand-sweep` (spec [05f](05f-expand-sweep.md)) run the same three-line read-and-`exec`. **Inline it at each site — do not factor it into a shared helper.** It is three trivial lines, and the two namespaces differ (preproc passes only `logger`/`test_cfg`/`root_cfg` and relies on the script's in-place mutation of `test_cfg`; sweep adds `TestConfig` + `out_test_cfgs`), so a wrapper would add a cross-file dependency between `build.py` and `setup.py` for no gain. Exceptions from the `open`/`exec` propagate into the surrounding `try/except` — see spec [05f](05f-expand-sweep.md) Notes.

**Guard scope.** This module is a **generator** (it forwards two edges, `test` + `model`). The success-path `yield`s of `test`/`model` sit **inside** the `try`, after the `exec`, and the `finally` restores `test.model`. Putting the `yield`s under the guard is the control-flow choice: each branch falls off its own end (success after the second `yield`, failure after the `fail` `yield`), so the `except` needs **no** trailing `return` to skip the success yields. It is safe because the harness drives module generators with a plain `for` loop and never throws into them (`src/rtl_comrade/node.py:304-306`), so a suspended `yield` cannot trigger the `except` — the only code that can actually raise is the read + `exec`. The module thus still owns exactly the exception set it can raise per `docs/modules/implementation.md` ("Exception Handling Is The Module's Responsibility"): the `open`/`exec` errors, and only those, route to `fail`. The `finally` runs *after* the success `yield`s, but the `test` edge still carries the name string: `test` forwards downstream **by reference** (`process_result` wraps it without copying, `node.py:256`), and the `finally` restores `test.model` during this node's own generator exhaustion — before any downstream node dereferences it. The `finally` only restores (no `yield`), so it is `GeneratorExit`-safe. Contrast `05f`, whose fan-out loop genuinely processes the script's `out_test_cfgs` and so must sit under the guard for a different reason.

**Script model-view compatibility (resolved).** Same mechanism as `expand-sweep` (spec [05f — Notes](05f-expand-sweep.md)). The drop-in promise covers config *files*; the preproc script is *code* run against **this plan's reimplemented** `test_cfg`/`root_cfg`. The model-field delta that would otherwise break drop-in preproc scripts — rtl_buddy resolves the model at suite-load, so its `test_cfg.model` is a resolved `ModelConfig` by `pre()` time, whereas this plan carries the name string on the test edge — is **closed**: `load-model` runs upstream (graph [06](../06-graph-yaml.md)) and this module sets `test_cfg.model = model.value` for the `exec`, so the script sees the resolved `ModelConfig` rtl_buddy would present (then restores the name string). **Residual (KIV):** (1) other reimplemented-`TestConfig` surface differences are still potential deltas — validate real preproc scripts before claiming parity; (2) a preproc script that *reassigns* `test_cfg.model` has the reassignment dropped (the `finally` restores the name string; the resolved `model` edge is fixed upstream). Record under [07 — Notable divergences](../07-ambiguities-and-assumptions.md) if a real script trips them.
