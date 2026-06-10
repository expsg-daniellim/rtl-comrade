# Spec 08f: interpret-sim (`InterpretSimMod`)

**Depends on:** spec [08d](08d-write-randseed.md) (`test_run`).
**References:** [03 — Simulation section](../03-module-catalog.md). Parent index:
[08 — Sim-cycle modules](08-sim-cycle-modules.md).

## Goal

Route the sim result on the timeout flag — pass `test_run` through on success, emit
`SimTimeoutResults` on timeout.

## Deliverables

In `modules/rtl_test/sim.py`:

- `InterpretSimMod` — `(test_run)` → pure routing: `test_run["timed_out"]` →
  `("timeout", {"key", "result": SimTimeoutResults()})`, else `("ok", test_run)`.
  **Failure handling**: routing on `test_run["timed_out"]`; no Python exception is caught.
  The ERROR log at emission of `("timeout", ...)` carries `test_run["key"]`, the
  configured timeout, and `test_run["err"]` (mirrors rtl_buddy's `vlog_sim.py` timeout
  reporting).
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/runner/test_runner.py:72-73` — the `execute_returncode == 4444 → SimTimeoutResults` branch; sentinel set at `tools/vlog_sim.py:258-261`; `SimTimeoutResults` at `runner/test_results.py:62-69`.

Manifest entries per [06](../06-graph-yaml.md).

## Tests

In `modules/tests/test_sim_cycle.py`:

- `interpret-sim` routes timeout-vs-ok on `test_run["timed_out"]`.

## Acceptance criteria

- Tests pass.
- Both output ports (`ok`, `timeout`) are exercised; the timeout path emits
  `SimTimeoutResults` and logs at ERROR.
