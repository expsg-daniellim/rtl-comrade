# Spec 07b: interpret-compile (`InterpretCompileMod`)

**Depends on:** spec 03 (run-process), spec [07a](07a-build-compile-cmd.md) (`build-compile-cmd` emits the `simv` edge).
**References:** [03 — Reusable subprocess core section](../03-module-catalog.md), [04 — keyed_join paragraph](../04-pipeline-and-contracts.md). Parent index: [idx-07 — Compile-cycle modules](../idx-07-compile-cycle.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)` signature, the allowed output forms (plain return / named-port tuple / generator), the `finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py` are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit `a69d962`). This module appends to `modules/rtl_buddy/build.py`, which is created by spec [`06a`](06a-run-preproc.md) — append, do not overwrite. The file is shared with run-process (`03`), the prep modules (`06a`–`06b`, index [idx-06](../idx-06-prep.md)), and the compile-cycle modules (`07a`–`07b`, index [idx-07](../idx-07-compile-cycle.md)); coordinate shared imports and helpers with those specs.

## Goal

Route the compile result on the subprocess rc — forward `test`+`simv` on success, emit `CompileFailResults` on failure. This is one of the two `keyed_join` nodes.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry — the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract:        keyed_join
contract_config: key_field: key
inputs:          test, simv, proc   (joined by key)
outputs:         test → {key, value}   (forwarded on compile success)
                 simv → {key, value}   (forwarded on compile success — co-gated with test)
                 fail → {key, result}
```

```python
class InterpretCompileMod:
    def run(self, test, simv, proc):
        if proc["rc"] == 0:
            yield ("test", test)   # forward test + simv together on success (co-gating)
            yield ("simv", simv)
            return
        result = CompileFailResults()   # desc is the fixed 'Compile failed' (rtl_buddy parity); rc/stderr go on the log, not in desc
        log.error("compile_failed", key=test["key"], test_name=test["value"].get_name(), rc=proc["rc"], stderr_path=proc["stderr_path"],
                  result=result.results["result"], desc=result.results["desc"])   # → SummaryProcessor row
        yield ("fail", { "key": test["key"], "result": result })
```

## Algorithm

1. Branch on the subprocess result (`test`, `simv`, `proc` joined by key via `keyed_join`): if `proc["rc"] == 0`, forward both `("test", test)` and `("simv", simv)` unchanged. The `simv` edge is **co-gated** here: it passes through interpret-compile only on success, so on a compile failure neither `test` nor `simv` proceeds and the downstream `expand-runs` join cannot dangle (design-doc co-gating rule).
2. **Failure — non-zero rc.** Otherwise build `result = CompileFailResults()` — its `desc` is the fixed `'Compile failed'` (rtl_buddy `runner/test_results.py:44-51`), **not** spliced from stderr — then `log.error("compile_failed", …)` at emission with `rc`/`stderr_path` (optionally a stderr tail as a **log** field for debugging) **plus `result`/`desc`** (so `SummaryProcessor`'s watch-list collects the row), and emit `("fail", {"key": test["key"], "result": result})` — `test`/`simv` are dropped. This is result routing on `rc`, not a caught Python exception; an `OSError`/`FileNotFoundError` reading `stderr_path` would be surprising and is left to propagate.

## Deliverables

In `modules/rtl_buddy/build.py`:

- `InterpretCompileMod` — `(test, simv, proc)`, `keyed_join` joining the three by key; rc == 0 → forward `("test", test)` then `("simv", simv)` (co-gated); rc != 0 → reads `proc["stderr_path"]`/`stdout_path` and logs at ERROR, then `("fail", {"key": test["key"], "result": CompileFailResults()})` (`test`/`simv` dropped).
  **Failure handling**: routing on `proc["rc"]`; no Python exception is caught here. `CompileFailResults`'s `desc` is the fixed `'Compile failed'` (rtl_buddy `runner/test_results.py:44-51`) — it is **not** derived from stderr. The ERROR `compile_failed` log at emission carries `rc`, `stderr_path`, optionally a stderr tail as a log field (rtl_buddy logs the full stderr/stdout dump at `tools/vlog_sim.py:170-172`; a bounded tail is acceptable here), **and `result`/`desc`** from `CompileFailResults` so the `SummaryProcessor` watch-list ([10c](10c-summary-handler.md)) renders the row. `OSError` / `FileNotFoundError` reading `stderr_path` would be surprising; let it propagate.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/runner/test_runner.py:63-65` — the `compile_returncode != 0 → CompileFailResults` branch; rc check at `tools/vlog_sim.py:168-171`; `CompileFailResults` at `runner/test_results.py:44-51`.

**Manifest** — append to the `- file: rtl_buddy/build.py` block in `modules/config.yaml` (opened by [`06a`](06a-run-preproc.md); append, don't re-create):

```yaml
  - { name: interpret-compile, class_name: InterpretCompileMod }
```

## Tests

In `modules/tests/test_compile_cycle.py`. Fixtures: `test` (`{key, value}`), `simv` (`{key, value}`), and `proc` (`{key, rc, stdout_path, stderr_path}`) edge dicts; a `tmp_path` stderr file with known content; `logging_handler` for the fail path. Drive `run(test, simv, proc)` directly — the `keyed_join` is the contract's concern.

- `proc["rc"] == 0` → emits `("test", test)` then `("simv", simv)` unchanged; no log.
- `proc["rc"] == 2` with a stderr file → emits `("fail", {"key", "result": CompileFailResults})` (no `test`/`simv`), `logging_handler.failure is True`, and the ERROR `compile_failed` log carries `rc`/`stderr_path`/the stderr tail **and `result="FAIL"`/`desc`** (so `SummaryProcessor` collects it).
- `proc["rc"] == -11` (signal-style non-zero) → still routes `("fail", …)` (boundary: any non-zero rc is a compile failure, not just positive codes).
- `proc["rc"] != 0` with `stderr_path` pointing at a missing file → reading the tail raises `FileNotFoundError`, which propagates uncaught → `pytest.raises(FileNotFoundError)` (boundary: surprising I/O error is not swallowed).

## Acceptance criteria

- Tests pass.
- All output ports (`test`, `simv`, `fail`) are exercised: on a zero `rc`, `test` and `simv` are forwarded together; the `fail` path emits `CompileFailResults` and logs at ERROR on a non-zero `rc` (dropping `test`/`simv`).
- Wiring `build-compile-cmd` → `run-process` (instance #1) → `interpret-compile` (with `keyed_join`) end-to-end against a real builder produces a non-zero `rc` on a known bad source file and surfaces it correctly.
- The `modules/config.yaml` manifest entry `{ name: interpret-compile, class_name: InterpretCompileMod }` validates and the harness resolves `interpret-compile` → `InterpretCompileMod`.

## Constraints

- `keyed_join` contract with `key_field: key` — join `test` + `simv` + `proc` by key; this is a join node, not single-source `default`.
- Route on `proc["rc"]`: `rc == 0` → forward `("test", test)` then `("simv", simv)` (co-gate `simv` through success so the `expand-runs` join can't dangle); `rc != 0` → `("fail", {key, result: CompileFailResults()})` on the **unwired** `fail` port (dropping `test`/`simv`) and `log.error("compile_failed", …)` at emission (`rc`, `stderr_path`, optional stderr tail, **and `result`/`desc`** so the `SummaryProcessor` watch-list collects the row). `CompileFailResults`'s `desc` is the fixed `'Compile failed'` — never splice stderr/`rc` into `desc`; they belong on the `log.error` only.
- This is result routing on `rc`, **not** a caught Python exception. An `OSError`/ `FileNotFoundError` reading `stderr_path` is surprising — let it propagate.

## Notes

`interpret-compile` joins `test` + `simv` + `proc`. The `simv` edge is born at `build-compile-cmd` and **co-gated** through here on compile success — `build-sim-cmd` joins it (along with `test`/`run_id`/`seed`) downstream of `expand-runs`. See [04 — keyed_join paragraph](../04-pipeline-and-contracts.md).
