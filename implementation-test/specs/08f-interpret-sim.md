# Spec 08f: interpret-sim (`InterpretSimMod`)

**Depends on:** spec [08d](08d-write-randseed.md) (`test_run`).
**References:** [03 — Simulation section](../03-module-catalog.md). Parent index:
[08 — Sim-cycle modules](08-sim-cycle-modules.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)`
signature, the allowed output forms (plain return / named-port tuple / generator), the
`finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py`
are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry
below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit
`a69d962`). This module appends to `modules/rtl_test/sim.py`, shared with the sim-cycle modules
(`08a`–`08f`, index [08](08-sim-cycle-modules.md)) and the post modules (`09a`–`09c`, index
[09](09-post-modules.md)); coordinate shared imports and helpers with those specs.

## Goal

Route the sim result on the timeout flag — pass `test_run` through on success, emit
`SimTimeoutResults` on timeout.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry —
the catalog is the design view, this is the build view; update both when behaviour changes.

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
            log.error("sim_timeout", key=test_run["key"], err=test_run["err"])
            return ("timeout", { "key": test_run["key"], "result": SimTimeoutResults(...) })
        return ("ok", test_run)
```

## Deliverables

In `modules/rtl_test/sim.py`:

- `InterpretSimMod` — `(test_run)` → pure routing: `test_run["timed_out"]` →
  `("timeout", {"key", "result": SimTimeoutResults()})`, else `("ok", test_run)`.
  **Failure handling**: routing on `test_run["timed_out"]`; no Python exception is caught.
  The ERROR log at emission of `("timeout", ...)` carries `test_run["key"]`, the
  configured timeout, and `test_run["err"]` (mirrors rtl_buddy's `vlog_sim.py` timeout
  reporting).
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/runner/test_runner.py:72-73` — the `execute_returncode == 4444 → SimTimeoutResults` branch; sentinel set at `tools/vlog_sim.py:258-261`; `SimTimeoutResults` at `runner/test_results.py:62-69`.

**Manifest** — append to the `- file: rtl_test/sim.py` block in `modules/config.yaml`
(opened by [`08a`](08a-expand-runs.md); append, don't re-create):

```yaml
  - { name: interpret-sim, class_name: InterpretSimMod }
```

## Tests

In `modules/tests/test_sim_cycle.py`:

- `interpret-sim` routes timeout-vs-ok on `test_run["timed_out"]`.

## Acceptance criteria

- Tests pass.
- Both output ports (`ok`, `timeout`) are exercised; the timeout path emits
  `SimTimeoutResults` and logs at ERROR.
