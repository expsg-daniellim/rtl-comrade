# Spec 12: CompileExecute

## What this covers

Implement `CompileExecute` in `modules/rtl_buddy_compat/compile.py` (the file created by spec 11). This module runs the compile subprocess asynchronously and routes the outcome to a `success` or `failure` port.

## Prerequisites

Specs 00 and 11 (artefacts + compile.py file exists) must be complete.

## Before you start

Read:
- `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:L167-L190` — compile subprocess, return code handling, logging
- `rtl_buddy/src/rtl_buddy/runner/test_runner.py:L63-L66` — compile failure → `CompileFailResults`
- `rtl_buddy/src/rtl_buddy/runner/test_results.py:L42-L48` — `CompileFailResults` shape

**The harness runs an async event loop. Do not use `subprocess.run()` or `Popen().wait()` — they block the event loop.** Use `asyncio.create_subprocess_exec` + `await process.communicate()`.

## Addition to `modules/rtl_buddy_compat/compile.py`

### `CompileExecute`

```
contract: default
inputs:  command: CompileCommand
outputs: success → CompileResult
         failure → TestResultRow
```

`run()` must be `async`.

Implementation steps:

1. Record `start = time.monotonic()`.
2. ```python
   proc = await asyncio.create_subprocess_exec(
       *command.argv,
       cwd=command.cwd,
       stdout=asyncio.subprocess.PIPE,
       stderr=asyncio.subprocess.PIPE,
   )
   stdout_bytes, stderr_bytes = await proc.communicate()
   ```
3. On `FileNotFoundError`: `log.critical(...)` and `raise SystemExit(1)`.
4. Decode stdout/stderr as UTF-8 with `errors="replace"`.
5. `duration_seconds = time.monotonic() - start`.
6. Log return code and a stderr excerpt at appropriate level (matching `vlog_sim.py:L176-L190`).
7. `returncode == 0` → emit `("success", CompileResult(command=command, returncode=0, stdout=..., stderr=..., duration_seconds=...))`.
8. `returncode != 0` → emit `("failure", TestResultRow(key=command.run_plan.key, result="FAIL", desc="compile failed", evidence={"returncode": str(proc.returncode), "stderr": stderr[:500]}))`.

Compatibility: `vlog_sim.py:L167-L190`, `test_runner.py:L63-L66`, `test_results.py:L42-L48`.

## Register in `modules/rtl_buddy_compat/config.yaml`

Add to the existing `compile.py` entry:

```yaml
  - name: compile_execute
    class_name: CompileExecute
```

## Tests

Write `modules/rtl_buddy_compat/tests/test_compile_execute.py`.

Use real subprocesses. All tests must be `async` (`asyncio_mode = "auto"` is set in `pyproject.toml`).

- `argv=["true"]` → emits on `"success"` with `returncode=0`
- `argv=["false"]` → emits on `"failure"` with `result="FAIL"`, `desc="compile failed"`
- `argv=["__no_such_binary__"]` → `SystemExit` raised
- `CompileResult.duration_seconds` is positive
- Evidence dict in failure row contains `"returncode"` key

## Constraints

- `run()` must be `async`.
- Do not emit both `"success"` and `"failure"` for the same invocation.
- `CompileResult` must be emitted on `"success"`, not the default port.
