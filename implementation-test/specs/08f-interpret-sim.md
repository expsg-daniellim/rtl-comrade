# Spec 08f: interpret-sim (`InterpretSimMod`)

**Depends on:** spec [08d](08d-write-randseed.md) (`test_run`).
**References:** [03 — Simulation section](../03-module-catalog.md). Parent index: [idx-08 — Sim-cycle modules](../idx-08-sim-cycle.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)` signature, the allowed output forms (plain return / named-port tuple / generator), the `finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py` are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit `a69d962`). This module appends to `modules/rtl_buddy/sim.py`, which is created by spec [`08a`](08a-expand-runs.md) — append, do not overwrite. The file is shared with the sim-cycle modules (`08a`–`08f`, index [idx-08](../idx-08-sim-cycle.md)) and the post modules (`09a`–`09c`, index [idx-09](../idx-09-post.md)); coordinate shared imports and helpers with those specs.

## Goal

Route the sim result on the timeout flag — pass `test_run` through on success, emit `SimTimeoutResults` on timeout.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry — the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract: default
inputs:   test_run
outputs:  ok      → test_run
          timeout → result
```

```python
class InterpretSimMod:
    def run(self, test_run):
        if test_run["timed_out"]:
            result = SimTimeoutResults(...)
            log.error("sim_timeout", key=test_run["key"], test_name=test_run["test"].get_name(), err=test_run["err"],
                      result=result.results["result"], desc=result.results["desc"])   # → SummaryProcessor row
            return ("timeout", { "key": test_run["key"], "result": result })
        return ("ok", test_run)
```

## Algorithm

1. Branch on the timeout flag: if not `test_run["timed_out"]`, emit `("ok", test_run)`.
2. **Timeout path.** Otherwise build `result = SimTimeoutResults(...)` and `log.error("sim_timeout", key=test_run["key"], err=test_run["err"], result=..., desc=...)` — the `result`/`desc` kwargs let `SummaryProcessor`'s watch-list collect the row. Emit `("timeout", {"key": test_run["key"], "result": result})`. Routing on a flag — no Python exception is caught.

## Deliverables

In `modules/rtl_buddy/sim.py`:

- `InterpretSimMod` — `(test_run)` → pure routing: `test_run["timed_out"]` → `("timeout", {"key", "result": SimTimeoutResults()})`, else `("ok", test_run)`.
  **Failure handling**: routing on `test_run["timed_out"]`; no Python exception is caught. The ERROR `sim_timeout` log at emission of `("timeout", ...)` carries `test_run["key"]`, `test_run["err"]`, **and `result`/`desc`** from `SimTimeoutResults` so the `SummaryProcessor` watch-list ([10c](10c-summary-handler.md)) renders the row (mirrors rtl_buddy's `vlog_sim.py` timeout reporting).
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/runner/test_runner.py:72-73` — the `execute_returncode == 4444 → SimTimeoutResults` branch; sentinel set at `tools/vlog_sim.py:258-261`; `SimTimeoutResults` at `runner/test_results.py:62-69`.

**Manifest** — append to the `- file: rtl_buddy/sim.py` block in `modules/config.yaml` (opened by [`08a`](08a-expand-runs.md); append, don't re-create):

```yaml
  - { name: interpret-sim, class_name: InterpretSimMod }
```

## Tests

In `modules/tests/test_sim_cycle.py`. Fixtures: a `test_run` dict fixture; `logging_handler` for the timeout path.

- `test_run["timed_out"] == False` → emits `("ok", test_run)` unchanged; no log.
- `test_run["timed_out"] == True` → emits `("timeout", {"key", "result": SimTimeoutResults})`, `logging_handler.failure is True`, and the ERROR `sim_timeout` log carries `key`/`err`/`result="FAIL"`/`desc` (so `SummaryProcessor` collects it).
- `test_run["timed_out"] == True` with `rc == 0` → still routes `("timeout", …)` (boundary: routes on the flag, independent of `rc` — see spec 03's `timed_out`-not-derived-from-`rc`).
- `test_run["timed_out"] == False` with a non-zero `rc` → still emits `("ok", test_run)` (boundary: rc classification is `parse-log`'s job, not this node's).

## Acceptance criteria

- Tests pass.
- Both output ports (`ok`, `timeout`) are exercised: `ok` forwards `test_run` on a clean run; the `timeout` path emits `SimTimeoutResults` (the `rc=4444`/`timed_out` case) and logs at ERROR.
- The `modules/config.yaml` manifest entry `{ name: interpret-sim, class_name: InterpretSimMod }` validates and the harness resolves `interpret-sim` → `InterpretSimMod`.

## Constraints

- Route on `test_run["timed_out"]`: false → `("ok", test_run)`; true → `("timeout", {key, result: SimTimeoutResults()})` on the **unwired** `timeout` port and `log.error("sim_timeout", …)` at emission (`key`, `err` path, **and `result`/`desc`** so the `SummaryProcessor` watch-list collects the row).
- This is routing on a flag, **not** a caught Python exception.
- Use string-literal port names (`ok`/`timeout`); stay graph-agnostic.
