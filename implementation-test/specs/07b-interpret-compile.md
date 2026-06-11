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
`a69d962`). This module appends to `modules/rtl_test/build.py`, shared with run-process (`03`),
the prep modules (`06a`–`06b`, index [06](06-prep-modules.md)), and the compile-cycle modules
(`07a`–`07b`, index [07](07-compile-cycle-modules.md)); coordinate shared imports and helpers
with those specs.

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

In `modules/tests/test_compile_cycle.py`:

- `interpret-compile` ok-path passes ctx through.
- `interpret-compile` fail-path emits `CompileFailResults` and an ERROR-level log entry
  with stderr content.

## Acceptance criteria

- Tests pass.
- Both output ports (`ok`, `fail`) are exercised; the fail path emits `CompileFailResults`
  and logs at ERROR.
- Wiring `build-compile-cmd` → `run-process` (instance #1) → `interpret-compile` (with
  `keyed_join`) end-to-end against a real builder produces a non-zero `rc` on a known
  bad source file and surfaces it correctly (see
  [07 index](07-compile-cycle-modules.md#acceptance-criteria)).

## Notes

`cc-int` (interpret-compile) is one of the two `keyed_join` nodes. `simv` is set by
`build-compile-cmd` and carried in `ctx` — `build-sim-cmd` reads it directly. See
[04 — keyed_join paragraph](../04-pipeline-and-contracts.md).
