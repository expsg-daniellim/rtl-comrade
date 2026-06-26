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
                   fail  → TestResult (self-keyed)
```

```python
class RunPreprocMod:
    def run(self, test:TestConfig, model:KeyedValue[ModelConfig], root_cfg:RootConfig):         # test: bare self-keyed TestConfig; model: {key, value} resolved ModelConfig from load-model
        preproc = test.get_preproc_path()
        if preproc is None:
            yield ("test", test)                  # no preproc → forward both edges unchanged
            yield ("model", model)
            return
        name = test.model                         # the model-name string (the test-edge invariant)
        ns = {"logger": logger, "test_cfg": test, "root_cfg": root_cfg}
        try:                                      # phase 1 — read the script: per-exception I/O events (mirrors io.py); no swap yet, so a read failure needs no restore
            with open(preproc) as f:
                code = f.read()
        except FileNotFoundError:
            log.error("preproc_script_not_found", key=test.key, test_name=test.get_name(), preproc_path=str(preproc))
            yield ("fail", TestResult.prep(test.key, test.get_name(), f"preproc script not found: {preproc}")); return
        except PermissionError as e:
            log.error("preproc_script_permission", key=test.key, test_name=test.get_name(), preproc_path=str(preproc), err=e.strerror)
            yield ("fail", TestResult.prep(test.key, test.get_name(), f"cannot read preproc script {preproc}")); return
        except OSError as e:
            log.error("preproc_script_read_error", key=test.key, test_name=test.get_name(), preproc_path=str(preproc), err=e.strerror, errno=e.errno)
            yield ("fail", TestResult.prep(test.key, test.get_name(), f"cannot read preproc script {preproc}")); return
        test.model = model.value                  # expose the resolved ModelConfig to the script as test_cfg.model (rtl_buddy parity) — live only for the exec, restored on both exits below
        try:                                      # phase 2 — exec user code: anything can raise, so one broad (but named) event
            exec(compile(code, preproc, "exec"), ns)   # mutates test in place
        except Exception as e:
            test.model = name                     # restore synchronously before leaving (no finally spanning a yield)
            log.error("preproc_script_error", key=test.key, test_name=test.get_name(), preproc_path=str(preproc), exc_info=e)
            yield ("fail", TestResult.prep(test.key, test.get_name(), f"preproc script raised: {e}")); return
        test.model = name                         # restore immediately after exec — before forwarding test by reference, so the test edge carries the name string regardless of downstream timing (script's in-place mutations persist)
        yield ("test", test)                      # mutated test, name string back on the test edge
        yield ("model", model)                    # forward the resolved model edge unchanged
```

## Algorithm

1. Branch on the preproc path: `preproc = test.get_preproc_path()` (`test` is the bare `TestConfig`; spec 01b → `str | None`). If `None`, emit `("test", test)` **and** `("model", model)` once (forward **both** joined edges) and return (rtl_buddy short-circuits the same way).
2. **Expose the resolved model to the script.** Save `name = test.model` (the model-name string) and build the namespace `ns = {"logger": logger, "test_cfg": test, "root_cfg": root_cfg}`. Read the script (`with open(preproc) as f: code = f.read()`), then — **immediately before the `exec`** — set `test.model = model.value` (the resolved `ModelConfig` from the joined `model` edge) so the preproc script sees `test_cfg.model` as a `ModelConfig` — the same view rtl_buddy gives it (it resolves the model at suite-load, before `pre()`; spec [05e](05e-load-model.md), graph [06](../06-graph-yaml.md)). `exec(compile(code, preproc, "exec"), ns)` mutates `test` in place via setters (`set_plusarg`/`set_plusdefine`/`set_timeout`, spec 01b) — those mutations land on the **real** `test`, so a copy is **not** usable here (it would lose them). Restore `test.model = name` the instant the `exec` returns (on both the success path and the exec-failure clause) — the swap is live only for the `exec`, never across the forwarding `yield`s.
3. After the restore, emit `("test", test)` (the mutated test, `test.model` already back to the name string) **and** `("model", model)` (the resolved model edge, forwarded unchanged).
4. **Failure — two phases, each its own event(s).** Use **two flat (sibling, not nested) `try` blocks** — there is no outer wrapper — splitting the read from the exec so a read error and a script crash get distinct events:
   - **read** (`with open(preproc) …`) → per-exception I/O events `preproc_script_not_found` (`FileNotFoundError`), `preproc_script_permission` (`PermissionError`, `err=e.strerror`), `preproc_script_read_error` (`OSError`, `err`/`errno`) — mirrors `io.py`. The read runs **before** the `test.model` swap, so a read failure returns without any restore;
   - **exec** (`exec(compile(…), ns)`) → one broad-but-named `preproc_script_error` (`exc_info=e`): user code can raise anything, scoped to the exec alone. The swap is set immediately before this `try` and restored synchronously on **both** exits — `test.model = name` in the `except` (before the fail `yield`) and again right after the `try` on success.
   Each clause logs its own event with exception-specific fields (**not** `result`/`desc`) and emits `("fail", TestResult.prep(test.key, test.get_name(), <per-case desc>))` (**neither** `test` nor `model` — the pair drops together at the `fail` port → `results-summary`, spec [10d](10d-summarise-results.md)); the per-exception `log.error` drives the exit. Notable divergence: per-test FAIL vs rtl_buddy's `logger.critical → typer.Abort`.

## Deliverables

In `modules/rtl_buddy/build.py` (continuing from spec 03):

- `RunPreprocMod` — `(test, model, root_cfg)`, `keyed_join` over `test` + `model` by key (`model` is the `{key, value}` resolved `ModelConfig` from `load-model`, now upstream — graph [06](../06-graph-yaml.md)); `root_cfg` persistent. A **generator** (it forwards two edges). Branches on `test.get_preproc_path()` (spec [01b](01b-suite-schema.md) — returns `str | None`). If `None`, yield `("test", test)` **and** `("model", model)` once (rtl_buddy `vlog_sim.py:120-122` short-circuits the same way). Else save `name = test.model`, build `ns = {"logger": logger, "test_cfg": test, "root_cfg": root_cfg}` and read the file; then set `test.model = model.value` (expose the resolved `ModelConfig` to the script — rtl_buddy parity) immediately before `exec(compile(code, preproc, "exec"), ns)`, and restore `test.model = name` the instant the exec returns (on both the success path and the exec-failure clause — two synchronous assignments, **not** a `finally`). The script mutates `test` in place (using setters like `test_cfg.set_plusarg(k, v)`, `set_plusdefine(k, v)`, `set_timeout(t)` per spec [01b](01b-suite-schema.md)) — mutate the **real** `test`, not a copy. After the restore, yield `("test", test)` **and** `("model", model)`. Inlines the three-line read-and-`exec` directly — `expand-sweep` (spec [05f](05f-expand-sweep.md)) inlines the same lines and uses the same model-exposure swap, deliberately not shared.
  **Failure handling**: **split the read from the exec**, each with its own event(s) — the read in per-exception clauses (`preproc_script_not_found`/`preproc_script_permission`/`preproc_script_read_error`) and the `exec` in one broad-but-named `preproc_script_error` (`exc_info=e`; user code can raise anything); mirrors `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:134-137` but per-test FAIL rather than abort. Each clause logs its event with the **exception-specific** fields (**not** `result`/`desc`) and emits `("fail", TestResult.prep(test.key, test.get_name(), <per-case desc>))`. **Notable divergence from rtl_buddy**: per-test FAIL vs rtl_buddy's `logger.critical → typer.Abort`.
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
- `test` with a script that raises (e.g. `raise ValueError("boom")`) → `log.error("preproc_script_error", exc_info=…)`, emits `("fail", TestResult.prep(key, test_name, …))`, neither `test` nor `model`, `logging_handler.failure is True`, no `typer.Exit`; `test.model` is restored (the synchronous restore in the exec `except`, before the fail `yield`).
- `test` whose preproc path points at a missing file → `FileNotFoundError` reading the script → `log.error("preproc_script_not_found", preproc_path=…)`, emits `("fail", …)`, no abort (boundary: the **read** phase logs its own event, distinct from the script-crash event).

## Acceptance criteria

- Tests pass.
- All three of `test`/`model`/`fail` are exercised: the no-script path forwards both `test` and `model` unchanged, a script-set mutation is reflected on the emitted `test` (with `model` forwarded), and a raising preproc script (or read error) routes a per-test FAIL `result` and logs at ERROR.
- A preproc script reading `test_cfg.model` sees the resolved `ModelConfig` (not the name string, not an `AttributeError`), and `test.model` is the name string again after the module returns.
- The `modules/config.yaml` manifest entry `{ name: run-preproc, class_name: RunPreprocMod }` validates and the harness resolves `run-preproc` → `RunPreprocMod`.

## Constraints

- `keyed_join` over `test` + `model` by key (`model` is the `{key, value}` resolved `ModelConfig` from the now-upstream `load-model`); `root_cfg` persistent.
- No preproc configured (`get_preproc_path()` is `None`) → emit `("test", test)` **and** `("model", model)` exactly once each (forward **both** joined edges).
- Expose the resolved model to the script: save `name = test.model`, set `test.model = model.value` **immediately before** the `exec`, and restore `test.model = name` synchronously the instant the `exec` returns — once in the exec `except` (before the fail `yield`) and once right after the `try` on success. Do **not** restore in a `finally`: the swap must be live only for the `exec`, never across the forwarding `yield`s, since the `test` edge forwards the **same object by reference** and the restore must land before any downstream node can dereference it. Operate on the **real** `test` (a copy would lose the script's in-place mutations) — the script sees `test_cfg.model` as a resolved `ModelConfig` (rtl_buddy parity).
- The script mutates `test` **in place** via setters (`set_plusarg`/`set_plusdefine`/`set_timeout`); after restoring `test.model`, forward the mutated test on the `test` port **and** the resolved model on the `model` port (the original `{key, value}`, unchanged).
- Split the failure handling into **two flat (sibling) `try` blocks** — **no outer `try` wrapping them**: the **read** (per-exception: `preproc_script_not_found`/`preproc_script_permission`/`preproc_script_read_error`) and the **exec** (broad-but-named `preproc_script_error`, `exc_info=e` — user code). Each logs its event with the exception-specific fields (**not** `result`/`desc`), emits `("fail", TestResult.prep(test.key, test.get_name(), <per-case desc>))` on the `fail` port (→ `results-summary`) (and **neither** `test` nor `model`); the per-exception `log.error` drives the exit. Per-test FAIL, **not** `log.fatal`/abort. Do **not** collapse them into one `except Exception`/one event.
- Inline the read + `exec` directly (`with open(preproc) as f: code = f.read()` then `exec(compile(code, preproc, "exec"), ns)`); `expand-sweep` (spec [05f](05f-expand-sweep.md)) inlines the same three lines and uses the same `test.model` swap. Deliberately **not** a shared helper.

## Notes

`run-preproc` and `expand-sweep` (spec [05f](05f-expand-sweep.md)) run the same three-line read-and-`exec`. **Inline it at each site — do not factor it into a shared helper.** It is three trivial lines, and the two namespaces differ (preproc passes only `logger`/`test_cfg`/`root_cfg` and relies on the script's in-place mutation of `test_cfg`; sweep adds `TestConfig` + `out_test_cfgs`), so a wrapper would add a cross-file dependency between `build.py` and `setup.py` for no gain. Exceptions from the `open`/`exec` propagate into their own per-phase `try/except` — see spec [05f](05f-expand-sweep.md) Notes.

**Script model-view compatibility (resolved).** Same mechanism as `expand-sweep` (spec [05f — Notes](05f-expand-sweep.md)). The drop-in promise covers config *files*; the preproc script is *code* run against **this plan's reimplemented** `test_cfg`/`root_cfg`. The model-field delta that would otherwise break drop-in preproc scripts — rtl_buddy resolves the model at suite-load, so its `test_cfg.model` is a resolved `ModelConfig` by `pre()` time, whereas this plan carries the name string on the test edge — is **closed**: `load-model` runs upstream (graph [06](../06-graph-yaml.md)) and this module sets `test_cfg.model = model.value` for the `exec`, so the script sees the resolved `ModelConfig` rtl_buddy would present (then restores the name string). **Residual (KIV):** (1) other reimplemented-`TestConfig` surface differences are still potential deltas — validate real preproc scripts before claiming parity; (2) a preproc script that *reassigns* `test_cfg.model` has the reassignment dropped (the post-exec restore puts the name string back; the resolved `model` edge is fixed upstream). Record in [`divergences.md`](../../divergences.md) if a real script trips them.
