# Spec 07b: interpret-compile (`InterpretCompileMod`)

**Depends on:** spec 03 (run-process), spec [07a](07a-build-compile-cmd.md)
(`build-compile-cmd` sets `ctx["simv"]`).
**References:** [03 — Reusable subprocess core section](../03-module-catalog.md),
[04 — keyed_join paragraph](../04-pipeline-and-contracts.md). Parent index:
[07 — Compile-cycle modules](07-compile-cycle-modules.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)`
signature, the allowed output forms (plain return / named-port tuple / generator), the
`finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py`
are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry
below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit
`a69d962`). This module appends to `modules/rtl_test/build.py`, which is created by spec
[`06a`](06a-run-preproc.md) — append, do not overwrite. The file is shared with run-process
(`03`), the prep modules (`06a`–`06b`, index [06](06-prep-modules.md)), and the compile-cycle
modules (`07a`–`07b`, index [07](07-compile-cycle-modules.md)); coordinate shared imports and
helpers with those specs.

## Goal

Route the compile result on the subprocess rc — pass `ctx` through on success, emit
`CompileFailResults` on failure. This is one of the two `keyed_join` nodes.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry —
the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract:        keyed_join
contract_config: key_field: key
inputs:          ctx, proc   (joined by key)
outputs:         ok   → ctx
                 fail → result
```

```python
class InterpretCompileMod:
    def run(self, ctx, proc):
        if proc["rc"] == 0:
            return ("ok", ctx)   # simv already set by build-compile-cmd
        log.error("compile_failed", key=ctx["key"], rc=proc["rc"], stderr_path=proc["stderr_path"])
        return ("fail", { "key": ctx["key"], "result": CompileFailResults(...) })
```

## Algorithm

1. Branch on the subprocess result (joined to `ctx` by key via `keyed_join`): if `proc["rc"]
   == 0`, emit `("ok", ctx)` unchanged — `ctx["simv"]` was already set by `build-compile-cmd`.
2. **Failure — non-zero rc.** Otherwise read a tail of `proc["stderr_path"]`, `log.error` at
   emission with `rc`/`stderr_path`/the stderr tail, and emit `("fail", {"key": ctx["key"],
   "result": CompileFailResults(...)})`. This is result routing on `rc`, not a caught Python
   exception; an `OSError`/`FileNotFoundError` reading `stderr_path` would be surprising and is
   left to propagate.

## Deliverables

In `modules/rtl_test/build.py`:

- `InterpretCompileMod` — `(ctx, proc)`, with `keyed_join` contract on the node;
  rc == 0 → `("ok", ctx)` unchanged (`ctx["simv"]` already set by `build-compile-cmd`);
  rc != 0 → reads `proc["stderr_path"]`/`stdout_path` and logs at ERROR, then
  `("fail", {"key": ctx["key"], "result": CompileFailResults()})`.
  **Failure handling**: routing on `proc["rc"]`; no Python exception is caught here. The
  ERROR log at emission carries `rc`, `stderr_path`, and a tail of the stderr file
  (mirrors `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:170-172`). `OSError` /
  `FileNotFoundError` reading `stderr_path` would be surprising; let it propagate.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/runner/test_runner.py:63-65` — the `compile_returncode != 0 → CompileFailResults` branch; rc check at `tools/vlog_sim.py:168-171`; `CompileFailResults` at `runner/test_results.py:44-51`.

**Manifest** — append to the `- file: rtl_test/build.py` block in `modules/config.yaml`
(opened by [`06a`](06a-run-preproc.md); append, don't re-create):

```yaml
  - { name: interpret-compile, class_name: InterpretCompileMod }
```

## Tests

In `modules/tests/test_compile_cycle.py`. Fixtures: `ctx` (carrying `simv`) and `proc`
(`rc`/`stdout_path`/`stderr_path`) dicts; a `tmp_path` stderr file with known content;
`logging_handler` for the fail path. Drive `run(ctx, proc)` directly — the `keyed_join` is
the contract's concern.

- `proc["rc"] == 0` → emits `("ok", ctx)` unchanged (`ctx["simv"]` preserved); no log.
- `proc["rc"] == 2` with a stderr file → emits `("fail", {"key", "result": CompileFailResults})`,
  `logging_handler.failure is True`, and the ERROR log carries `rc`/`stderr_path`/the stderr tail.
- `proc["rc"] == -11` (signal-style non-zero) → still routes `("fail", …)` (boundary: any
  non-zero rc is a compile failure, not just positive codes).
- `proc["rc"] != 0` with `stderr_path` pointing at a missing file → reading the tail raises
  `FileNotFoundError`, which propagates uncaught → `pytest.raises(FileNotFoundError)` (boundary:
  surprising I/O error is not swallowed).

## Acceptance criteria

- Tests pass.
- Both output ports (`ok`, `fail`) are exercised; the fail path emits `CompileFailResults`
  and logs at ERROR.
- Wiring `build-compile-cmd` → `run-process` (instance #1) → `interpret-compile` (with
  `keyed_join`) end-to-end against a real builder produces a non-zero `rc` on a known
  bad source file and surfaces it correctly (see
  [07 index](07-compile-cycle-modules.md#acceptance-criteria)).

## Constraints

- `keyed_join` contract with `key_field: key` — join `ctx` + `proc` by key; this is a join
  node, not single-source `default`.
- Route on `proc["rc"]`: `rc == 0` → `("ok", ctx)` unchanged (`ctx["simv"]` already set by
  `build-compile-cmd`); `rc != 0` → `("fail", {key, result: CompileFailResults()})` on the
  **unwired** `fail` port and `log.error` at emission (`rc`, `stderr_path`, stderr tail).
- This is result routing on `rc`, **not** a caught Python exception. An `OSError`/
  `FileNotFoundError` reading `stderr_path` is surprising — let it propagate.

## Notes

`cc-int` (interpret-compile) is one of the two `keyed_join` nodes. `simv` is set by
`build-compile-cmd` and carried in `ctx` — `build-sim-cmd` reads it directly. See
[04 — keyed_join paragraph](../04-pipeline-and-contracts.md).
