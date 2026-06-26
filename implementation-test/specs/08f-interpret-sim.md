# Spec 08f: interpret-sim (`InterpretSimMod`)

**Depends on:** spec [08c](08c-build-sim-cmd.md) (forwards `test`), spec 03 (run-process — `proc`).
**References:** [03 — Simulation section](../03-module-catalog.md). Parent index: [idx-08 — Sim-cycle modules](../idx-08-sim-cycle.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)` signature, the allowed output forms (plain return / named-port tuple / generator), the `finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py` are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit `a69d962`). This module appends to `modules/rtl_buddy/sim.py`, which is created by spec [`08a`](08a-expand-runs.md) — append, do not overwrite. The file is shared with the sim-cycle modules (`08a`–`08f`, index [idx-08](../idx-08-sim-cycle.md)) and the post modules (`09a`–`09c`, index [idx-09](../idx-09-post.md)); coordinate shared imports and helpers with those specs.

## Goal

Route the sim result on the timeout indicator (`proc.rc is None`) — forward `test`+`proc` on success, emit a `TestResult.sim_timeout` on timeout.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry — the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract:        keyed_join
contract_config: key_field: key
inputs:          test, proc   (joined by key)
outputs:         test    → TestConfig (self-keyed)   (forwarded on a clean run, co-gated with proc)
                 proc    → {key, rc, stdout_path, stderr_path}   (forwarded on a clean run)
                 timeout → TestResult (self-keyed)
```

```python
class InterpretSimMod:
    def run(self, test:TestConfig, proc:Proc):
        if proc.rc is None:   # the run-process timeout indicator
            result = TestResult.sim_timeout(test.key, test.get_name())   # desc is the fixed 'Sim hit timeout' (rtl_buddy parity); stderr_path goes on the log
            log.error("sim_timeout", key=test.key, test_name=test.get_name(), err=str(proc.stderr_path))   # rich domain context, no result/desc; drives the exit. TestResult → results-summary
            yield ("timeout", result)
        else:
            yield ("test", test)    # forward test + proc on a clean run (co-gated for route-post/parse)
            yield ("proc", proc)
```

## Algorithm

1. Branch on the timeout indicator: if `proc.rc is not None`, forward both `("test", test)` and `("proc", proc)` (co-gated — the classification chain downstream needs `test` for identity and `proc` for the log path).
2. **Timeout path.** Otherwise (`proc.rc is None`) build `result = TestResult.sim_timeout(test.key, test.get_name())` — a self-keyed `TestResult` (`type_=SIM_TIMEOUT`) whose `desc` is the fixed `'Sim hit timeout'` (rtl_buddy `runner/test_results.py:62-69`), not derived from stderr — and `log.error("sim_timeout", key=test.key, err=proc.stderr_path)`; the `log.error` drives the exit, and the emitted `TestResult` → `results-summary` (spec [10d](10d-summarise-results.md)). Emit `("timeout", result)` (dropping `test`/`proc`). Routing on the `rc is None` test — no Python exception is caught.

## Deliverables

In `modules/rtl_buddy/sim.py`:

- `InterpretSimMod` — `(test, proc)`, `keyed_join` → pure routing on `proc.rc is None`: true → `("timeout", TestResult.sim_timeout(test.key, test.get_name()))`; false → forward `("test", test)` then `("proc", proc)` (co-gated for the classification chain).
  **Failure handling**: routing on `proc.rc is None`; no Python exception is caught. The ERROR `sim_timeout` log at emission of `("timeout", ...)` carries `test.key` and `proc.stderr_path` (rich domain context, **no** `result`/`desc` — the fixed verdict/desc are implied by the event); the emitted `TestResult` → `results-summary` (spec [10d](10d-summarise-results.md)) (mirrors rtl_buddy's `vlog_sim.py` timeout reporting).
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/runner/test_runner.py:72-73` — the `execute_returncode == 4444 → SimTimeoutResults` branch; rtl_buddy's `4444` sentinel is set at `tools/vlog_sim.py:258-261` (this plan reads `proc.rc is None` instead); `SimTimeoutResults` at `runner/test_results.py:62-69`.

**Manifest** — append to the `- file: rtl_buddy/sim.py` block in `modules/config.yaml` (opened by [`08a`](08a-expand-runs.md); append, don't re-create):

```yaml
  - { name: interpret-sim, class_name: InterpretSimMod }
```

## Tests

In `modules/tests/test_sim_cycle.py`. Fixtures: `test` (`{key, value}`) and `proc` (`{key, rc, stdout_path, stderr_path}`) dict fixtures; `logging_handler` for the timeout path. Drive `run(test, proc)` directly.

- `proc.rc == 0` → emits `("test", test)` then `("proc", proc)`; no log.
- `proc.rc is None` → emits `("timeout", TestResult.sim_timeout(key, test_name))` (no `test`/`proc`), `logging_handler.failure is True`, and the ERROR `sim_timeout` log carries `key`/`err` (no `result`/`desc`); the emitted `TestResult` → `results-summary`.
- `proc.rc` non-zero (and not `None`) → still forwards `test`+`proc` (boundary: any `int` rc is ordinary data — classification is `parse-log`'s job, not this node's).

## Acceptance criteria

- Tests pass.
- All output ports (`test`, `proc`, `timeout`) are exercised: on a clean run `test`+`proc` are forwarded together; the `timeout` path emits a `TestResult.sim_timeout(...)` `TestResult` (the `rc is None` case) and logs at ERROR (dropping `test`/`proc`).
- The `modules/config.yaml` manifest entry `{ name: interpret-sim, class_name: InterpretSimMod }` validates and the harness resolves `interpret-sim` → `InterpretSimMod`.

## Constraints

- `keyed_join` over `test`+`proc` (key_field `key`). Route on `proc.rc is None`: not-None → forward `("test", test)` then `("proc", proc)` (co-gate both for the classification chain); None → `("timeout", TestResult.sim_timeout(test.key, test.get_name()))` on the `timeout` port (→ `results-summary`) (dropping `test`/`proc`) and `log.error("sim_timeout", …)` at emission (`key`, `proc.stderr_path`; **no** `result`/`desc`); the emitted `TestResult` → `results-summary`. The result's `desc` is the fixed `'Sim hit timeout'` — never splice `stderr_path` into `desc`; it belongs on the `log.error` only.
- This is routing on `proc.rc is None`, **not** a caught Python exception.
- Use string-literal port names (`test`/`proc`/`timeout`); stay graph-agnostic.
