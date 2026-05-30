# Spec 03: `run-process` module

**Depends on:** spec 00.
**References:** [03 — `run-process`](../03-module-catalog.md), [07 settled 4 / open verify 23](../07-ambiguities-and-assumptions.md).

## Goal

The generic async subprocess runner used by both compile and sim cycles. Redirects
stdout/stderr to caller-supplied files; carries an opaque correlation key for downstream
joining; enforces an optional timeout via SIGQUIT to the process group with the rtl_buddy
`rc=4444` sentinel.

## Deliverables

- `modules/rtl_test/build.py::RunProcessMod` per the sketch in [03](../03-module-catalog.md).
- `modules/tests/test_run_process.py` covering:
  - normal exit (rc 0) → output dict has correct `rc`, `timed_out=False`, files contain
    expected stdout/stderr.
  - non-zero rc → propagated; no exception raised by the module.
  - timeout path → SIGQUIT delivered, `rc=4444`, `timed_out=True`, **partial stdout
    written by the child before the kill is present in the output file** (this is the
    motivating reason for the redirect change).
  - opaque key passthrough — output `key` equals input `command["key"]`.
  - emits paths in `proc`, not open file handles.
- Pre-pending `.` to `$PATH` for CWD-local simulator discovery — either inside the module
  or as part of spec 04's setup (decide one place; document).

## Acceptance criteria

- All tests pass.
- A probe with a 1-second sleep child and a 100ms timeout confirms partial output capture
  and clean process-group cleanup.
- SIGINT (Ctrl-C) at the harness level cancels the subprocess cleanly without leaving
  zombies.

## Notes

This is the workhorse — both compile and sim are wired instances of this single module.
Async subprocess corner cases (signals, process-group lifetime, race conditions between
`wait_for` cancellation and `communicate`) need attention; the [03](../03-module-catalog.md)
sketch is illustrative, not final. The redirect (rather than `PIPE`+`communicate`) is the
non-negotiable design point.
