# Spec 03: `run-process` module

**Depends on:** none.
**References:** [03 — `run-process`](../03-module-catalog.md), [07 settled 4 / open verify 23](../07-ambiguities-and-assumptions.md).

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

The generic async subprocess runner used by both compile and sim cycles. Redirects
stdout/stderr to caller-supplied files; carries an opaque correlation key for downstream
joining; enforces an optional timeout via SIGQUIT to the process group with SIGKILL
escalation, surfacing the rtl_buddy `rc=4444` sentinel.

## Lifecycle

Each `RunProcessMod.run()` call traverses exactly one terminal state between launch and
return. The states below are exhaustive — anything not on this list is a defect.

1. **Launch.** `asyncio.create_subprocess_exec(*argv, stdout=out_fp, stderr=err_fp,
   preexec_fn=os.setpgrp)`. The `preexec_fn` makes the child a process-group leader so
   the entire subtree can later be signalled in one syscall. Stdout/stderr are bound to
   caller-supplied files (opened by this module under `with`); no `PIPE`, no
   `communicate()`. Launch can fail — see Failure case (a).

2. **Wait.** `await asyncio.wait_for(proc.wait(), timeout)`. With `timeout=None`
   (compile cycle), `wait_for` is equivalent to a plain `proc.wait()`. Four
   mutually-exclusive resolutions:

   - **2a. Normal exit (or externally killed).** `proc.wait()` returns; `rc =
     proc.returncode` (non-negative for `exit(N)`, negative `-signum` for a death by
     signal — POSIX convention). `timed_out = False`. Go to step 4. See Failure case (b)
     for the externally-killed sub-case.
   - **2b. Timeout (`asyncio.TimeoutError`).** The per-call timeout elapsed without the
     child exiting. Go to step 3a.
   - **2c. Cancellation (`asyncio.CancelledError`).** The harness cancelled the wrapping
     task. Go to step 3b.
   - **2d. Exited before `wait_for` first wakes up.** Asyncio's SIGCHLD child-watcher
     records the exit; `proc.wait()` resolves on the next event-loop tick with no race.
     Equivalent to 2a.

3. **Cleanup-and-kill** (entered only from 2b or 2c).

   - **3a. Timeout path.**
     1. `os.killpg(os.getpgid(proc.pid), signal.SIGQUIT)` — signals every process in the
        group, not just the leader. (rtl_buddy `vlog_sim.py:259` signals only the leader
        via `Popen.send_signal`; Plan B corrects this — see Notes.)
     2. `await asyncio.wait_for(proc.wait(), _TIMEOUT_GRACE_S)` — give the child a grace
        period to dump a core / flush logs. `_TIMEOUT_GRACE_S` is a module-level constant
        (`5.0` s, not per-invocation).
     3. If the grace elapses, escalate: `os.killpg(..., signal.SIGKILL)`, then
        unconditional `await proc.wait()` to reap.
     4. Set `rc = 4444`, `timed_out = True`. Go to step 4.
   - **3b. Cancellation path.**
     1. `os.killpg(os.getpgid(proc.pid), signal.SIGKILL)` — no grace; the caller already
        abandoned the result.
     2. `await asyncio.shield(proc.wait())` to reap. The `shield` wrapper prevents a
        second cancel from orphaning the subprocess between the kill and the reap.
     3. Re-raise `CancelledError`. No payload is returned — the harness propagates the
        cancel upward and ends this node's stream.

   In both 3a and 3b, `os.killpg` may raise `ProcessLookupError` (race: child exited
   between the `TimeoutError`/cancel and our signal). Swallow it; the subsequent
   `proc.wait()` still reaps.

4. **Return.** `{ "key": command["key"], "rc": rc, "timed_out": timed_out,
   "stdout_path": ..., "stderr_path": ... }`. The outer `with`-blocks close the redirect
   files; already-flushed bytes are visible to downstream readers via the paths.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry —
the catalog is the design view; the Lifecycle above and this spec are the authoritative
build view. `env_ready` is an ordering-only persistent input (never read or branched on).

```
contract: default
inputs:   command:{key, argv, stdout_path, stderr_path}, timeout:float | None = None, env_ready:bool = True
outputs:  default → proc:{key, rc, timed_out, stdout_path, stderr_path}
```

```python
class RunProcessMod:
    async def run(self, command:dict, timeout:float | None = None, env_ready:bool = True):
        with open(command["stdout_path"], "wb") as out, open(command["stderr_path"], "wb") as err:
            proc = await asyncio.create_subprocess_exec(*command["argv"],
                     stdout=out, stderr=err, preexec_fn=os.setpgrp)
            timed_out = False
            try:
                await asyncio.wait_for(proc.wait(), timeout)
                rc = proc.returncode
            except asyncio.TimeoutError:
                # Lifecycle step 3a: SIGQUIT to group, grace, SIGKILL escalation
                rc, timed_out = 4444, True
        return { "key": command["key"], "rc": rc, "timed_out": timed_out,
                 "stdout_path": command["stdout_path"], "stderr_path": command["stderr_path"] }
```

## Deliverables

`modules/rtl_test/build.py::RunProcessMod`, refined per the Lifecycle above. The
[03](../03-module-catalog.md) catalog sketch is illustrative; this spec is authoritative.

**Compatibility source:**
- `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:162-179` — `VlogSim.compile`'s `subprocess.run` + `FileNotFoundError` (no-timeout compile leg).
- `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:240-281` — `VlogSim.execute`'s `Popen` + `wait(timeout)` + `SIGQUIT`/`rc=4444` block (with-timeout sim leg). Plan B diverges on signal target (process group, not leader) and adds SIGKILL escalation — see the policy below and [07 settled 23](../07-ambiguities-and-assumptions.md).

### Signal and timeout policy

| step | signal  | target        | grace before next  |
|------|---------|---------------|--------------------|
| 1    | SIGQUIT | process group | `_TIMEOUT_GRACE_S` |
| 2    | SIGKILL | process group | — (final reap)     |

- **Process group, not leader.** `os.killpg(os.getpgid(proc.pid), …)`. On POSIX, the
  child's process-group ID equals its PID after `os.setpgrp()`, so the explicit
  `getpgid` is defensive rather than load-bearing — but readable.
- **Grace period.** `_TIMEOUT_GRACE_S = 5.0`. Module-level constant, **not** exposed as
  a per-command knob; the per-test `timeout` is the user-facing dial and a second knob
  would have to flow through `build-sim-cmd` for no use case.
- **No grace on cancel.** Cancellation says "abandon"; escalating to SIGKILL immediately
  is cheaper and correct.

### `rc=4444` sentinel

- **Who sets it.** `RunProcessMod` only; never propagated from a child.
- **When.** Exactly when step 3a completes — the timeout-and-kill path.
- **`timed_out` is independent of `rc`.** The flag is set explicitly at the return site
  (step 4), not derived from `rc == 4444`, so a child that legitimately returns 4444 is
  not misclassified as a timeout.
- **Who reads it.** `interpret-sim` (via `proc["timed_out"]`; `rc` is informational for
  logging). The compile cycle wires `timeout=None`, so `rc=4444` cannot appear there.
- **Convention source.** Matches `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:260`.

### Cancellation behaviour

- File handles close via the outer `with`-block on any exit path, including
  `CancelledError`.
- Subprocess group is sent SIGKILL in the cancellation branch; the cleanup `proc.wait()`
  is wrapped in `asyncio.shield` so a second cancel cannot orphan the child.
- Partial stdout/stderr already on disk is preserved (the redirect-to-file design
  point — no Python-side buffering to lose).
- The module does **not** emit a `proc` payload on cancel; `CancelledError` propagates
  and ends this node's stream cleanly.

### Failure handling

- **(a) Launch failure.** `FileNotFoundError` (binary not on PATH) or `PermissionError`
  (exec bit unset, EACCES) raised by `asyncio.create_subprocess_exec`. Caught;
  `log.critical(...)` emitted with the offending `argv[0]`. Matches rtl_buddy
  `vlog_sim.py:163-165`. Harness exits 1 via the deferred-CRITICAL contract. See
  [05 — Log idioms](../05-branching-and-results.md#log-idioms-per-failure-site).
- **(b) Externally killed.** A second process (admin `kill -9`, oom-killer, parent
  shell sending SIGTERM) reaps the child. `proc.wait()` returns `rc = -signum` (POSIX).
  `timed_out = False`. The negative `rc` is returned unchanged; downstream
  `interpret-compile`/`interpret-sim` treats it as ordinary non-zero failure.
- **(c) Exits before `wait_for` first wakes up.** Asyncio's SIGCHLD child-watcher
  records the exit; the first iteration of `proc.wait()` returns immediately. No race;
  no special handling.
- **(d) Subprocess never reaps.** SIGKILL escalation in step 3a.3 makes this
  defensively impossible for in-band timeout — SIGKILL is uncatchable on POSIX. For
  defence-in-depth, the final `await proc.wait()` (in both 3a and 3b) is unconditional;
  a hypothetically unreaped child would block the node, surfacing the defect rather
  than silently leaking.
- **Non-zero `rc` and `timed_out=True` are not failures at this layer.** They are
  interpreted downstream by `interpret-compile` / `interpret-sim` as per-test results.

### Tests (`modules/tests/test_run_process.py`)

The tests below are testable against a slow-sleep bash fake (a child of the form
`bash -c 'trap ... QUIT; sleep N'`) plus a few one-shot exit scripts.

- **Normal exit (rc 0).** Child writes "hello" to stdout, exits 0. Output dict has
  `rc=0`, `timed_out=False`; stdout file contains "hello".
- **Non-zero `rc`.** Child exits 7. `rc=7`, `timed_out=False`. No exception.
- **Timeout path — cooperative child.** Child runs
  `trap 'echo got_QUIT; exit 0' QUIT; sleep 30`; `timeout=0.1`. Expect SIGQUIT delivered
  to the group, child exits during grace. `rc=4444`, `timed_out=True`, stdout file
  contains `got_QUIT`.
- **Timeout path — uncooperative child (SIGKILL escalation).** Child runs `trap '' QUIT;
  sleep 30`; `timeout=0.1`, `_TIMEOUT_GRACE_S=0.5` (monkeypatched). Expect SIGKILL after
  ~0.5 s, `rc=4444`, `timed_out=True`. Test completes in well under 30 s.
- **Process-group reach.** Child spawns a grandchild that also sleeps; on timeout, both
  die. Verify by `os.kill(grandchild_pid, 0)` raising `ProcessLookupError` after the
  call returns.
- **Launch failure.** `command["argv"] = ["/no/such/binary"]`. Module catches
  `FileNotFoundError` and calls `log.critical`; the harness exits 1 (asserted via
  `caplog` plus the bubbling-`SystemExit` contract).
- **External kill.** Child runs a 10 s sleep; a sibling task sends SIGKILL at 0.1 s.
  `rc = -signal.SIGKILL`, `timed_out=False`. The module returns normally.
- **Cancellation cleanup.** Wrap `run()` in an `asyncio.Task` that is `cancel()`-ed
  mid-wait. Assert: `CancelledError` propagates from the task; the child PID is no
  longer alive (`os.kill(pid, 0)` → `ProcessLookupError`); the stdout file is closed;
  `os.waitpid(-1, os.WNOHANG)` reports no orphans.
- **Independent `timed_out` flag.** A child that explicitly `exit(4444)` (no timeout)
  produces `rc=4444`, `timed_out=False` — i.e. the flag is not derived from `rc`.
- **Opaque key passthrough.** Output `key` equals input `command["key"]` on every
  successful return path (including timeout).
- **Emits paths, not handles.** Output dict's `stdout_path` / `stderr_path` are
  `str`/`Path`, not file objects.
- **`env_ready` accepted and ignored.** A `run()` call with `env_ready=True` (and
  with the parameter omitted, exercising the default) both succeed and produce
  identical output; the parameter never appears in the returned dict. The
  end-to-end PATH-resolution check (PrependCwdPathMod + a `.`-relative binary)
  lives in `test_setup.py` (spec [04](04-setup-modules.md)), not here, because
  the wiring is what's under test, not the runner.

### `$PATH` prepend

Owned by `PrependCwdPathMod` (a dedicated setup `unit` node — see spec
[04](04-setup-modules.md) and [07 settled 25](../07-ambiguities-and-assumptions.md)).
`run-process` itself does **not** mutate `os.environ`; it only declares a generic
persistent input `env_ready:bool = True` that the graph wires to `prepend-cwd-path`'s
output. The value is never read or branched on — the input exists so the harness's
data-dependency ordering pins the PATH mutation strictly upstream of every subprocess.
The Python default `True` keeps the module testable in isolation and the graph valid if
no env-setup node is wired.

### Manifest

Append to the `- file: rtl_test/build.py` block in `modules/config.yaml` (opened by
[`06a`](06a-run-preproc.md); append, don't re-create):

```yaml
  - { name: run-process, class_name: RunProcessMod }
```

## Acceptance criteria

- All tests above pass.
- A probe with a 1-second sleep child and a 100 ms timeout confirms partial output
  capture and clean process-group cleanup (no stale children in `os.waitpid(-1,
  os.WNOHANG)` after return).
- A probe with a SIGQUIT-trapping child (`trap '' QUIT; sleep 30`) confirms SIGKILL
  escalation completes within `_TIMEOUT_GRACE_S + ε` of the timeout firing.
- SIGINT (Ctrl-C) at the harness level cancels the subprocess cleanly — the cancellation
  path runs to completion before `CancelledError` propagates, and no zombies remain.
- A reader of this spec can write a slow-sleep fake and exercise every state in the
  Lifecycle section without consulting source.

## Notes

This is the workhorse — both compile and sim are wired instances of this single module
(`cc-run` with no timeout; `sim-run` with the per-test timeout from `build-sim-cmd`).
The redirect (rather than `PIPE`+`communicate`) is the non-negotiable design point: it
preserves partial output across a SIGQUIT and keeps memory bounded regardless of log
size.

**Deliberate rtl_buddy corrections.** Two:

1. rtl_buddy `vlog_sim.py:259` signals only the process-group leader
   (`process.send_signal(SIGQUIT)`); processes the simulator spawned (licence servers,
   helper shells) are not reached. Plan B uses `os.killpg` to signal the whole group.
2. rtl_buddy has no SIGKILL escalation — a SIGQUIT-trapping simulator would hang the
   suite. Plan B adds a `_TIMEOUT_GRACE_S` window followed by SIGKILL.

Both should be recorded under "Notable divergences" in
[07](../07-ambiguities-and-assumptions.md) when implementation lands.

**`timed_out` is set independently of `rc`.** rtl_buddy's `timed_out` is implicitly
`rc == 4444`. Plan B sets the flag at the return site (step 4) so a child that
organically returns 4444 is not misclassified.

**asyncio child-watcher.** Python 3.8+ default `ThreadedChildWatcher` reaps children
transparently; no explicit `os.waitpid` is required beyond `proc.wait()`. Spec 00's
framework probe should confirm the default policy on the target Python.

**`asyncio.shield` around the cancellation-path reap.** Small and non-load-bearing,
but explicit: a second cancellation during the finally-block would otherwise drop the
subprocess on the floor mid-reap.
