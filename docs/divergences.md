# Divergences from rtl_buddy

Behavioural deltas between rtl-comrade's `test` command and upstream `rtl_buddy test`. Each entry describes what rtl_buddy does, what rtl-comrade does instead, and whether the delta is deliberate or a known, deferred limitation.

For the `test` graph itself see [graphs/test.md](graphs/test.md); for the CLI and output layout see [graphs/index.md](graphs/index.md).

---

## Deliberate divergences

### `--early-stop` exits 0 instead of 1

rtl_buddy exits 1 on `--early-stop` because it treats an NA verdict as a failure (`EarlyStopResults.is_pass()` returns False). rtl-comrade treats a user-requested early stop as a deliberate, successful early exit: `early-stop-gate` emits no `log.error`, so the run exits 0. The per-test NA verdict is unchanged.

### `--early-stop pre/comp` desc uses phase token

rtl_buddy emits `"Stopped early at preproc"` / `"Stopped early at compile"` for the `pre` and `comp` phases. rtl-comrade emits `"Stopped early at pre"` / `"Stopped early at comp"` (the phase token). The `sim` desc is identical between the two.

### Compile logs persisted to files

rtl_buddy captures compile output in memory (`subprocess.run(capture_output=True)`) and logs it on failure but never writes it to disk. rtl-comrade redirects compile stdout/stderr to `logs/<test>.compile.log` / `logs/<test>.compile.err` as a side effect of `run-process` always redirecting. The files are produced even on success.

### `load-model` is lazy

rtl_buddy loads every test's model during suite parsing (`TestConfigFile.initialise`), so a broken `models.yaml` on a skipped test causes an early error. rtl-comrade loads models lazily, per-test, after `filter-reglvl` has excluded skipped tests. A broken `models.yaml` on a filtered-out test is never read and does not affect the run.

### `ParseLogMod` corrects VlogPost quirks

rtl_buddy's `VlogPost` has three bugs corrected in `ParseLogMod`:
1. Word-boundary guard: `PASSTHROUGH` no longer misclassifies as PASS.
2. FAIL wins over PASS when both appear in the log.
3. FAIL-without-`ERR:` no longer crashes (`AttributeError` on `None.group(2)`).

### `select-platform` is first-match

rtl_buddy's `config/root.py` iterates all platforms with no `break`, so the last matching platform wins when two share a `uname`. rtl-comrade returns on the first match. Overlapping `unames` are a misconfiguration; single-platform-per-`uname` configs (the norm) are unaffected.

### `-L/--logs-dir` override and centralised artefact provenance

rtl_buddy hard-codes `"logs"` as the artefact subdirectory. rtl-comrade accepts a `-L/--logs-dir` CLI override (default `"logs"`) and centralises artefact-location provenance in the `work-dir` and `ensure-logs-dir` nodes.

### `sim` timeout signalled by `rc is None`, not a `4444` sentinel

rtl_buddy returns `rc=4444` as its timeout sentinel (`tools/vlog_sim.py:260`), which an organic `exit(4444)` could forge. rtl-comrade's `run-process` returns `Proc.rc = None` on the timeout-and-kill path; a reaped child's returncode is always an `int`, so `rc is None` unambiguously means the runner timed the child out. `interpret-sim` routes on `proc.rc is None` (`modules/rtl_buddy/sim.py:104`).

### Timeout signals the whole process group (`os.killpg`)

rtl_buddy signals only the process-group leader (`process.send_signal(SIGQUIT)`, `tools/vlog_sim.py:259`), so processes the simulator spawned (licence servers, helper shells) are never reached. rtl-comrade uses `os.killpg(os.getpgid(proc.pid), SIGQUIT)` (`build.py:167,181`) to reach the whole group.

### SIGKILL escalation after a grace window

rtl_buddy has no SIGKILL escalation — a SIGQUIT-trapping simulator hangs the suite indefinitely. rtl-comrade waits `grace_s` (per-node, default `5.0`s) after SIGQUIT, then escalates to `os.killpg(..., SIGKILL)` (`build.py:145,171-174,185-188`).

### Per-child `cwd=work_dir` replaces a process-wide `chdir`

rtl_buddy `os.chdir`s the whole process into each suite's directory and back (`rtl_buddy.py:404,436`) — safe only because it runs suites serially. rtl-comrade runs tests concurrently, where a process-wide `chdir` would race, so it passes `cwd=work_dir` to each `create_subprocess_exec` (`build.py:158`) — per-child, no shared global state. This is what makes `work_dir` the single artefact-location source: the leaves root their paths on it, the runner roots each child's CWD on it, and the harness process never `chdir`s.

### Atomic `force_symlink`

rtl_buddy's `force_symlink` does a non-atomic `os.remove` + `os.symlink` (`tools/vlog_sim.py:26-30`), leaving a window with no link. rtl-comrade symlinks to a unique temp name then `os.replace`s it over the target (`sim.py:89-92`), so the "latest" pointer swap is atomic.

---

## Fixed-simv concurrency hole (deferred)

On non-verilator (fixed-simv) builders, a concurrent multi-test run can overwrite one test's binary with another's and silently report wrong results (rc 0, green summary). There is no built-in serialisation. This is an expected, known limitation deferred until the upstream rtl_buddy per-invocation-subdir change lands. Validate fixed-simv builders one test per invocation as an operational workaround.

Verilator builders are unaffected: each test writes to a per-tag `obj_dir_<tag>/` directory, so concurrent runs do not collide.

---

## Latent / conditional divergences

These are corrections whose triggering condition has not yet fired; they are recorded here pre-emptively.

### `ModelConfig.get_model_name` bug fix

rtl_buddy's `ModelConfig.get_model_name` returns `self.model_name` (`config/model.py:30`) — an attribute that does not exist on the dataclass (`name` is the real field), so any caller would `AttributeError`. No rtl_buddy caller invokes it, so this never surfaced. rtl-comrade fixes it to return `self.name` (`modules/rtl_buddy/schema/model.py:12`). There is currently no production or reference-suite caller, so this is informational.

### Sweep/preproc script model-view residuals

The `sweep`/`preproc` hooks run drop-in user scripts against rtl-comrade's reimplemented `TestConfig`/`root_cfg`, and expose the resolved `ModelConfig` as `test_cfg.model` only for the span of the `exec`, restoring the name string before the edge is emitted. Two residual deltas from rtl_buddy, neither yet observed in a real script:

1. Reimplemented-`TestConfig` surface differences (method/attribute shapes beyond the `name`/`set_plusarg`/`get_plusargs`/`deepcopy` the reference scripts use) could break a script that relied on rtl_buddy-specific surface.
2. A script that *reassigns* `test_cfg.model` to a different `ModelConfig` has the reassignment dropped — the post-exec restore puts the name string back and the resolved `model` edge is fixed upstream — whereas in rtl_buddy such a reassignment could change what compiles.

The reference scripts (`example_sweep.py` / `example_preproc.py`) trip neither.
