# Module catalog

Each module is the smallest sensible unit of node-local work. Every `run()` parameter is
one input port the harness can see; branches are expressed as named output ports; **no
module contains scheduling** (no guards, no awareness of other items). Signatures follow
the repo style (no space before the annotation colon, British spelling). "Tags" are
documentation-level labels (the manifest has no tag field — see
[07](07-ambiguities-and-assumptions.md)); they replace the old phase structure.

Conventions: `ctx`, `test_run`, `sim_cmd`, `command`, `proc`, `seed`, `filelist`, `result`
are the payload shapes from [02](02-payload-conventions.md). **Contract** is the recommended pairing
([04](04-pipeline-and-contracts.md)).

---

## Setup / config

> **Reimplemented, not wrapped.** Per [07](07-ambiguities-and-assumptions.md) item 1, these
> modules reimplement `rtl_buddy`'s behaviour natively; only the **config schema** (the YAML
> field names/structure of `root_config.yaml`, `tests.yaml`, `models.yaml`) is preserved, so
> existing config files load drop-in. Reimplementing is what lets the monolithic loaders be
> split into the atomic, reusable nodes below.

### `discover-config-file`  · tags: setup · contract: `unit`
Walk up the directory tree from CWD for a filename, stopping at the git root / filesystem
root. Generic and reusable (the harness itself locates `rtl_comrade_config.yaml` this way).

- **Config:** `filename:str` (e.g. `root_config.yaml`), `max_levels:int = 8`
- **In:** — (zero-input; runs once)
- **Out:** default → `Path`
- **Log idiom:** `log.critical` if no `root_config.yaml` found; immediate `SystemExit(1)`. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

### `prepend-cwd-path`  · tags: setup · contract: `unit`
Prepend `.` to `$PATH` so a CWD-local simulator (`simv`, `verilator`) is discoverable by
downstream subprocess invocations. Idempotent — skips the mutation if `.` is already on
`$PATH`. Mirrors `rtl_buddy/src/rtl_buddy/rtl_buddy.py:100-102`, where rtl_buddy does the
same once at CLI bootstrap; here it is a graph node so the responsibility is explicit.
Emits a `bool` sentinel consumed by `run-process` (`env_ready`), which pins the mutation
strictly upstream of every compile/sim subprocess via the harness's data-dependency
ordering — no race window. No failure path: dict mutation cannot meaningfully fail.

- **In:** — (zero-input; runs once)
- **Out:** default → `bool` (always `True`; the receiver only uses it for sequencing)
- **Log idiom:** none (no failure path). See [07 settled 25](07-ambiguities-and-assumptions.md).

### `parse-root-config`  · tags: setup · contract: `unit`
Deserialise the root-config YAML into schema-compatible dataclasses (preserving rtl_buddy
field names: `rtl-buddy-filetype`, `cfg-rtl-builder`, `cfg-platforms`, …).

- **In:** `path:Path`
- **Out:** default → `root_cfg`
- **Log idiom:** `log.critical` on malformed YAML / schema mismatch. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

### `select-platform`  · tags: setup · contract: `unit`
Run `uname` and match it against each platform's `unames`; pick the platform. Side-effecting
(subprocess), runs once.

- **In:** `root_cfg`
- **Out:** default → `platform_cfg`
- **Log idiom:** `log.critical` if no platform's `unames` matches the current host. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

### `resolve-builder`  · tags: setup · contract: `unit`
Resolve the active builder from the platform (honouring the `--builder` override); critical
if the named builder is missing.

- **In:** `platform_cfg`, `builder:str = ""`
- **Out:** default → `builder_cfg`
- **Log idiom:** `log.critical` if the named builder is missing on the platform. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

### `check-suite-cwd`  · tags: setup · contract: `unit`
Enforce the user-driven CWD convention: `rtl-comrade test`/`randtest` must be invoked from
the suite directory (matching `rtl_buddy`'s `do_cmd_test`, which never `chdir`s — only
`do_rtl_regression` does, per-suite). Resolves the CLI `test_config` against CWD and
fails fast if the resolved path's parent is not CWD. Emits the resolved `Path` for
downstream `parse-suite-config`.

- **In:** `test_config:str = "tests.yaml"`
- **Out:** default → `Path` (the resolved suite-config path)
- **Log idiom:** `log.critical` if (a) `(Path.cwd() / test_config).resolve().parent !=
  Path.cwd().resolve()` (CWD mismatch), or (b) the resolved path is not a file. See
  [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site). Not wired
  in the regression graph (regression `chdir`s per-suite — see
  [08](08-sibling-graphs.md)).

### `ensure-logs-dir`  · tags: setup · contract: `unit`
Bootstrap the CWD-relative artefact directory (`logs/` by default) that downstream subprocess
nodes and randseed writers redirect into. Mirrors `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:55-59`
(`output_dir = "logs"; if not os.path.exists(...): os.makedirs(...)`), lifted out of
`VlogSim.__init__`'s per-test lazy mkdir into a single explicit setup node so no downstream
writer needs to `mkdir` and the directory is created exactly once per invocation. Takes the
CLI `logs_dir` (with `--logs-dir` default `"logs"` — a small **Notable divergence** from
rtl_buddy, which has no override; see [07](07-ambiguities-and-assumptions.md)), plus two
sequencing inputs: `env_ready:bool` from `prepend-cwd-path` (chains the PATH-prepend
strictly upstream) and `_cwd:Path` from `check-suite-cwd` (so a bad-CWD invocation never
materialises a rogue `logs/` before the cwd check has aborted). Emits a `bool` sentinel
consumed by `cc-run.env_ready` and `sim-run.env_ready` — the env_ready chain
([07 settled 25](07-ambiguities-and-assumptions.md)) is now `prepend-path → ensure-logs →
cc-run/sim-run`. Idempotent (`mkdir(parents=True, exist_ok=True)`) — accepts nested or
absolute `logs_dir`. Not wired in the regression graph (regression `chdir`s per-suite — see
[08](08-sibling-graphs.md)).

- **In:** `logs_dir:str = "logs"`, `env_ready:bool = True`, `_cwd:Path`
- **Out:** default → `bool` (always `True`; only used for sequencing)
- **Log idiom:** `log.info("logs_dir_ready", path=...)` once; no failure port. `OSError` /
  `PermissionError` from `mkdir` propagate uncaught and surface as a harness CRITICAL via
  the bubbling-SystemExit catch (same idiom as `discover-config-file`'s `PermissionError`).
  See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site) and
  [07 settled 26](07-ambiguities-and-assumptions.md).

### `parse-suite-config`  · tags: setup · contract: `unit`
Deserialise `tests.yaml` into the schema-compatible suite (testbenches + tests), binding each
test to its testbench (within-file) and recording the suite directory on each test so
`load-model` can resolve `model_path` later. Model loading is deferred to `load-model`.

- **In:** `test_config:Path` (resolved by `check-suite-cwd` in test/randtest, or by
  `parse-reg-config` in regression — see [08](08-sibling-graphs.md))
- **Out:** default → `suite_cfg`
- **Log idiom:** `log.critical` on `tests.yaml` missing/malformed or testbench bind failure. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

### `derive-seed-mode`  · tags: setup · contract: `unit`
Collapse the two bool flags into one `SeedMode` (`rnd_new` wins, else `DEFAULT`).

- **In:** `rnd_new:bool = False`, `rnd_last:bool = False`
- **Out:** default → `SeedMode`

### `git-status`  · tags: setup · contract: `unit`
Record the repository's git state once at run start, for reproducibility and bug triage
(rtl_buddy logs git state alongside results). Zero-input; reads `git` via subprocess (or
`subprocess.run(["git", "rev-parse", ...])`) and emits a single structured log event
`log.info("git_state", branch=..., sha=..., dirty=...)`. It routes **nothing through the
graph**: the summary is assembled by the `SummaryHandler` logging plugin, which collects the
`git_state` event (see [05 — Re-convergence](05-branching-and-results.md#re-convergence-the-summary-is-a-logging-concern-not-a-graph-node)).
This is the resolution of TODO #15 — git state is recorded as a logging concern, not a
graph-routed payload, which is what makes it a one-line setup node.

- **In:** — (zero-input; runs once)
- **Out:** default → `bool` (always `True`; unwired — the node exists only for its `log.info`
  side-effect, so the harness logs `no_destination` at INFO)
- **Log idiom:** `log.info("git_state", ...)` once. Not in a git repo / `git` missing →
  `log.warning("git_state_unavailable", ...)` and emit nothing collectable; **never**
  `log.error`/`log.critical` (git state is informational, not a run gate). See
  [07 settled 27](07-ambiguities-and-assumptions.md).

---

## Selection / expansion (fan-out)

### `route-list-mode`  · tags: select · contract: `unit`
Routes on the `--list` flag (a global mode): `list` → the `list-test-names` terminal,
`run` → `select-tests`. A pure named-port classifier, so neither downstream needs a guard.

- **In:** `suite_cfg`, `list:bool = False`
- **Out:** `("run", suite_cfg)` | `("list", suite_cfg)`

### `list-test-names`  · tags: select · contract: `unit`
Print the suite's test names. Terminal — emits nothing, so in list-mode the whole pipeline
drains and exits 0.

- **In:** `suite_cfg`
- **Out:** none

### `select-tests`  · tags: select · contract: `unit`
Select one test or all (`get_tests(test_name)`) and yield one `ctx` per test, stamping
`key`. No mode logic — `--list` is handled upstream by `route-list-mode`.

- **In:** `suite_cfg`, `test_name:str = ""`
- **Out:** default → `ctx` per test
- **Log idiom:** `log.critical` if `test_name` is given but not found in the suite (matches `rtl_buddy`'s `typer.Abort`). See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

```python
class SelectTestsMod:
    def run(self, suite_cfg, test_name:str = ""):
        for t in suite_cfg.get_tests(test_name or None):
            yield ("default", { "key": t.get_name(), "test": t, "run_id": None })
```

### `filter-reglvl`  · tags: select · contract: `default` (persistent: `builder_cfg`,`reg_level`,`start_level`)
`TestConfig.get_reglvl(builder_cfg.get_name())`. Emits on `skip` (a `result` payload)
when outside the `[start_level, reg_level]` window, else on `keep`. For `test`,
`reg_level`/`start_level` default to `None`, so it always emits `keep`; the node exists
so `regression` reuses it. Only the builder *name* is read off `builder_cfg` (see spec
[01a](specs/01a-builder-schema.md)); the full object is carried on the port because the
same `builder_cfg` feeds `cc-build`, `seed`, and `sim-build` downstream.

- **In:** `ctx`, `builder_cfg`, `reg_level=None`, `start_level=None`
- **Out:** `("keep", ctx)` | `("skip", result)`
- **Log idiom:** port-routed `skip` `result`; no log call (SKIP is pass-like via `is_pass()`). See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

### `load-model`  · tags: select · contract: `default`
Load the test's `models.yaml` (resolving `model_path` relative to the suite dir recorded by
`parse-suite-config`) and attach the `ModelConfig` to `ctx["test"]`. Deferred from suite
parse so it is per-test and reusable (the `filelist` command needs the same step).

- **In:** `ctx`
- **Out:** `("default", ctx)` (test now carries its model) | `("fail", result)`
- **Log idiom:** port-routed `fail` `result` on missing/malformed `models.yaml`; `log.error` at emission. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

### `expand-sweep`  · tags: expand · contract: `default` (persistent: `root_cfg`)
Reimplements `_expand_tests_with_sweep`'s `exec` pattern. No sweep → emit the one `ctx`
unchanged. Else yield one refined `ctx` per produced `TestConfig`.

- **In:** `ctx`, `root_cfg`
- **Out:** `("default", ctx)` per variant (key suffixed `#i`) | `("fail", result)`
- **Log idiom:** port-routed `fail` `result` on sweep script `exec` crash; `log.error` at emission. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

---

## Per-test preparation

### `run-preproc`  · tags: pre · contract: `default` (persistent: `root_cfg`)
Reimplements `VlogSim.pre`: if the test has a `preproc` script, `exec` it to mutate the test.

- **In:** `ctx`, `root_cfg`
- **Out:** `("default", ctx)` | `("fail", result)`
- **Log idiom:** port-routed `fail` `result` on preproc script `exec` crash; `log.error` at emission. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

### `write-filelist`  · tags: compile · contract: `default`
Reimplements `VlogFilelist.write_output(unroll=True, deduplicate=True)`. Writes the filelist
to a **per-tag** path `run.{test_tag}.f` (computing `test_tag = re.sub(r"[^A-Za-z0-9_.-]",
"_", ctx["test"].get_name())`, the same regex `build-compile-cmd` uses) so concurrent tests
don't collide on a shared `run.f`. Emits the `ctx` unchanged **and** the filelist `Path` on a
second port (both consumed in lockstep by `build-compile-cmd`, which passes
`filelist["filelist"]` straight to `-f`, so no join and no naming change is needed there).

- **In:** `ctx`
- **Out:** `("ctx", ctx)`, `("filelist", {key, filelist})` | `("fail", result)`
- **Log idiom:** port-routed `fail` `result` on filelist generation failure (e.g. unresolved source file); `log.error` at emission. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).
- **Concurrency:** the per-tag `run.{test_tag}.f` name is the graph-local interim mitigation
  (TODO #30) that replaces the removed lock shim. The residual shared-CWD artefacts it cannot
  rename (non-verilator `simv`, `test.*` symlinks, tool-internal files) wait on the upstream
  per-invocation-subdir change — see [07 item 17](07-ambiguities-and-assumptions.md) and
  [05 — Interim CWD-collision posture](05-branching-and-results.md#interim-cwd-collision-posture--per-tag-artefact-naming).

---

## The reusable subprocess core

### `build-compile-cmd`  · tags: compile · contract: `default` (persistent: `builder_cfg`,`builder_mode`,`logs_dir`)
Assembles the compiler argv as `VlogSim.compile`:
`[exe] + compile_time_opts(mode) + (["--Mdir", obj_dir] if verilator) + plusdefines + ["-f", run.f]`.
Computes `test_tag`, `build_dir`, and `simv` for use in the argv and log paths; puts the
compile log paths into `command` so `run-process` redirects there. Folds `simv` into `ctx` so downstream nodes carry it without re-derivation; does not fold
`build_dir` (not needed downstream). Does not `mkdir` — `ensure-logs-dir` has already
bootstrapped the directory (env_ready chain).

- **In:** `ctx`, `filelist`, `builder_cfg`, `builder_mode:str = "debug"`, `logs_dir:str = "logs"`
- **Out:** `("ctx", ctx_with_simv)`, `("command", {key, argv, stdout_path, stderr_path})`

### `run-process`  · tags: compile, sim  ← **the reusable star**
Run a command's argv as an async subprocess, **redirecting** stdout/stderr to the files named
in the command (not buffering them in memory). Returns `rc`/`timed_out` and echoes the paths.
Redirecting means a timed-out run keeps whatever it wrote before the SIGQUIT, and memory is
bounded regardless of log size. Optionally enforces a timeout: SIGQUIT to the process group,
then SIGKILL after a `_TIMEOUT_GRACE_S` grace period, with `rc=4444` as the timeout sentinel
and `timed_out` set independently of `rc`. Used as two node instances (compile: no timeout;
sim: with timeout). See [specs/03-run-process.md](specs/03-run-process.md) for the full
lifecycle and cancellation semantics.

- **In:** `command:{key,argv,stdout_path,stderr_path}`, `timeout:float | None = None`, `env_ready:bool = True`
- **Out:** default → `proc:{key,rc,timed_out,stdout_path,stderr_path}`
- **Log idiom:** `log.critical` if the subprocess fails to *launch* (binary not on PATH, permission denied) — system-wide condition, not per-test. Non-zero `rc` and `timed_out` are not failures here; they are interpreted downstream by `interpret-compile` / `interpret-sim` as per-test results. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).
- **`env_ready`** is a generic persistent sequencing input. The default `True` keeps the module testable in isolation (and the graph valid if no env-setup nodes are wired); in the production graph it carries the `bool` signal from `prepend-cwd-path` (and any future env-setup node) so the PATH mutation strictly precedes the first subprocess. The value is never read or branched on. Pairs with [07 settled 25](07-ambiguities-and-assumptions.md).

```python
class RunProcessMod:
    async def run(self, command:dict, timeout:float | None = None):
        with open(command["stdout_path"], "wb") as out, open(command["stderr_path"], "wb") as err:
            proc = await asyncio.create_subprocess_exec(*command["argv"],
                     stdout=out, stderr=err, preexec_fn=os.setpgrp)
            timed_out = False
            try:
                await asyncio.wait_for(proc.wait(), timeout)
                rc = proc.returncode
            except asyncio.TimeoutError:
                # spec 03 step 3a: SIGQUIT to group, grace, SIGKILL escalation
                rc, timed_out = 4444, True
        return { "key": command["key"], "rc": rc, "timed_out": timed_out,
                 "stdout_path": command["stdout_path"], "stderr_path": command["stderr_path"] }
```

It emits **paths, not open handles** — the files close when the process exits and live
handles don't survive across async queue edges; downstream re-opens by path. The opaque `key`
is carried for correlation only — `run-process` never reads or branches on it.

### `interpret-compile`  · tags: compile · contract: `keyed_join` (`key_field: key`)
Joins the direct `ctx` edge (carrying `simv` set by `build-compile-cmd`) with the
subprocess `proc` by key. `rc == 0` → emit `ok` (`ctx` unchanged, `simv` already present).
`rc != 0` → emit `fail` (`CompileFailResults`; reads `proc["stderr_path"]`/`stdout_path`
and logs at ERROR). Takes only the two keyed ports — no config port, since `keyed_join`
joins *every* port by key.

- **In:** `ctx`, `proc`
- **Out:** `("ok", ctx)` | `("fail", result)`
- **Log idiom:** port-routed `fail` `result` (`CompileFailResults`) when `rc != 0`; `log.error` at emission with the compile `rc` and stderr path. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

---

## Run expansion (fan-out per run-id)

### `expand-runs`  · tags: sim · contract: `default` (persistent: `run_ids`)
One compiled test → one `ctx` per run-id, yielding a fresh `ctx` with `key` suffixed
`#run_id` and `run_id` set. For `test`, `run_ids=[None]` → a single passthrough with
`run_id=None` and key unchanged.

- **In:** `ctx`, `run_ids=[None]`
- **Out:** default → `ctx` per run-id (fresh dict; `run_id` set; key suffixed when `run_id is not None`)

---

## Simulation

### `resolve-seed`  · tags: sim · contract: `default` (persistent: `seed_mode`,`builder_cfg`,`logs_dir`)
`VlogSim.execute` seed logic: `NEW`→`random.randrange(1_000_000)`,
`DEFAULT`→`builder_cfg.get_seed()`, `REPLAY`→read `<logs_dir>/<test>[_NNNN].randseed`
(default `logs/...`, matching rtl_buddy). Emits `ctx` unchanged and the seed payload
in lockstep so `build-sim-cmd` receives both from the same upstream without a join.

- **In:** `ctx`, `seed_mode`, `builder_cfg`, `logs_dir:str = "logs"`
- **Out:** `("ctx", ctx)`, `("seed", {key, seed})` | `("fail", result)` *(REPLAY only)*
- **Log idiom:** port-routed `fail` `result` in REPLAY mode when `<logs_dir>/<test>[_NNNN].randseed` is missing or malformed; `log.error` at emission with the path. `NEW`/`DEFAULT` modes have no failure path. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

### `build-sim-cmd`  · tags: sim · contract: `default` (persistent: `builder_cfg`,`builder_mode`,`logs_dir`)
`VlogSim.execute` argv: `[simv] + run_time_opts(mode, seed) + plusdefines + plusargs`; also
computes the per-test `timeout` from `TestConfig.get_timeout()` and the sim log/randseed
paths. Reads `simv` from `ctx["simv"]` (set by `build-compile-cmd`).
Puts log paths into `command` so `run-process` redirects there, and into `sim_cmd` so
`write-randseed` and the post-sim chain have them without a persistent config port.
Does not `mkdir` — `ensure-logs-dir` has already done so.

- **In:** `ctx`, `seed`, `builder_cfg`, `builder_mode`, `logs_dir:str = "logs"`
- **Out:** `("ctx", ctx)` (unchanged), `("sim_cmd", {key, seed, log, err, randseed_path})`, `("command", {key, argv, stdout_path, stderr_path})`, `("timeout", float)`

*(then `run-process` again, wired with the `timeout` input)*

> The sim `.log`/`.err` are written by `run-process` itself (it redirects there), so there
> is no separate "write-sim-logs" module — the log writer **is** the generic runner. The two
> remaining post-sim concerns (per directive 1: randseed and symlinks are distinct) become
> their own nodes. The first of them holds the `ctx ⋈ proc` join.

### `write-randseed`  · tags: sim · contract: `keyed_join` (`key_field: key`)
The sim's join point: correlates `ctx` (the stable identity record), `proc` (the subprocess
result), and `sim_cmd` (the pre-composed sim paths) by key. Writes `sim_cmd["randseed_path"]`
from `sim_cmd["seed"]` (plus `HierInstanceSeed.txt` contents when present). Then assembles
and emits `test_run` — the single post-sim context record consumed by all downstream nodes.
The directory was created at startup by `ensure-logs-dir`.

- **In:** `ctx`, `proc`, `sim_cmd` (3-port `keyed_join`)
- **Out:** default → `test_run`

### `link-latest`  · tags: sim · contract: `default`
Force the stable `test.log`/`test.err`/`test.randseed` symlinks in CWD to this run's files
(paths from `test_run`). Runs after `write-randseed` so the `.randseed` target exists.
Distinct functionality from randseed writing.

- **In:** `test_run`
- **Out:** default → `test_run`

### `interpret-sim`  · tags: sim · contract: `default`
Pure routing on the joined result: `timed_out` → `timeout` (`SimTimeoutResults`), else `ok`.
No side-effects — the artifacts were written upstream.

- **In:** `test_run`
- **Out:** `("ok", test_run)` | `("timeout", result)`
- **Log idiom:** port-routed `timeout` `result` (`SimTimeoutResults`) when `timed_out` is set; `log.error` at emission with the sim stderr path. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

---

## Post-processing

### `route-post`  · tags: post · contract: `default`
Classifies on `test_run["test"].uvm`: emit `uvm` when a `UVMConfig` is present, else
`plain`. Pure data classification expressed as a named-port return — not scheduling. This
is the only place the uvm/plain decision lives.

- **In:** `test_run`
- **Out:** `("uvm", test_run)` | `("plain", test_run)`

### `parse-log`  · tags: post · contract: `default`
Reimplements `VlogPost` with corrections (see [07 settled 15](07-ambiguities-and-assumptions.md)):
the `PASS/FAIL/ERR/FAT` regex scan on `test_run["log"]`. Emits `{key, result}`.

- **In:** `test_run`
- **Out:** default → `result`
- **Log idiom:** port-routed `result`; `log.error` at emission when the parsed result is FAIL. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).
- **Note:** no `postproc` script is run (parity with rtl_buddy). See [07 settled 14](07-ambiguities-and-assumptions.md).

### `parse-uvm-log`  · tags: post · contract: `default`
Reimplements `UvmVlogPost`: parse the UVM Report Summary severity counts from
`test_run["log"]` and compare against `test_run["test"].uvm.max_warns`/`max_errors`
(FATAL must be 0). Emits `{key, result}`.

- **In:** `test_run`
- **Out:** default → `result`
- **Log idiom:** port-routed `result`; `log.error` at emission when the parsed result is FAIL. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

---

## Control / aggregation

### `early-stop-gate`  · tags: (cross-cutting) · contract: `default` (persistent: `early_stop`)
Compare the global `early_stop` phase against this gate's configured `phase`. Stop here →
emit `stop` (`EarlyStopResults`); else `go`. Three instances differing only in config.
The work port is named `payload` so it accepts either `ctx` (gate-pre, gate-comp) or
`test_run` (gate-sim) without a signature change.

- **In:** `payload`, `early_stop:str = "post"`
- **Config:** `phase:str` (`pre`|`comp`|`sim`)
- **Out:** `("go", payload)` | `("stop", result)`
- **Log idiom:** port-routed `stop` `result` (`EarlyStopResults`); no log call (a normal terminal, not a failure). See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

### ~~`fan-in-results`~~ / ~~`aggregate-results`~~ — removed (TODO #15)

> **Removed by the TODO #15 redesign (2026-06-10).** Both nodes are gone. The summary table
> and the exit code are no longer produced by a graph sink:
>
> - **Summary** is rendered by a per-graph `SummaryHandler` (`logging.Handler` plugin in
>   `log/summary.py`) from the `test_result` rows that each terminal node now logs at
>   emission, plus the `git_state` event from `git-status`. It renders in its `finalise()`
>   teardown hook (`App.cleanup`). See
>   [05 — Re-convergence](05-branching-and-results.md#re-convergence-the-summary-is-a-logging-concern-not-a-graph-node).
> - **Exit code** is driven solely by the per-emission `log.error` at each failure site —
>   the old belt-and-braces `aggregate-results.finalise()` `log.error` is gone.
> - The 13 terminal ports that used to feed `fan-in-results` are now **unwired** (the
>   harness logs `no_destination` at INFO); their modules' signatures are unchanged.
>
> The `any` contract that `fan-in-results` used is retained as a reusable (plain) contract but
> has no consumer in the `test` graph. The `SummaryHandler` / `drop_summary_events` plugin is
> specified in [spec 10](specs/10-control-aggregate-modules.md). (The interim parallel-safety
> lock shim that once hung off `any.release_lock` was removed entirely by
> [TODO #30](../implementation-test-todos.md) in favour of per-tag artefact naming.)

## Module → rtl_buddy provenance

All modules **reimplement** the rtl_buddy source natively; only the config schema is kept
identical (07, item 1).

| module | reimplements (rtl_buddy source) |
|---|---|
| `discover-config-file` | `_discover_root_cfg` upward walk |
| `prepend-cwd-path` | `rtl_buddy.py:100-102` `os.environ["PATH"]` prepend |
| `ensure-logs-dir` | `tools/vlog_sim.py:55-59` `output_dir = "logs"` lazy mkdir (lifted to setup) |
| `parse-root-config` | `RootConfigFile` deserialisation |
| `select-platform` | `RootConfig` `uname`/platform match |
| `resolve-builder` | `PlatformConfig.initialise` builder resolution |
| `parse-suite-config` | `SuiteConfigFile` parse + testbench bind |
| `load-model` | `ModelConfigLoader.get_model` (per test) |
| `derive-seed-mode` | `rnd_new/rnd_last` → `SeedMode` in `do_cmd_test` |
| `route-list-mode` | the `--list` branch in `do_cmd_test` |
| `list-test-names` | `--list` echo of `get_test_names()` |
| `select-tests` | `SuiteConfig.get_tests` |
| `filter-reglvl` | `_do_test_suite` level filter + `SkipResults` |
| `expand-sweep` | `_expand_tests_with_sweep` |
| `run-preproc` | `VlogSim.pre` |
| `write-filelist` | `VlogFilelist.write_output` |
| `build-compile-cmd` | `VlogSim.compile` argv assembly |
| `run-process` | `VlogSim.compile`/`execute` subprocess + output redirect |
| `interpret-compile` | `VlogSim.compile` rc check + `CompileFailResults` |
| `expand-runs` | `TestRunner.run` vs `run_multiple` run-id loop |
| `resolve-seed` | `VlogSim.execute` seed resolution (all modes) |
| `build-sim-cmd` | `VlogSim.execute` argv + timeout |
| `write-randseed` | `VlogSim.execute` `.randseed` write |
| `link-latest` | `VlogSim.execute` `test.log`/`.err`/`.randseed` symlink forcing |
| `interpret-sim` | `VlogSim.execute` timeout check |
| `route-post` | the `if test.uvm` dispatch inside `VlogSim.post` |
| `parse-log` | `VlogPost` |
| `parse-uvm-log` | `UvmVlogPost` |
| `early-stop-gate` | `RunDepth`/`--early-stop` + `EarlyStopResults` |
| `git-status` | rtl_buddy git-state capture logged alongside test results |

> `fan-in-results` and `aggregate-results` were removed by the TODO #15 redesign — the
> `do_cmd_test` summary is now reproduced by the `SummaryHandler` logging plugin and the
> OR-accumulated exit by per-emission `log.error`. See the note above and
> [05](05-branching-and-results.md#re-convergence-the-summary-is-a-logging-concern-not-a-graph-node).
