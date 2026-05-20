# Spec 16: SimExecute + SimArtifactLink

## What this covers

Implement `SimExecute` and `SimArtifactLink` in `modules/rtl_buddy_compat/sim.py` (the file created by spec 13). `SimExecute` runs the simulator asynchronously with timeout handling. `SimArtifactLink` is a small follow-up that creates the `test.*` compatibility symlinks — kept together because it has no independent test scenarios worth a separate session.

## Prerequisites

Specs 00 and 13 (artefacts + sim.py file exists) must be complete.

## Before you start

Read:
- `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:L26-L31` — `force_symlink()` helper
- `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:L264-L285` — simulation execution, timeout, randseed write, symlinks
- `rtl_buddy/src/rtl_buddy/runner/test_runner.py:L72-L75` — timeout → `SimTimeoutResults`
- `rtl_buddy/src/rtl_buddy/runner/test_results.py:L59-L66` — timeout result shape

**The harness runs an async event loop. Do not use blocking subprocess calls.** Use `asyncio.create_subprocess_exec` with file handle redirection and `asyncio.wait_for(process.wait(), timeout=...)`.

## Additions to `modules/rtl_buddy_compat/sim.py`

### `SimExecute`

```
contract: default
inputs:  command: SimCommand
outputs: success_or_failure → SimResult
         timeout → TestResultRow
```

`run()` must be `async`.

Implementation steps:

1. Create parent dirs if needed. Open `<command.log_path_prefix>.err` and `<command.log_path_prefix>.log` for writing.
2. `start = time.monotonic()`.
3. ```python
   proc = await asyncio.create_subprocess_exec(
       *command.argv,
       cwd=command.cwd,
       stdout=log_fh,
       stderr=err_fh,
   )
   ```
4. ```python
   try:
       await asyncio.wait_for(proc.wait(), timeout=command.timeout_seconds)
   except asyncio.TimeoutError:
       proc.kill()
       await proc.wait()
       # fall through to timeout emit
   ```
5. Close file handles.
6. Write `<command.log_path_prefix>.randseed` with the seed on its own line.
7. On timeout: emit `("timeout", TestResultRow(key=command.key, result="FAIL", desc="Sim hit timeout", evidence={"timeout_seconds": str(command.timeout_seconds)}))`.
8. On completion: emit `("success_or_failure", SimResult(command=command, returncode=proc.returncode, duration_seconds=time.monotonic()-start))`.

Non-zero return code still goes to `"success_or_failure"` — the log parser determines pass/fail from the log content.

Compatibility: `vlog_sim.py:L264-L285`, `test_runner.py:L72-L75`.

---

### `SimArtifactLink`

```
contract: default
inputs:  sim_result: SimResult
outputs: default → LinkedSimArtifacts
```

Implementation steps:

1. `prefix = sim_result.command.log_path_prefix`
2. `base_dir = os.path.dirname(prefix)`
3. For each suffix in `[".log", ".err", ".randseed"]`:
   - `target = prefix + suffix`
   - `link = os.path.join(base_dir, "test" + suffix)`
   - Remove `link` if it exists (symlink or file).
   - `os.symlink(target, link)`.
4. Emit `LinkedSimArtifacts(sim_result=sim_result, log_path=prefix+".log", err_path=prefix+".err", randseed_path=prefix+".randseed")`.

Compatibility: `vlog_sim.py:L26-L31, L277-L279`.

## Register in `modules/rtl_buddy_compat/config.yaml`

Add to the existing `sim.py` entry:

```yaml
  - name: sim_execute
    class_name: SimExecute
  - name: sim_artifact_link
    class_name: SimArtifactLink
```

## Tests

Write `modules/rtl_buddy_compat/tests/test_sim_execute.py`. All tests must be `async`.

Use real subprocesses: `["sleep", "0"]` (success), `["false"]` (nonzero exit), `["sleep", "100"]` with `timeout_seconds=0` (timeout).

**`SimExecute`**:
- Process completes → emits `"success_or_failure"` with correct `returncode`
- Non-zero exit (no timeout) → emits `"success_or_failure"`, not `"timeout"`
- Timeout → emits `"timeout"` with `result="FAIL"` and `desc="Sim hit timeout"`
- `.log`, `.err`, `.randseed` files created at expected paths
- `.randseed` contains the seed value from `command.seed`

**`SimArtifactLink`** (requires `tmp_path`):
- `test.log`, `test.err`, `test.randseed` symlinks created
- Symlinks point at run-specific files (e.g. `test_0000.log`)
- Second run replaces existing symlinks without error

## Constraints

- `SimExecute.run()` must be `async`.
- Non-timeout non-zero return codes must emit on `"success_or_failure"`.
- `.randseed` must be written after process completion, including after timeout.
- `SimArtifactLink` must handle pre-existing symlinks or files without raising.
