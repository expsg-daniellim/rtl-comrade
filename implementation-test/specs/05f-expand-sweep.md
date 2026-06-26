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
        ns = {"logger": logger, "TestConfig": TestConfig,
              "test_cfg": test, "root_cfg": root_cfg, "out_test_cfgs": []}
        try:                                         # phase 1 — read the script: per-exception I/O events (mirrors io.py); no swap yet, so a read failure needs no restore
            with open(sweep) as f:
                code = f.read()
        except FileNotFoundError:
            log.error("sweep_script_not_found", key=test.key, test_name=test.get_name(), sweep_path=str(sweep))
            yield ("fail", TestResult.prep(test.key, test.get_name(), f"sweep script not found: {sweep}")); return
        except PermissionError as e:
            log.error("sweep_script_permission", key=test.key, test_name=test.get_name(), sweep_path=str(sweep), err=e.strerror)
            yield ("fail", TestResult.prep(test.key, test.get_name(), f"cannot read sweep script {sweep}")); return
        except OSError as e:
            log.error("sweep_script_read_error", key=test.key, test_name=test.get_name(), sweep_path=str(sweep), err=e.strerror, errno=e.errno)
            yield ("fail", TestResult.prep(test.key, test.get_name(), f"cannot read sweep script {sweep}")); return
        test.model = model.value                     # expose the resolved ModelConfig to the script as test_cfg.model (rtl_buddy parity) — live only for the exec, restored on both exits below
        try:                                         # phase 2 — exec user code: anything can raise, so one broad (but named) event
            exec(compile(code, sweep, "exec"), ns)
        except Exception as e:
            test.model = name                        # restore synchronously before leaving (no finally spanning a yield)
            log.error("sweep_script_error", key=test.key, test_name=test.get_name(), sweep_path=str(sweep), exc_info=e)
            yield ("fail", TestResult.prep(test.key, test.get_name(), f"sweep script raised: {e}")); return
        test.model = name                            # restore immediately after a successful exec — the swap only needs to be live for the exec
        try:                                         # phase 3 — fan out: malformed out_test_cfgs is its own structured failure (test.model already restored)
            for i, variant in enumerate(ns["out_test_cfgs"]):
                variant.key = f"{test.key}#{i}"      # stamp the per-variant instance identity
                variant.model = name                 # name string back on the test edge; the resolved model rides the model edge
                yield ("test", variant)              # bare TestConfig variant, self-keyed (distinct object)
                yield ("model", KeyedValue(variant.key, model.value))   # same ModelConfig, re-keyed to the variant
        except (TypeError, AttributeError, KeyError) as e:
            log.error("sweep_output_invalid", key=test.key, test_name=test.get_name(), sweep_path=str(sweep), err=str(e))
            yield ("fail", TestResult.prep(test.key, test.get_name(), f"sweep script produced malformed out_test_cfgs: {e}"))
```

## Algorithm

1. Branch on the sweep path: `sweep = test.get_sweep_path()` (`test` is the bare `TestConfig`; spec 01b → `str | None`). If `None`, yield `("test", test)` **and** `("model", model)` once (forward **both** joined edges unchanged) and return — no sweep configured.
2. **Expose the resolved model to the script.** Save `name = test.model` (the model-name string) and build the namespace `ns = {"logger": logger, "TestConfig": TestConfig, "test_cfg": test, "root_cfg": root_cfg, "out_test_cfgs": []}` (matches rtl_buddy's namespace). Read the script (`with open(sweep) as f: code = f.read()`), then — **immediately before the `exec`** — set `test.model = model.value` (the resolved `ModelConfig` from the joined `model` edge) so the sweep script sees `test_cfg.model` as a `ModelConfig` — the same view rtl_buddy gives it (rtl_buddy resolves the model at suite-load, before sweep; spec [05e](05e-load-model.md), graph [06](../06-graph-yaml.md)). This is a temporary state of the **real** `test` object (not a copy) — identical to what rtl_buddy's `_expand_tests_with_sweep` passes. `exec(compile(code, sweep, "exec"), ns)` populates `ns["out_test_cfgs"]`, then `test.model = name` restores the name string the instant the `exec` returns (on both the success path and the exec-failure clause) — the swap is live only for the `exec`, never across the fan-out.
3. Fan out: for each variant `TestConfig` accumulated in `ns["out_test_cfgs"]`, stamp `variant.key = f"{test.key}#{i}"`, restore `variant.model = name` (the name string — the resolved `ModelConfig` rides the `model` edge, not the test object), and yield both `("test", variant)` (the bare variant, self-keyed) **and** `("model", KeyedValue(variant.key, model.value))` (the same resolved `ModelConfig`, re-keyed to the variant). Each variant is a distinct object, so stamping in place is sound — no copy needed (contrast `expand-runs`, which shares one object across runs). All variants inherit the parent test's one resolved model (sweep does not re-resolve — matching rtl_buddy, where the model is fixed before the script runs).
4. **Failure — three phases, each its own event(s).** Use **three flat (sibling, not nested) `try` blocks**, one per phase, so a read error, a script crash, and malformed output are never conflated — there is no outer wrapper:
   - **read** (`with open(sweep) …`) → per-exception I/O events `sweep_script_not_found` (`FileNotFoundError`), `sweep_script_permission` (`PermissionError`, `err=e.strerror`), `sweep_script_read_error` (`OSError`, `err`/`errno`) — mirrors `io.py`. The read runs **before** the `test.model` swap, so a read failure returns without any restore;
   - **exec** (`exec(compile(…), ns)`) → one broad-but-named `sweep_script_error` (`exc_info=e`): user code can raise anything, so a broad `except Exception` is honest here, but it is **scoped to the exec alone**. The swap is set immediately before this `try` and restored synchronously on **both** exits — `test.model = name` in the `except` (before the fail `yield`) and again right after the `try` on success;
   - **fan-out** (the loop over `ns["out_test_cfgs"]`) → `sweep_output_invalid` (`TypeError` if non-iterable, `AttributeError` if a variant rejects `.key`, `KeyError` if `out_test_cfgs` was deleted; `err=str(e)`). Runs with `test.model` already restored, so it guards no swap.
   Each clause logs its own event with the exception-specific fields (**not** `result`/`desc`) and emits `("fail", TestResult.prep(test.key, test.get_name(), <per-case desc>))` (**neither** `test` nor `model` — the pair drops together at the `fail` port → `results-summary`, spec [10d](10d-summarise-results.md)); the per-exception `log.error` drives the exit. Notable divergence: per-test FAIL vs rtl_buddy's `logger.critical → typer.Abort`.

## Deliverables

In `modules/rtl_buddy/setup.py` (continuing from spec 04):

- `ExpandSweepMod` — `(test, model, root_cfg)`, `keyed_join` over `test` + `model` by key (`model` is the `{key, value}` resolved `ModelConfig` from `load-model`, now upstream — graph [06](../06-graph-yaml.md)); `root_cfg` persistent. `test` is the bare self-keyed `TestConfig`. Branches on `test.get_sweep_path()` (spec [01b](01b-suite-schema.md) — returns `str | None`). If `None`, yield `("test", test)` **and** `("model", model)` once (forward both). Else save `name = test.model`, build `ns = {"logger": logger, "TestConfig": TestConfig, "test_cfg": test, "root_cfg": root_cfg, "out_test_cfgs": []}` and read the file at that path; then set `test.model = model.value` (expose the resolved `ModelConfig` to the script — rtl_buddy parity) immediately before `exec(code, ns)`, and restore `test.model = name` the instant the exec returns (on both the success path and the exec-failure clause — two synchronous assignments, **not** a `finally`). After the exec, for each `variant` in `ns["out_test_cfgs"]` stamp `variant.key = f"{test.key}#{i}"`, set `variant.model = name`, and yield `("test", variant)` **and** `("model", KeyedValue(variant.key, model.value))` (key suffixed `#i`).
  **Failure handling**: **split by phase**, each with its own event(s) — the read in per-exception clauses (`sweep_script_not_found`/`sweep_script_permission`/`sweep_script_read_error`), the `exec` in one broad-but-named `sweep_script_error` (`exc_info=e`; user code can raise anything), and the fan-out loop in `(TypeError, AttributeError, KeyError)` → `sweep_output_invalid` (malformed `out_test_cfgs`); mirrors `rtl_buddy/src/rtl_buddy/rtl_buddy.py:279-281` but per-test FAIL rather than abort. Each clause logs its event with the **exception-specific** fields (**not** `result`/`desc`) and emits `("fail", TestResult.prep(test.key, test.get_name(), <per-case desc>))`. The module catches **every** exception its own code can raise per `docs/modules/implementation.md` ("Exception Handling Is The Module's Responsibility"); read / exec / fan-out are all its code, each **scoped to its own guard** so the event matches the phase. **Notable divergence from rtl_buddy**: per-test FAIL vs rtl_buddy's `logger.critical → typer.Abort`.
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
- `test` with a sweep script that raises (e.g. `raise RuntimeError("boom")`) → `log.error("sweep_script_error", exc_info=…)`, yields `("fail", TestResult.prep(key, test_name, …))`, neither `test` nor `model`, `logging_handler.failure is True`, no `typer.Exit`; `test.model` is restored (the synchronous restore in the exec `except`, before the fail `yield`).
- `test` whose sweep path points at a missing file → `FileNotFoundError` reading the script → `log.error("sweep_script_not_found", sweep_path=…)`, yields `("fail", …)`, no abort (boundary: the **read** phase logs its own event, distinct from the script-crash event).
- `test` with a sweep script that leaves `out_test_cfgs` empty → yields nothing on `test`/`model` (boundary: zero-variant fan-out).
- `test` with a sweep script that sets `out_test_cfgs` to a non-iterable (e.g. an `int`), or appends an object that rejects `.key` assignment → the **fan-out** phase raises `TypeError`/`AttributeError` → `log.error("sweep_output_invalid", err=…)`, yields `("fail", TestResult.prep(key, test_name, …))`, no abort (boundary: malformed output is its own event, distinct from a script crash; not bubbled to the harness).

## Acceptance criteria

- Tests pass.
- All three non-fail/fail ports are exercised: a sweep script multiplies one fixture test by 4 (one `test` edge **and** one re-keyed `model` edge per variant, key suffixed `#i`); a raising sweep script routes a per-test FAIL `result` and logs at ERROR.
- A sweep script reading `test_cfg.model` sees the resolved `ModelConfig` (not the name string, not an `AttributeError`), and `test.model` is the name string again after the module returns.
- The `modules/config.yaml` manifest entry `{ name: expand-sweep, class_name: ExpandSweepMod }` validates and the harness resolves `expand-sweep` → `ExpandSweepMod`.

## Constraints

- `keyed_join` over `test` + `model` by key (`model` is the `{key, value}` resolved `ModelConfig` from `load-model`, now positioned upstream of this node); `root_cfg` persistent.
- No sweep configured (`get_sweep_path()` is `None`) → yield `("test", test)` **and** `("model", model)` exactly once each (forward **both** joined edges).
- Expose the resolved model to the script: save `name = test.model`, set `test.model = model.value` **immediately before** the `exec`, and restore `test.model = name` synchronously the instant the `exec` returns — once in the exec `except` (before the fail `yield`) and once right after the `try` on success. Do **not** restore in a `finally` wrapping the body: the swap must be live only for the `exec`, never across the fan-out yields, and the restore must not be deferred to generator drain. The script sees `test_cfg.model` as a resolved `ModelConfig` (rtl_buddy parity), not a name string. Operate on the **real** `test` object, not a copy (matches rtl_buddy's `_expand_tests_with_sweep`).
- Fan out per `TestConfig` in `ns["out_test_cfgs"]`: stamp `variant.key = f"{test.key}#{i}"`, set `variant.model = name` (name string on the test edge), and yield `("test", variant)` **and** `("model", KeyedValue(variant.key, model.value))` (the same resolved model, re-keyed; bare self-keyed variant, each a distinct object). All variants share the parent's resolved model.
- Split the failure handling **by phase** into **three flat (sibling) `try` blocks**, each its own event — **no outer `try` wrapping them**: read → `sweep_script_not_found`/`sweep_script_permission`/`sweep_script_read_error`; `exec` → `sweep_script_error` (broad, `exc_info=e` — user code); fan-out → `sweep_output_invalid` (`TypeError`/`AttributeError`/`KeyError`). Each logs its event with exception-specific fields (**not** `result`/`desc`), emits `("fail", TestResult.prep(test.key, test.get_name(), <per-case desc>))` on the `fail` port (→ `results-summary`) (and **neither** `test` nor `model`); the per-exception `log.error` drives the exit. Per-test FAIL, **not** `log.fatal`/abort (divergence from rtl_buddy's `typer.Abort`). Do **not** collapse the phases into one `except Exception`/one event.
- Inline the read + `exec` directly (`with open(sweep) as f: code = f.read()` then `exec(compile(code, sweep, "exec"), ns)`); `run-preproc` (spec [06a](06a-run-preproc.md)) inlines the same three lines independently. The pattern is deliberately **not** abstracted into a shared helper.

## Notes

`expand-sweep` and `run-preproc` (spec [06a](06a-run-preproc.md)) run the same three-line read-and-`exec` (`with open(path) as f: code = f.read()` then `exec(compile(code, path, "exec"), ns)`). **Inline it at each site — do not factor it into a shared helper.** It is three trivial lines, and the two call sites build different namespaces anyway (sweep adds `TestConfig` + an `out_test_cfgs` list it reads back out; preproc passes only `logger`/`test_cfg`/`root_cfg` and relies on in-place `test_cfg` mutation), so a wrapper would buy nothing over the literal lines while adding a cross-file dependency between `setup.py` and `build.py`.

- **Partial emission on a malformed variant.** Because the `yield`s run inside the loop (not after a materialised list), a script that yields some good variants then a bad one — e.g. `out_test_cfgs = [good0, good1, 5]` — emits the `("test", good0)`/`("model", …)` and `("test", good1)`/`("model", …)` pairs before the `5.key = …` `AttributeError` routes `("fail", …)`. This is accepted: a single inline loop is the chosen shape (no list materialisation, no second loop), and the common cases stay clean — a raising script and a non-iterable `out_test_cfgs` both fail *before* any `test` edge is emitted.
- **Script model-view compatibility (resolved).** The `exec` namespace injects **this plan's reimplemented** `TestConfig`/`root_cfg`, not rtl_buddy's. The one model-field delta that used to break drop-in sweep scripts — rtl_buddy resolves the model at suite-load, so its `test_cfg.model` is a resolved `ModelConfig` by sweep time, whereas this plan keeps the name string on the test edge — is **closed** here: `load-model` runs upstream (graph [06](../06-graph-yaml.md)), and the module sets `test_cfg.model = model.value` for the duration of the `exec` so the script sees exactly the resolved `ModelConfig` rtl_buddy would present (then restores the name string on the test edge). This is why `load-model` was moved ahead of the hooks. **Residual (KIV):** (1) other reimplemented-`TestConfig` surface differences (method/attribute shapes) are still potential deltas — validate real sweep scripts against the reimplemented `TestConfig` before claiming parity; (2) a sweep script that *reassigns* `test_cfg.model` to a different `ModelConfig` has that reassignment dropped (the post-exec restore puts the name string back and the resolved `model` edge is fixed upstream) — in rtl_buddy such a reassignment could change what compiles. Both are narrow; record in [`divergences.md`](../../divergences.md) if a real script trips them. `run-preproc` (spec [06a](06a-run-preproc.md)) uses the same model-exposure mechanism.
