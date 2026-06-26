# Spec 03: `run-process` module

**Depends on:** spec 06a (creates the shared `modules/rtl_buddy/build.py` that 03 appends to — file-creation ordering only; no logic dependency).
**References:** [03 — `run-process`](../03-module-catalog.md), [07 settled 4 / open verify 23](../07-ambiguities-and-assumptions.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)` signature, the allowed output forms (plain return / named-port tuple / generator), the `finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py` are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit `a69d962`). This module appends to `modules/rtl_buddy/build.py`, which is created by spec [`06a`](06a-run-preproc.md) — append, do not overwrite. The file is shared with run-process (`03`), the prep modules (`06a`–`06b`, index [idx-06](../idx-06-prep.md)), and the compile-cycle modules (`07a`–`07b`, index [idx-07](../idx-07-compile-cycle.md)); coordinate shared imports and helpers with those specs.

## Goal

The generic async subprocess runner used by both compile and sim cycles. Redirects stdout/stderr to caller-supplied files; carries an opaque correlation key for downstream joining; enforces an optional timeout via SIGQUIT to the process group with SIGKILL escalation, signalling a timeout by returning `rc = None`.

## Lifecycle

Each `RunProcessMod.run()` call traverses exactly one terminal state between launch and return. The states below are exhaustive — anything not on this list is a defect.

1. **Launch.** `asyncio.create_subprocess_exec(*argv, stdout=out_fp, stderr=err_fp, preexec_fn=os.setpgrp, cwd=work_dir)`. The `preexec_fn` makes the child a process-group leader so the entire subtree can later be signalled in one syscall. `cwd=work_dir` runs the child in the artefact base directory supplied by the `work-dir` provider (= CWD for `test`/`randtest`; the per-suite `suite_dir` for regression), so the compiler/simulator resolves its own relative inputs (the `-f` filelist contents, `HierInstanceSeed.txt`, tool-internal scratch) and writes its relative outputs there — the per-subprocess equivalent of `do_rtl_regression`'s process-wide `os.chdir(suite_cfg_dir)` (`rtl_buddy.py:404`), but **concurrency-safe**: `cwd=` is per-`exec` so concurrent tests can run in different `work_dir`s without racing a shared process CWD (see Notes). Stdout/stderr are bound to caller-supplied files (opened by this module under `with`); no `PIPE`, no `communicate()`. Launch can fail — see Failure case (a).

2. **Wait.** `await asyncio.wait_for(proc.wait(), timeout.value if timeout else None)`. `timeout` is the `{key, value}` edge from `build-sim-cmd` (sim cycle); the compile cycle leaves it unwired (`None`), so `wait_for` is equivalent to a plain `proc.wait()`. Four mutually-exclusive resolutions:

   - **2a. Normal exit (or externally killed).** `proc.wait()` returns; `rc = proc.returncode` (non-negative for `exit(N)`, negative `-signum` for a death by signal — POSIX convention). Go to step 4. See Failure case (b) for the externally-killed sub-case.
   - **2b. Timeout (`asyncio.TimeoutError`).** The per-call timeout elapsed without the child exiting. Go to step 3a.
   - **2c. Cancellation (`asyncio.CancelledError`).** The harness cancelled the wrapping task. Go to step 3b.
   - **2d. Exited before `wait_for` first wakes up.** Asyncio's SIGCHLD child-watcher records the exit; `proc.wait()` resolves on the next event-loop tick with no race. Equivalent to 2a.

3. **Cleanup-and-kill** (entered only from 2b or 2c).

   - **3a. Timeout path.**
     1. `os.killpg(os.getpgid(proc.pid), signal.SIGQUIT)` — signals every process in the group, not just the leader. (rtl_buddy `vlog_sim.py:259` signals only the leader via `Popen.send_signal`; this plan corrects this — see Notes.)
     2. `await asyncio.wait_for(proc.wait(), self.grace_s)` — give the child a grace period to dump a core / flush logs. `grace_s` is a module `Config` field (default `5.0` s), set once per node at construction.
     3. If the grace elapses, escalate: `os.killpg(..., signal.SIGKILL)`, then unconditional `await proc.wait()` to reap.
     4. Set `rc = None` — the timeout indicator. Go to step 4.
   - **3b. Cancellation path.** Same SIGQUIT→grace→SIGKILL escalation as 3a, wrapped in `asyncio.shield` so the cleanup completes before the cancel propagates. The result is abandoned, but the child still needs a graceful window to release locks and close its on-disk state (coverage DB, lockfiles, waveforms) — otherwise a hard kill can leave corrupt/locked artifacts that poison the next run.
     1. `os.killpg(os.getpgid(proc.pid), signal.SIGQUIT)` — graceful, to the whole group.
     2. `await asyncio.shield(asyncio.wait_for(proc.wait(), self.grace_s))`; on grace expiry escalate `os.killpg(..., signal.SIGKILL)` then `await asyncio.shield(proc.wait())`. The `shield` wrappers prevent a second cancel from orphaning the subprocess between signal and reap.
     3. Re-raise `CancelledError`. No payload is returned — the harness propagates the cancel upward and ends this node's stream.

   In both 3a and 3b, `os.killpg` may raise `ProcessLookupError` (race: child exited between the `TimeoutError`/cancel and our signal). Swallow it; the subsequent `proc.wait()` still reaps.

4. **Return.** `Proc(command.key, rc=rc, stdout_path=..., stderr_path=...)` — `rc` is the child's return code, or `None` if step 3a fired (timeout). The outer `with`-blocks close the redirect files; already-flushed bytes are visible to downstream readers via the paths.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry — the catalog is the design view; the Lifecycle above and this spec are the authoritative build view. `env_ready` is an ordering-only input (never read or branched on); its edge from `prepend-cwd-path` is marked `required: true` and the node lists it in `persistent_inputs`, so the first invocation blocks until PATH is set and later ones replay the cached token (see [`$PATH` prepend](#path-prepend) below). `work_dir` is a **read** persistent input (the artefact base from `work-dir`) used as the subprocess `cwd`.

```
contract: default (compile instance: command only) / keyed_join over command+timeout (sim instance)
inputs:   command:{key, argv, stdout_path, stderr_path}, timeout:{key, value} | None = None, work_dir:Path, env_ready:bool = True
outputs:  default → proc:{key, rc:int|None, stdout_path, stderr_path}   # rc is None ⟺ timed out
```

**Per-instance contract.** The module is contract-agnostic and wired twice: the **compile** instance (`cc-run`) is `default` over `command` alone (`timeout` unwired → module default `None`); the **sim** instance (`sim-run`) is `keyed_join` over `command` + `timeout` joined by key, so the right per-test timeout pairs with the right command (a non-keyed timeout would mispair). `work_dir` and `env_ready` are `persistent_inputs` on **both** instances (`work_dir` is the single artefact base emitted once by `work-dir` and replayed to every invocation). `timeout` is a single-value `{key, value}` edge from `build-sim-cmd`; the module reads `timeout.value`. `command` and `proc` keep their named-field shapes (cohesive messages, not wrapped).

```python
class RunProcessMod:
    @serde
    class Config:
        grace_s: float = 5.0   # SIGQUIT→SIGKILL escalation grace; per-node, default 5.0 s
    def __init__(self, config):
        self.grace_s = config.grace_s
    async def run(self, command:Command, work_dir:Path, timeout:KeyedValue[float | None] | None = None, env_ready:bool = True):
        with open(command.stdout_path, "wb") as out, open(command.stderr_path, "wb") as err:
            try:
                proc = await asyncio.create_subprocess_exec(*command.argv,
                         stdout=out, stderr=err, preexec_fn=os.setpgrp, cwd=work_dir)   # run in the artefact base, not ambient CWD
            except (FileNotFoundError, PermissionError) as e:
                log.fatal("launch_failed", argv0=command.argv[0], exc_info=e)
            try:
                await asyncio.wait_for(proc.wait(), timeout.value if timeout else None)   # timeout: {key, value} edge or None
                rc = proc.returncode
            except asyncio.TimeoutError:
                # Lifecycle step 3a: SIGQUIT to group, grace, SIGKILL escalation
                rc = None   # the timeout indicator
        return Proc(command.key, rc=rc, stdout_path=command.stdout_path, stderr_path=command.stderr_path)
```

Both instances are config-bearing: the nested `Config` exposes `grace_s: float = 5.0` (the SIGQUIT→SIGKILL escalation grace), which the harness deserializes from each node's `config` mapping in the graph YAML and `__init__` stores as `self.grace_s`. The compile instance never times out, so its `grace_s` is inert; the sim instance reads it in Lifecycle step 3a.2. The Python default `5.0` keeps the module constructible without explicit node config and testable in isolation via `Config(grace_s=...)`.

## Deliverables

`modules/rtl_buddy/build.py::RunProcessMod`, refined per the Lifecycle above. The [03](../03-module-catalog.md) catalog sketch is illustrative; this spec is authoritative.

**Compatibility source:**
- `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:162-179` — `VlogSim.compile`'s `subprocess.run` + `FileNotFoundError` (no-timeout compile leg).
- `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:240-281` — `VlogSim.execute`'s `Popen` + `wait(timeout)` + `SIGQUIT`/`rc=4444` block (with-timeout sim leg). This plan diverges on signal target (process group, not leader) and adds SIGKILL escalation — see the policy below and [07 settled 23](../07-ambiguities-and-assumptions.md).

### Signal and timeout policy

| step | signal  | target        | grace before next  |
|------|---------|---------------|--------------------|
| 1    | SIGQUIT | process group | `self.grace_s`     |
| 2    | SIGKILL | process group | — (final reap)     |

- **Process group, not leader.** `os.killpg(os.getpgid(proc.pid), …)`. On POSIX, the child's process-group ID equals its PID after `os.setpgrp()`, so the explicit `getpgid` is defensive rather than load-bearing — but readable.
- **Grace period.** `self.grace_s` — a module `Config` field (default `5.0` s), set per node in the graph YAML; deserialized by the harness and independent of the per-test `timeout` data edge.
- **Grace on cancel too.** Cancellation is an `asyncio.CancelledError`, not an OS kill — the harness chose to stop, so the child still gets the SIGQUIT→grace→SIGKILL window to unwind its on-disk state. (An actual SIGKILL to the harness is delivered by the OS and propagated by it; this path does not model that.)

### `rc = None` timeout indicator

- **Who sets it.** `RunProcessMod` only; never propagated from a child.
- **When.** Exactly when step 3a completes — the timeout-and-kill path.
- **Unambiguous by construction.** A reaped child's `proc.returncode` is always an `int` (non-negative for `exit(N)`, negative `-signum` for a signal death) — never `None`. So `rc is None` in a returned `Proc` can only mean the runner timed the child out; no child exit value can collide with it. (This replaces rtl_buddy's `rc=4444` magic sentinel, which an organic `exit(4444)` could forge.)
- **Who reads it.** `interpret-sim` routes on `proc.rc is None`. The compile cycle wires `timeout=None`, so `rc is None` cannot appear there.
- **Divergence from source.** rtl_buddy returns `4444` (`tools/vlog_sim.py:260`) as its timeout sentinel; this plan returns `None` instead. Record in [`divergences.md`](../../divergences.md) when implementation lands.

### Cancellation behaviour

- File handles close via the outer `with`-block on any exit path, including `CancelledError`.
- Subprocess group gets the SIGQUIT→grace→SIGKILL escalation in the cancellation branch (same as timeout); every reap is wrapped in `asyncio.shield` so a second cancel cannot orphan the child.
- Partial stdout/stderr already on disk is preserved (the redirect-to-file design point — no Python-side buffering to lose).
- The module does **not** emit a `proc` payload on cancel; `CancelledError` propagates and ends this node's stream cleanly.

### Failure handling

- **(a) Launch failure.** `FileNotFoundError` (binary not on PATH) or `PermissionError` (exec bit unset, EACCES) raised by `asyncio.create_subprocess_exec`. The module **catches** it (an error this call can raise) and converts it to `log.fatal(...)` with the offending `argv[0]` and `exc_info` — mirroring `FileReadMod`'s file-access handling (`modules/io.py:23-30`). The original OS exception never escapes `run()`; the immediate harness exit 1 is driven by the CRITICAL log **level** (`docs/invariants.md` — CRITICAL → `SystemExit(1)`; `LoggingFatalHandler` raises `typer.Exit(1)`), not by an exception propagating up. Matches rtl_buddy `vlog_sim.py:163-165`. See [05 — Log idioms](../05-branching-and-results.md#log-idioms-per-failure-site).
- **(b) Externally killed.** A second process (admin `kill -9`, oom-killer, parent shell sending SIGTERM) reaps the child. `proc.wait()` returns `rc = -signum` (POSIX) — an `int`, not `None`, so it is **not** mistaken for a timeout. The negative `rc` is returned unchanged; downstream `interpret-compile`/`interpret-sim` treats it as ordinary non-zero failure.
- **(c) Exits before `wait_for` first wakes up.** Asyncio's SIGCHLD child-watcher records the exit; the first iteration of `proc.wait()` returns immediately. No race; no special handling.
- **(d) Subprocess never reaps.** SIGKILL escalation in step 3a.3 makes this defensively impossible for in-band timeout — SIGKILL is uncatchable on POSIX. For defence-in-depth, the final `await proc.wait()` (in both 3a and 3b) is unconditional; a hypothetically unreaped child would block the node, surfacing the defect rather than silently leaking.
- **Non-zero `rc` and `rc is None` (timeout) are not failures at this layer.** They are interpreted downstream by `interpret-compile` / `interpret-sim` as per-test results.

### Tests (`modules/tests/test_run_process.py`)

The tests below are testable against a slow-sleep bash fake (a child of the form `bash -c 'trap ... QUIT; sleep N'`) plus a few one-shot exit scripts.

- **Normal exit (rc 0).** Child writes "hello" to stdout, exits 0. Output dict has `rc=0`; stdout file contains "hello".
- **Non-zero `rc`.** Child exits 7. `rc=7`. No exception.
- **Timeout path — cooperative child.** Child runs `trap 'echo got_QUIT; exit 0' QUIT; sleep 30`; `timeout=KeyedValue(k, 0.1)`. Expect SIGQUIT delivered to the group, child exits during grace. `rc is None`, stdout file contains `got_QUIT`.
- **Timeout path — uncooperative child (SIGKILL escalation).** Child runs `trap '' QUIT; sleep 30`; `timeout=KeyedValue(k, 0.1)`, module constructed with `Config(grace_s=0.5)`. Expect SIGKILL after ~0.5 s, `rc is None`. Test completes in well under 30 s.
- **Process-group reach.** Child spawns a grandchild that also sleeps; on timeout, both die. Verify by `os.kill(grandchild_pid, 0)` raising `ProcessLookupError` after the call returns.
- **Launch failure.** `command.argv = ["/no/such/binary"]`. Module catches `FileNotFoundError` and calls `log.fatal` (the OS error never escapes `run()`); the CRITICAL level then raises `typer.Exit(1)` (asserted via `caplog` for the fatal record plus `pytest.raises(typer.Exit)`).
- **External kill.** Child runs a 10 s sleep; a sibling task sends SIGKILL at 0.1 s. `rc = -signal.SIGKILL` (an `int`, not `None`). The module returns normally.
- **Cancellation cleanup (cooperative child).** Wrap `run()` in an `asyncio.Task` that is `cancel()`-ed mid-wait; child runs `trap 'echo got_QUIT; exit 0' QUIT; sleep 30`. Assert: SIGQUIT is delivered (child exits during grace, `got_QUIT` in stdout), `CancelledError` propagates from the task, the child PID is gone (`os.kill(pid, 0)` → `ProcessLookupError`), the stdout file is closed, and `os.waitpid(-1, os.WNOHANG)` reports no orphans.
- **Cancellation cleanup (uncooperative child, SIGKILL escalation).** As above but `trap '' QUIT; sleep 30` and `Config(grace_s=0.5)` → SIGKILL after ~0.5 s, `CancelledError` re-raises, no orphans.
- **Organic `4444` is not a timeout.** A child that explicitly `exit(4444)` (no timeout) produces `rc=4444` (an `int`), **not** `None` — the timeout indicator cannot be forged by a child exit value.
- **Opaque key passthrough.** Output `key` equals input `command.key` on every successful return path (including timeout).
- **Emits paths, not handles.** Output dict's `stdout_path` / `stderr_path` are `str`/`Path`, not file objects.
- **`env_ready` accepted and ignored.** A `run()` call with `env_ready=True` (and with the parameter omitted, exercising the default) both succeed and produce identical output; the parameter never appears in the returned dict. The end-to-end PATH-resolution check (PrependCwdPathMod + a `.`-relative binary) lives in `test_setup.py` (spec [idx-04](../idx-04-setup.md)), not here, because the wiring is what's under test, not the runner.

### `$PATH` prepend

Owned by `PrependCwdPathMod` (a dedicated zero-input setup node — see spec [idx-04](../idx-04-setup.md) and [07 settled 25](../07-ambiguities-and-assumptions.md)). `run-process` itself does **not** mutate `os.environ`; it only declares a generic input `env_ready:bool = True` that the graph wires to `prepend-cwd-path`'s output. The value is never read or branched on — the input exists so the harness's data-dependency ordering pins the PATH mutation strictly upstream of every subprocess. In the production graph that edge is marked **`required: true`** (`docs/harness_configs/graph.md`) **and** the node lists `env_ready` in `persistent_inputs`: `required` suppresses the Python default so the **first** invocation is a blocking required port (PATH mutation strictly precedes the first subprocess), and `persistent` caches `prepend-path`'s once-emitted token to replay it on the streaming later invocations. The Python default `True` is retained so the module stays testable in isolation (called with no `env_ready`); `required`/`persistent` are per-wiring properties, not of this signature, so both hold. See [07 settled 25](../07-ambiguities-and-assumptions.md).

### Manifest

Append to the `- file: rtl_buddy/build.py` block in `modules/config.yaml` (opened by [`06a`](06a-run-preproc.md); append, don't re-create):

```yaml
  - { name: run-process, class_name: RunProcessMod }
```

## Tests

In `modules/tests/test_run_process.py` (async tests via `await run_module_scenario(...)`). Fixtures: `tmp_path` for the `stdout_path`/`stderr_path` redirect files; real shell children (`["sh", "-c", "…"]`) as the mock subprocess; `logging_handler` for the launch-failure path; an `asyncio` task wrapper for the cancellation case; `os.waitpid(-1, os.WNOHANG)` after return to assert no orphaned children. One terminal Lifecycle state per case (the list is exhaustive).

- `command` with `argv=["sh","-c","echo hi; exit 0"]`, `timeout=None` → emits `("default", {key, rc: 0, stdout_path, stderr_path})`; the `stdout_path` file contains `hi` (Lifecycle 2a, normal exit).
- Subprocess runs in `work_dir`, not the harness CWD: with `monkeypatch.chdir(other)`, `work_dir=tmp_path`, and **absolute** `stdout_path`/`stderr_path`, `argv=["sh","-c","pwd > ran_here; : > relative_artifact"]` → `tmp_path/"relative_artifact"` exists and `tmp_path/"ran_here"` resolves to `tmp_path` (boundary: the child's relative reads/writes resolve against `work_dir`, while the absolute redirect files are unaffected; nothing lands in `other`).
- `argv=["sh","-c","exit 7"]` → `rc: 7`, **no** log (a non-zero `rc` is not a failure at this layer — `interpret-*` classifies it downstream).
- A child killed by a signal externally → `rc: -<signum>` (negative `int`, POSIX convention; not `None`) (Lifecycle 2a externally-killed sub-case).
- `argv=["sh","-c","echo partial; sleep 5"]`, `timeout=KeyedValue(k, 0.1)` → `rc is None`; the already-written `partial` line is preserved in `stdout_path`, and `os.waitpid(-1, WNOHANG)` finds no stale children (Lifecycle 2b → 3a; process-group reap).
- `argv=["sh","-c","trap '' QUIT; sleep 30"]`, `timeout=KeyedValue(k, 0.1)` → SIGKILL escalation completes within `grace_s + ε` of the timeout; `rc is None` (boundary: SIGQUIT ignored → SIGKILL escalation in step 3a).
- A child that exits `4444` on a **normal** exit → `rc == 4444` (an `int`), **not** `None` (boundary: the timeout indicator is `rc is None`, never an exit value, so an organic 4444 is not misclassified).
- `argv=["./nonexistent-binary"]` → `create_subprocess_exec` raises `FileNotFoundError` → launch-failure `log.fatal` → `pytest.raises(typer.Exit)` (Failure case (a)).
- Wrap `run()` in a task and cancel it while the child sleeps → the child gets SIGQUIT then (on grace expiry) SIGKILL, reaped under `asyncio.shield`, `CancelledError` re-raises, **no** `proc` payload is emitted, partial stdout on disk is preserved, and no zombies remain (Lifecycle 2c → 3b).

## Acceptance criteria

- All tests above pass.
- A probe with a 1-second sleep child and a 100 ms timeout confirms partial output capture and clean process-group cleanup (no stale children in `os.waitpid(-1, os.WNOHANG)` after return).
- A probe with a SIGQUIT-trapping child (`trap '' QUIT; sleep 30`) confirms SIGKILL escalation completes within `grace_s + ε` of the timeout firing.
- SIGINT (Ctrl-C) at the harness level cancels the subprocess cleanly — the cancellation path runs to completion before `CancelledError` propagates, and no zombies remain.
- A reader of this spec can write a slow-sleep fake and exercise every state in the Lifecycle section without consulting source.
- Output port `default` exercised: emits `proc:{key, rc, stdout_path, stderr_path}` on both clean-exit (`rc` an `int`) and timed-out (`rc is None`) runs; no port-routed failure path (a non-zero `rc` is data, interpreted downstream).
- The `modules/config.yaml` manifest entry `{ name: run-process, class_name: RunProcessMod }` validates and the harness resolves `run-process` → `RunProcessMod` (shared by the compile and sim cycles).

## Constraints

- `grace_s` is a module `Config` field (default `5.0` s), set per node in the graph YAML — distinct from the per-test `timeout` data edge (set per test via `build-sim-cmd`).
- `rc = None` is set by **this module only**, **only** on the timeout-and-kill path (step 3a); never propagate `None` from a child (`proc.returncode` is always an `int` after reaping).
- The timeout indicator is `rc is None` — do **not** reintroduce a separate `timed_out` flag or a magic `int` sentinel. A child that organically exits 4444 reads `rc == 4444` (an `int`), never `None`.
- Signal the **process group** (`os.killpg`), not just the leader: SIGQUIT then SIGKILL escalation (grace = `self.grace_s`) on **both** timeout and cancel — cancel reaps under `asyncio.shield`. Swallow `ProcessLookupError` from `killpg` (exit race); the final `proc.wait()` still reaps.
- Redirect stdout/stderr to caller-supplied files under `with` — **never** `PIPE` / `communicate()` (bounds memory, preserves partial output across a kill).
- Launch the subprocess with `cwd=work_dir` — the artefact base from `work-dir`, supplied as a **read** persistent input on both instances. This is the per-`exec` (concurrency-safe) equivalent of `do_rtl_regression`'s process-wide `os.chdir` (`rtl_buddy.py:404`); the harness process itself never `chdir`s. `stdout_path`/`stderr_path` are absolute (composed under `logs_dir`, which is `work_dir`-rooted), so the redirect-file opens — done in the harness process — are unaffected by the child's `cwd`.
- Launch failure (`FileNotFoundError`/`PermissionError`) → `log.fatal` (harness exit 1). A non-zero `rc` or `rc is None` (timeout) is **not** a failure at this layer — downstream `interpret-compile`/`interpret-sim` classify it.
- On cancellation, do **not** emit a `proc` payload — re-raise `CancelledError` after reaping (shield the reap). `env_ready` is ordering-only: never read or branch on it.

## Notes

This is the workhorse — both compile and sim are wired instances of this single module (`cc-run` with no timeout; `sim-run` with the per-test timeout from `build-sim-cmd`). The redirect (rather than `PIPE`+`communicate`) is the non-negotiable design point: it preserves partial output across a SIGQUIT and keeps memory bounded regardless of log size.

**Deliberate rtl_buddy corrections.** Two:

1. rtl_buddy `vlog_sim.py:259` signals only the process-group leader (`process.send_signal(SIGQUIT)`); processes the simulator spawned (licence servers, helper shells) are not reached. This plan uses `os.killpg` to signal the whole group.
2. rtl_buddy has no SIGKILL escalation — a SIGQUIT-trapping simulator would hang the suite. This plan adds a `grace_s` window followed by SIGKILL.

Both should be recorded in [`divergences.md`](../../divergences.md) when implementation lands.

**Subprocess `cwd` replaces a process-wide `chdir`.** rtl_buddy's regression `os.chdir`s the whole process into each suite's directory and back (`rtl_buddy.py:404,436`) — safe only because it runs suites serially. rtl-comrade runs tests concurrently, so a process-wide `chdir` would race (one node's `chdir` corrupts every concurrent node's relative paths). This module instead passes `cwd=work_dir` to each `create_subprocess_exec`, which is per-child and shares no global state — so each subprocess resolves its relative inputs/outputs (the `-f` filelist contents, `HierInstanceSeed.txt`, tool scratch) against its own `work_dir` while the harness process never `chdir`s. This is what makes `work_dir` (from `work-dir`) the genuine single artefact-location source: the leaf modules root *paths* on it and the runner roots the *child's CWD* on it. Record in [`divergences.md`](../../divergences.md) when implementation lands.

**asyncio child-watcher.** Python 3.8+ default `ThreadedChildWatcher` reaps children transparently; no explicit `os.waitpid` is required beyond `proc.wait()`. Confirming the default policy on the target Python is tracked under [07 item 23](../07-ambiguities-and-assumptions.md) (async subprocess hardening — empirical verification before the module is built).

**`asyncio.shield` around the cancellation-path reap.** Small and non-load-bearing, but explicit: a second cancellation during the finally-block would otherwise drop the subprocess on the floor mid-reap.
