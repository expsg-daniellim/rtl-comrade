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

> **Source citations.** Every module below carries a `Source:` line naming the rtl_buddy
> file and line range it reimplements. All ranges are anchored to **rtl_buddy `v1.4.0`**
> (commit `a69d962`; see [00 — Source baseline](00-overview.md)). Ranges bound the *behaviour*
> mirrored, not the enclosing class. If rtl_buddy is updated, re-verify every cited range.
> The same citations are propagated into the `specs/` tickets as `Compatibility source:`
> bullets — keep the two in sync.

---

## Setup / config

> **Reimplemented, not wrapped.** Per [07](07-ambiguities-and-assumptions.md) item 1, these
> modules reimplement `rtl_buddy`'s behaviour natively; only the **config schema** (the YAML
> field names/structure of `root_config.yaml`, `tests.yaml`, `models.yaml`) is preserved, so
> existing config files load drop-in. Reimplementing is what lets the monolithic loaders be
> split into the atomic, reusable nodes below.

### `discover-config-file`  · tags: setup · contract: `unit`
Walk up the directory tree from CWD for a filename, stopping at the filesystem root (no `.git`
boundary — rtl_buddy's `_discover_root_cfg` walks purely by `max_levels`). Generic and reusable
(the harness itself locates `rtl_comrade_config.yaml` this way).

- **Source:** `rtl_buddy/src/rtl_buddy/config/root.py:16-36` — `_discover_root_cfg`, the upward `os.path.dirname` walk bounded by `max_levels`, `log.fatal` when nothing is found.
- **Config:** `filename:str` (e.g. `root_config.yaml`), `max_levels:int = 8`
- **In:** — (zero-input; runs once)
- **Out:** default → `Path`
- **Log idiom:** `log.fatal` if no `root_config.yaml` found; immediate `SystemExit(1)`. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

### `prepend-cwd-path`  · tags: setup · contract: `unit`
Prepend `.` to `$PATH` so a CWD-local simulator (`simv`, `verilator`) is discoverable by
downstream subprocess invocations. Idempotent — skips the mutation if `.` is already on
`$PATH`. Mirrors `rtl_buddy/src/rtl_buddy/rtl_buddy.py:100-102`, where rtl_buddy does the
same once at CLI bootstrap; here it is a graph node so the responsibility is explicit.
Emits a `bool` token wired **directly** to each `run-process` on `env_ready` (no relay through
`ensure-logs`). The edge is marked `required: true` and `env_ready` is in each `run-process`'s
`persistent_inputs`: `required` suppresses the module default so the first subprocess **blocks**
until the PATH mutation is done (hard ordering), `persistent` replays the once-emitted token for
later invocations (see [07 settled 25](07-ambiguities-and-assumptions.md)). No failure path: dict mutation cannot meaningfully fail.

- **Source:** `rtl_buddy/src/rtl_buddy/rtl_buddy.py:100-102` — the `if not '.' in os.environ["PATH"].split(...)` guard + prepend in `RtlBuddy.__init__` (here lifted from CLI bootstrap into an explicit graph node).
- **In:** — (zero-input; runs once)
- **Out:** default → `bool` (always `True`; the receiver only uses it for sequencing)
- **Log idiom:** none (no failure path). See [07 settled 25](07-ambiguities-and-assumptions.md).

### `parse-root-config`  · tags: setup · contract: `unit`
Deserialise the root-config YAML into schema-compatible dataclasses (preserving rtl_buddy
field names: `rtl-buddy-filetype`, `cfg-rtl-builder`, `cfg-platforms`, …).

- **Source:** `rtl_buddy/src/rtl_buddy/config/root.py:38-48` — the `RootConfigFile`/`RootRtlField` `@serde` field renames; the `from_yaml(RootConfigFile, ...)` load at `root.py:84-90`.
- **In:** `path:Path`
- **Out:** default → `root_cfg`
- **Log idiom:** `log.fatal` on malformed YAML / schema mismatch. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

### `select-platform`  · tags: setup · contract: `unit`
Run `uname` and match it against each platform's `unames`; pick the platform. Side-effecting
(subprocess), runs once.

- **Source:** `rtl_buddy/src/rtl_buddy/config/root.py:107-118` — the `subprocess.run(["uname"])` call, the `for platform_cfg … for cfg_uname …` match loop, and the `log.fatal` when no platform matches (inside `RootConfig.__init__`).
- **In:** `root_cfg`
- **Out:** default → `platform_cfg`
- **Log idiom:** `log.fatal` if no platform's `unames` matches the current host. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

### `resolve-builder`  · tags: setup · contract: `unit`
Resolve the active `RtlBuilderConfig` from the root builders dict using the platform's declared
builder name (honouring the `--builder` override); critical if the named builder is missing.

- **Source:** `rtl_buddy/src/rtl_buddy/config/platform.py:63-84` (`PlatformConfigFile.initialise`: builder lookup + `builder_override` branch) resolving against `config/root.py:94`'s `rtl_builder_cfgs` dict. Verible resolution is dropped (R3).
- **In:** `root_cfg`, `platform_cfg`, `builder:str = ""`
- **Out:** default → `builder_cfg`
- **Log idiom:** `log.fatal` if the resolved name is missing from `root_cfg.rtl_builder_cfgs`. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

### `check-suite-cwd`  · tags: setup · contract: `unit`
Enforce the user-driven CWD convention: `rtl-comrade test`/`randtest` must be invoked from
the suite directory (matching `rtl_buddy`'s `do_cmd_test`, which never `chdir`s — only
`do_rtl_regression` does, per-suite). Resolves the CLI `test_config` against CWD and
fails fast if the resolved path's parent is not CWD. Emits the resolved suite-config `Path`
for `parse-suite-config` **and** the validated base directory `work_dir` (= `resolved.parent`)
for `ensure-logs-dir`. This is the **single artefact-location provider**: downstream writers
consume a resolved directory instead of re-deriving it from the ambient CWD, so relocating
artefacts (a future `--work-dir`, or regression's per-suite root) is a change to this node alone.

- **Source:** No direct rtl_buddy analogue — a new check (Notable divergence, see [07 settled 24](07-ambiguities-and-assumptions.md)). It enforces the CWD convention that `do_cmd_test` (`rtl_buddy/src/rtl_buddy/rtl_buddy.py:166-209`) silently assumes: that command never `chdir`s, unlike `do_rtl_regression`'s per-suite `os.chdir` at `rtl_buddy.py:404`.
- **In:** `test_config:str = "tests.yaml"`
- **Out:** default → `Path` (resolved suite-config path); work_dir → `Path` (validated base dir)
- **Log idiom:** `log.fatal` if (a) `(Path.cwd() / test_config).resolve().parent !=
  Path.cwd().resolve()` (CWD mismatch), or (b) the resolved path is not a file. See
  [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site). Not wired
  in the regression graph (regression `chdir`s per-suite — see
  [08](08-sibling-graphs.md)).

### `ensure-logs-dir`  · tags: setup · contract: `unit`
Bootstrap the artefact directory (`<work_dir>/logs` by default) that downstream subprocess
nodes and randseed writers redirect into, **and emit its resolved path as data** so the path
composers join onto a provided directory instead of the ambient CWD. Mirrors
`rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:55-59`
(`output_dir = "logs"; if not os.path.exists(...): os.makedirs(...)`), lifted out of
`VlogSim.__init__`'s per-test lazy mkdir into a single explicit setup node so no downstream
writer needs to `mkdir`, the directory is created exactly once per invocation, and artefact
location is decided once (by `check-suite-cwd`'s `work_dir`). Takes `work_dir:Path` from
`check-suite-cwd` (the validated base directory — **load-bearing**, joined under `logs_dir`,
so a missing edge fails edge-validation) and the CLI `logs_dir` **subdir name** (with `--logs-dir`
default `"logs"` — a small **Notable divergence** from rtl_buddy, which has no override; see
[07](07-ambiguities-and-assumptions.md)). Emits the resolved directory `Path` on `logs_dir` (a
first-run-required persistent input consumed by `cc-build`/`sim-build`/`seed`). It carries **no**
`env_ready` token: because it `mkdir`s *before* emitting `logs_dir` and the composers block on that
value before building a command, the directory provably exists before any subprocess redirects into
it — the `logs_dir` data edge orders the `mkdir` for free, and the PATH prepend is sequenced
separately by `prepend-cwd-path → run-process.env_ready` (`required: true`,
[07 settled 25](07-ambiguities-and-assumptions.md)). Idempotent (`mkdir(parents=True,
exist_ok=True)`) — accepts nested names. Not wired in the regression graph (regression `chdir`s
per-suite — see [08](08-sibling-graphs.md)).

- **Source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:55-59` — the `output_dir = "logs"; if not os.path.exists(...): os.makedirs(...)` block in `VlogSim.__init__` (lifted out of the per-test lazy mkdir into a single setup node; rooting on `work_dir`, emitting the resolved path, and the `--logs-dir` override are Notable divergences, [07 settled 26](07-ambiguities-and-assumptions.md)).
- **In:** `work_dir:Path`, `logs_dir:str = "logs"` (subdir name)
- **Out:** logs_dir → `Path` (resolved artefact dir; first-run-required at consumers)
- **Log idiom:** `log.info("logs_dir_ready", path=...)` once; no failure port. `OSError` /
  `PermissionError` from `mkdir` propagate uncaught and surface as a harness CRITICAL via
  the bubbling-SystemExit catch (same idiom as `discover-config-file`'s `PermissionError`).
  See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site) and
  [07 settled 26](07-ambiguities-and-assumptions.md).

### `parse-suite-config`  · tags: setup · contract: `unit`
Deserialise `tests.yaml` into the schema-compatible suite (testbenches + tests), binding each
test to its testbench (within-file) and recording the suite directory on each test so
`load-model` can resolve `model_path` later. Model loading is deferred to `load-model`.

- **Source:** `rtl_buddy/src/rtl_buddy/config/suite.py:26-50` — `SuiteConfig.__init__`: `from_yaml(SuiteConfigFile, ...)`, the testbench bind `tbs = {tb.get_name(): tb for tb in data.testbenches}` (`suite.py:40`), and `test.initialise(config_dir, tbs)` (`suite.py:46`). Per-test `initialise` at `config/test.py:320-323`. (this plan defers `load-model`, which rtl_buddy does eagerly at `test.py:322`.)
- **In:** `test_config_path:Path` (resolved by `check-suite-cwd` in test/randtest, or by
  `parse-reg-config` in regression — see [08](08-sibling-graphs.md))
- **Out:** default → `suite_cfg`
- **Log idiom:** `log.fatal` on `tests.yaml` missing/malformed or testbench bind failure. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

### `derive-seed-mode`  · tags: setup · contract: `unit`
Collapse the two bool flags into one `SeedMode` (`rnd_new` wins, else `DEFAULT`).

- **Source:** `rtl_buddy/src/rtl_buddy/rtl_buddy.py:188-194` — the `seed_mode = SeedMode.DEFAULT … if rnd_new: NEW elif rnd_last: REPLAY` block in `do_cmd_test`; the enum is `seed_mode.py:4-7`.
- **In:** `rnd_new:bool = False`, `rnd_last:bool = False`
- **Out:** default → `SeedMode`

### `git-status`  · tags: setup · contract: `unit`
Record the repository's git state once at run start, for reproducibility and bug triage
(rtl_buddy logs git state alongside results). Zero-input; reads `git` via subprocess (or
`subprocess.run(["git", "rev-parse", ...])`) and emits a single structured log event
`log.info("git_state", branch=..., sha=..., dirty=...)`. It routes **nothing through the
graph**: the `git_state` event falls through the `SummaryProcessor` logging plugin (which
accumulates results only) to the console, printing at run start (see
[05 — Re-convergence](05-branching-and-results.md#re-convergence-the-summary-is-a-logging-concern-not-a-graph-node)).
This is the resolution of TODO #15 — git state is recorded as a logging concern, not a
graph-routed payload, which is what makes it a one-line setup node.

- **Source:** `rtl_buddy/src/rtl_buddy/rtl_buddy.py:500-522` — `show_git_rev`: the `git status -sb` / `git log -1 --pretty=%h` subprocess calls and the branch/mod/staged derivation (here emitted as one structured `log.info("git_state", ...)` rather than printed).
- **In:** — (zero-input; runs once)
- **Out:** default → `bool` (always `True`; unwired — the node exists only for its `log.info`
  side-effect, so the harness logs `no_destination` at INFO)
- **Log idiom:** `log.info("git_state", ...)` once. Not in a git repo / `git` missing →
  `log.warning("git_state_unavailable", ...)` and emit nothing collectable; **never**
  `log.error`/`log.fatal` (git state is informational, not a run gate). See
  [07 settled 27](07-ambiguities-and-assumptions.md).

---

## Selection / expansion (fan-out)

### `route-list-mode`  · tags: select · contract: `unit`
Routes on the `--list` flag (a global mode): `list` → the `list-test-names` terminal,
`run` → `select-tests`. A pure named-port classifier, so neither downstream needs a guard.

- **Source:** `rtl_buddy/src/rtl_buddy/rtl_buddy.py:182-184` — the `if list_tests: typer.echo(...); raise typer.Exit(0)` branch in `do_cmd_test` (here split into a classifier + a separate `list-test-names` terminal).
- **In:** `suite_cfg`, `list:bool = False`
- **Out:** `("run", suite_cfg)` | `("list", suite_cfg)`

### `list-test-names`  · tags: select · contract: `default`
Print the suite's test names. Terminal — emits nothing, so in list-mode the whole pipeline
drains and exits 0. `default` (not `unit`) so the unfired branch in run-mode drains an empty
stream silently — see [04 — Why each contract](04-pipeline-and-contracts.md#default--the-post-branch-run-once-nodes-select-list-names).

- **Source:** `rtl_buddy/src/rtl_buddy/rtl_buddy.py:183` — `typer.echo("  ".join(self.suite_cfg.get_test_names()))`; `get_test_names` is `config/suite.py:69-76`.
- **In:** `suite_cfg`
- **Out:** none

### `select-tests`  · tags: select · contract: `default`
Select one test or all (`get_tests(test_name)`) and yield one `ctx` per test, stamping
`key`. No mode logic — `--list` is handled upstream by `route-list-mode`. `default` (not `unit`)
so the unfired `run` branch in list-mode drains an empty stream silently — see
[04 — Why each contract](04-pipeline-and-contracts.md#default--the-post-branch-run-once-nodes-select-list-names).

- **Source:** `rtl_buddy/src/rtl_buddy/config/suite.py:52-67` — `SuiteConfig.get_tests`: returns `[self.tests[test_name]]` for a named test (with `log.fatal` if absent) or `self.tests.values()` for all.
- **In:** `suite_cfg`, `test_name:str = ""`
- **Out:** default → `ctx` per test
- **Log idiom:** `log.fatal` if `test_name` is given but not found in the suite (matches `rtl_buddy`'s `typer.Abort`). See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

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

- **Source:** `rtl_buddy/src/rtl_buddy/rtl_buddy.py:349-357` — the `_do_test_suite` level filter (`t_lvl > reg_level` / `t_lvl < start_level` → `_append_skip_results`). Level resolution is `TestConfig.get_reglvl` at `config/test.py:287-299`; the SKIP payload is `SkipResults` at `runner/test_results.py:71-78`.
- **In:** `ctx`, `builder_cfg`, `reg_level=None`, `start_level=None`
- **Out:** `("keep", ctx)` | `("skip", result)`
- **Log idiom:** port-routed `skip` `result`; no log call (SKIP is pass-like via `is_pass()`). See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

### `load-model`  · tags: select · contract: `default`
Load the test's `models.yaml` (resolving `model_path` relative to the suite dir recorded by
`parse-suite-config`) and attach the `ModelConfig` to `ctx["test"]`. Deferred from suite
parse so it is per-test and reusable (the `filelist` command needs the same step).

- **Source:** `rtl_buddy/src/rtl_buddy/config/model.py:66-100` — `ModelConfigLoader.__init__` (`from_yaml(ModelConfigFile, ...)`) + `get_model` (name lookup, `model.path` stamp, not-found path). This plan **raises** here instead of rtl_buddy's `log.fatal` so the module can route a per-test FAIL ([07 settled 10](07-ambiguities-and-assumptions.md)).
- **In:** `ctx`
- **Out:** `("default", ctx)` (test now carries its model) | `("fail", result)`
- **Log idiom:** port-routed `fail` `result` on missing/malformed `models.yaml`; `log.error` at emission. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

### `expand-sweep`  · tags: expand · contract: `default` (persistent: `root_cfg`)
Reimplements `_expand_tests_with_sweep`'s `exec` pattern. No sweep → emit the one `ctx`
unchanged. Else yield one refined `ctx` per produced `TestConfig`.

- **Source:** `rtl_buddy/src/rtl_buddy/rtl_buddy.py:264-283` — `_expand_tests_with_sweep`: the no-sweep early return, the `exec(code, ns)` of the sweep script with the `{logger, TestConfig, test_cfg, root_cfg, out_test_cfgs}` namespace, and `return ns["out_test_cfgs"]`.
- **In:** `ctx`, `root_cfg`
- **Out:** `("default", ctx)` per variant (key suffixed `#i`) | `("fail", result)`
- **Log idiom:** port-routed `fail` `result` on sweep script `exec` crash; `log.error` at emission. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

---

## Per-test preparation

### `run-preproc`  · tags: pre · contract: `default` (persistent: `root_cfg`)
Reimplements `VlogSim.pre`: if the test has a `preproc` script, `exec` it to mutate the test.

- **Source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:119-139` — `VlogSim.pre`: the no-preproc early return and the `exec(code, ns)` of the preproc script with the `{logger, test_cfg, root_cfg}` namespace.
- **In:** `ctx`, `root_cfg`
- **Out:** `("default", ctx)` | `("fail", result)`
- **Log idiom:** port-routed `fail` `result` on preproc script `exec` crash; `log.error` at emission. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

### `write-filelist`  · tags: compile · contract: `default` (persistent: `work_dir`)
Reimplements `VlogFilelist.write_output(unroll=True, deduplicate=True)`. Writes the filelist
to a **per-tag** path `Path(work_dir) / f"run.{test_tag}.f"` (computing `test_tag =
re.sub(r"[^A-Za-z0-9_.-]", "_", ctx["test"].get_name())`, the same regex `build-compile-cmd`
uses) so concurrent tests don't collide on a shared `run.f`, rooted on the `work_dir` provider
(`check-suite-cwd`) rather than the ambient CWD. Emits the `ctx` unchanged **and** the filelist
`Path` on a
second port (both consumed in lockstep by `build-compile-cmd`, which passes
`filelist["filelist"]` straight to `-f`, so no join and no naming change is needed there).

- **Source:** `rtl_buddy/src/rtl_buddy/tools/vlog_filelist.py:137-159` — `VlogFilelist.write_output` (model + test filelist `_extract`, `_process`, write). Called from `VlogSim._write_filelist` at `tools/vlog_sim.py:88-93` with `unroll=True, deduplicate=True`. The per-tag `run.{test_tag}.f` name is a divergence in this plan (rtl_buddy hard-codes `"run.f"` at `vlog_sim.py:157`).
- **In:** `ctx`, `work_dir:Path` (validated base dir from `check-suite-cwd`; **load-bearing** persistent input)
- **Out:** `("ctx", ctx)`, `("filelist", {key, filelist})` | `("fail", result)`
- **Log idiom:** port-routed `fail` `result` on filelist generation failure (e.g. unresolved source file); `log.error` at emission. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).
- **Concurrency:** the per-tag `run.{test_tag}.f` name is the graph-local interim mitigation
  (TODO #30) that replaces the removed lock shim; rooting it on `work_dir` (R14) brings it under
  the same artefact-location provider model as `logs/`. The residual shared-CWD artefacts neither
  covers (non-verilator configured `simv`, `test.*` symlinks, tool-internal files) wait on the
  upstream per-invocation-subdir change — see [07 item 17](07-ambiguities-and-assumptions.md) and
  [05 — Interim CWD-collision posture](05-branching-and-results.md#interim-cwd-collision-posture--per-tag-artefact-naming).

---

## The reusable subprocess core

### `build-compile-cmd`  · tags: compile · contract: `default` (persistent: `builder_cfg`,`builder_mode`,`logs_dir`,`work_dir`)
Assembles the compiler argv as `VlogSim.compile`:
`[exe] + compile_time_opts(mode) + (["--Mdir", obj_dir] if verilator) + plusdefines + ["-f", run.f]`.
Computes `test_tag`, `build_dir = str(Path(work_dir) / f"obj_dir_{test_tag}")` (rooted on the
`work_dir` provider, not the ambient CWD), and `simv` for use in the argv and log paths; puts the
compile log paths into `command` so `run-process` redirects there. Folds `simv` into `ctx` so downstream nodes carry it without re-derivation; does not fold
`build_dir` (not needed downstream). Does not `mkdir` — `ensure-logs-dir` has already
bootstrapped the directory, and this node blocks on its `logs_dir` (first-run-required) before
composing the command, so the directory exists by the time `run-process` redirects into it.

- **Source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:141-159` — `VlogSim.compile` argv assembly (`[get_exe()] + get_compile_time_opts(mode) + (["--Mdir", build_dir] if verilator) + plusdefines + ["-f", run.f]`), up to but excluding the `subprocess.run`. Supporting helpers: `_get_build_tag` regex `vlog_sim.py:65`, `_get_build_dir` `:67-71`, `_get_simv_path` verilator switch `:73-80`, `_get_plusdefines` `:107-117`.
- **In:** `ctx`, `filelist`, `builder_cfg`, `logs_dir:Path` (resolved artefact dir from `ensure-logs-dir`), `work_dir:Path` (validated base dir from `check-suite-cwd`), `builder_mode:str = "debug"`
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

- **Source:**
  - `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:162-179` — `VlogSim.compile`'s `subprocess.run(run_cmd, capture_output=True)` + `FileNotFoundError` handling (the no-timeout compile leg).
  - `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:240-281` — `VlogSim.execute`'s `Popen(preexec_fn=os.setpgrp, stdout=…, stderr=…)`, `process.wait(timeout)`, and the timeout→`SIGQUIT`/`rc=4444` block (the with-timeout sim leg). This plan diverges on signal target + SIGKILL escalation — see [specs/03-run-process.md](specs/03-run-process.md) and [07 settled 23](07-ambiguities-and-assumptions.md).
- **In:** `command:{key,argv,stdout_path,stderr_path}`, `timeout:float | None = None`, `env_ready:bool = True`
- **Out:** default → `proc:{key,rc,timed_out,stdout_path,stderr_path}`
- **Log idiom:** `log.fatal` if the subprocess fails to *launch* (binary not on PATH, permission denied) — system-wide condition, not per-test. Non-zero `rc` and `timed_out` are not failures here; they are interpreted downstream by `interpret-compile` / `interpret-sim` as per-test results. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).
- **`env_ready`** is a generic sequencing input. The Python default `True` keeps the module testable in isolation (and the graph valid if no env-setup node is wired). In the production graph the edge `prepend-cwd-path → run-process.env_ready` is marked **`required: true`** and the node lists `env_ready` in `persistent_inputs`: `required` suppresses the default so the **first** invocation blocks until the PATH mutation is done (a hard dependency, not best-effort), and `persistent` caches that single token and replays it for the streaming later invocations. Wired **directly** from `prepend-cwd-path` (no relay through `ensure-logs`). The value is never read or branched on. Pairs with [07 settled 25](07-ambiguities-and-assumptions.md).

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

- **Source:** `rtl_buddy/src/rtl_buddy/runner/test_runner.py:63-65` — the `compile_returncode != 0 → CompileFailResults` branch in `TestRunner.run`. The rc check + error dump it interprets is `tools/vlog_sim.py:168-171`; the FAIL payload is `CompileFailResults` at `runner/test_results.py:44-51`.
- **In:** `ctx`, `proc`
- **Out:** `("ok", ctx)` | `("fail", result)`
- **Log idiom:** port-routed `fail` `result` (`CompileFailResults`) when `rc != 0`; `log.error` at emission with the compile `rc` and stderr path. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

---

## Run expansion (fan-out per run-id)

### `expand-runs`  · tags: sim · contract: `default` (persistent: `run_ids`)
One compiled test → one `ctx` per run-id, yielding a fresh `ctx` with `key` suffixed
`#run_id` and `run_id` set. For `test`, `run_ids=[None]` → a single passthrough with
`run_id=None` and key unchanged.

- **Source:** `rtl_buddy/src/rtl_buddy/runner/test_runner.py:82-117` — `TestRunner.run_multiple`'s `for run_id in run_ids:` loop (vs the single-run `run` at `:51-80`); the `len(run_ids) == 1 → [run()] else run_multiple` dispatch is `rtl_buddy.py:297-299`. `run_ids` themselves are set in `do_cmd_test` (`rtl_buddy.py:188`, `[None]`).
- **In:** `ctx`, `run_ids=[None]`
- **Out:** default → `ctx` per run-id (fresh dict; `run_id` set; key suffixed when `run_id is not None`)

---

## Simulation

### `resolve-seed`  · tags: sim · contract: `default` (persistent: `seed_mode`,`builder_cfg`,`logs_dir`)
`VlogSim.execute` seed logic: `NEW`→`random.randrange(1_000_000)`,
`DEFAULT`→`builder_cfg.get_seed()`, `REPLAY`→read `<logs_dir>/<test>[_NNNN].randseed`
(default `logs/...`, matching rtl_buddy). Emits `ctx` unchanged and the seed payload
in lockstep so `build-sim-cmd` receives both from the same upstream without a join.

- **Source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:191-219` — `VlogSim.execute`'s seed resolution: REPLAY reads `<path>.randseed` with `(FileNotFoundError, ValueError)` handling (`:197-213`), NEW does `random.randrange(1000000)` (`:214-216`), DEFAULT uses `get_seed()` (`:218-219`). This plan routes REPLAY failure as a per-test FAIL `result` rather than rtl_buddy's inline FAIL-stub-and-return (`:203-212`).
- **In:** `ctx`, `seed_mode`, `builder_cfg`, `logs_dir:Path` (resolved artefact dir from `ensure-logs-dir`)
- **Out:** `("ctx", ctx)`, `("seed", {key, seed})` | `("fail", result)` *(REPLAY only)*
- **Log idiom:** port-routed `fail` `result` in REPLAY mode when `<logs_dir>/<test>[_NNNN].randseed` is missing or malformed; `log.error` at emission with the path. `NEW`/`DEFAULT` modes have no failure path. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

### `build-sim-cmd`  · tags: sim · contract: `default` (persistent: `builder_cfg`,`builder_mode`,`logs_dir`)
`VlogSim.execute` argv: `[simv] + run_time_opts(mode, seed) + plusdefines + plusargs`; also
computes the per-test `timeout` from `TestConfig.get_timeout()` and the sim log/randseed
paths. Reads `simv` from `ctx["simv"]` (set by `build-compile-cmd`).
Puts log paths into `command` so `run-process` redirects there, and into `sim_cmd` so
`write-randseed` and the post-sim chain have them without a persistent config port.
Does not `mkdir` — `ensure-logs-dir` has already done so.

- **Source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:195,221-235` — `VlogSim.execute` argv assembly (`[_get_simv_path()] + get_run_time_opts(mode, seed) + plusdefines + plusargs`) and `timeout, is_custom = test_cfg.get_timeout()`. `get_timeout` is `config/test.py:210-219`; `get_run_time_opts` (seed appended via `sim_rand_prefix`) is `config/rtl.py:104-123`.
- **In:** `ctx`, `seed`, `builder_cfg`, `builder_mode`, `logs_dir:Path` (resolved artefact dir from `ensure-logs-dir`)
- **Out:** `("ctx", ctx)` (unchanged), `("sim_cmd", {key, seed, log, err, randseed_path, argv})`, `("command", {key, argv, stdout_path, stderr_path})`, `("timeout", float)`. `argv` rides `sim_cmd` (as well as `command`) so the `write-randseed` `keyed_join` can run the `"hier_inst_seed" in argv` check — `keyed_join` cannot take a persistent config port (see [02 — Shape 2](02-payload-conventions.md), specs [08c](specs/08c-build-sim-cmd.md)/[08d](specs/08d-write-randseed.md)).

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

- **Source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:263-269` — the `with open(f"{log_path}.randseed", "w")` block in `VlogSim.execute`: writes the seed and appends `HierInstanceSeed.txt` when `hier_inst_seed` is in the run cmd.
- **In:** `ctx`, `proc`, `sim_cmd` (3-port `keyed_join`)
- **Out:** default → `test_run`

### `link-latest`  · tags: sim · contract: `default`
Force the stable `test.log`/`test.err`/`test.randseed` symlinks in CWD to this run's files
(paths from `test_run`). Runs after `write-randseed` so the `.randseed` target exists.
Distinct functionality from randseed writing.

- **Source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:271-273` — the three `force_symlink(f"{log_path}.{ext}", "test.{ext}")` calls in `VlogSim.execute`; the helper `force_symlink` (lexists-then-remove-then-symlink) is `vlog_sim.py:26-30`.
- **In:** `test_run`
- **Out:** default → `test_run`

### `interpret-sim`  · tags: sim · contract: `default`
Pure routing on the joined result: `timed_out` → `timeout` (`SimTimeoutResults`), else `ok`.
No side-effects — the artifacts were written upstream.

- **Source:** `rtl_buddy/src/rtl_buddy/runner/test_runner.py:72-73` — the `execute_returncode == 4444 → SimTimeoutResults` branch in `TestRunner.run`. The `rc=4444` sentinel is set in `tools/vlog_sim.py:258-261`; the FAIL payload is `SimTimeoutResults` at `runner/test_results.py:62-69`. This plan keys on the explicit `timed_out` flag rather than the magic `rc`.
- **In:** `test_run`
- **Out:** `("ok", test_run)` | `("timeout", result)`
- **Log idiom:** port-routed `timeout` `result` (`SimTimeoutResults`) when `timed_out` is set; `log.error` at emission with the sim stderr path. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

---

## Post-processing

### `route-post`  · tags: post · contract: `default`
Classifies on `test_run["test"].uvm`: emit `uvm` when a `UVMConfig` is present, else
`plain`. Pure data classification expressed as a named-port return — not scheduling. This
is the only place the uvm/plain decision lives.

- **Source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:293-298` — the `if self.test_cfg.uvm: UvmVlogPost(...) else: VlogPost(...)` dispatch in `VlogSim.post` (here a pure named-port classifier ahead of the two parse nodes).
- **In:** `test_run`
- **Out:** `("uvm", test_run)` | `("plain", test_run)`

### `parse-log`  · tags: post · contract: `default`
Reimplements `VlogPost` with corrections (see [07 settled 15](07-ambiguities-and-assumptions.md)):
the `PASS/FAIL/ERR/FAT` regex scan on `test_run["log"]`. Emits `{key, result}`.

- **Source:** `rtl_buddy/src/rtl_buddy/tools/vlog_post.py:23-45` — `VlogPost.get_results`: the per-line `^PASS` / `^FAIL` / `^(ERR|FAT):` searches and the `NA`/`FAIL`/`PASS` precedence. This plan **corrects** the quirks (PASS-after-FAIL override, partial-match `match_err` crash) — see [07 settled 15](07-ambiguities-and-assumptions.md).
- **In:** `test_run`
- **Out:** default → `result`
- **Log idiom:** port-routed `result`; `log.error` at emission when the parsed result is FAIL. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).
- **Note:** no `postproc` script is run (parity with rtl_buddy). See [07 settled 14](07-ambiguities-and-assumptions.md).

### `parse-uvm-log`  · tags: post · contract: `default`
Reimplements `UvmVlogPost`: parse the UVM Report Summary severity counts from
`test_run["log"]` and compare against `test_run["test"].uvm.max_warns`/`max_errors`
(FATAL must be 0). Emits `{key, result}`.

- **Source:** `rtl_buddy/src/rtl_buddy/tools/vlog_post.py:58-81` — `UvmVlogPost.get_results`: the `UVM Report Summary` regex, the severity-count `finditer`, the missing/invalid-summary FAILs, and the `WARNING <= max_warns and ERROR <= max_errors and FATAL <= 0` PASS rule. Thresholds come from `UVMConfig` (`config/uvm.py:3-19`).
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

- **Source:** `rtl_buddy/src/rtl_buddy/runner/test_runner.py:59-76` — the three `if self.run_depth == RunDepth.{PRE,COMP,SIM}: return EarlyStopResults(...)` checkpoints in `TestRunner.run`. The `RunDepth` enum is `test_runner.py:14-18`; the `--early-stop` flag is `rtl_buddy.py:121`; the payload is `EarlyStopResults` at `runner/test_results.py:53-60`.
- **In:** `payload`, `early_stop:str = "post"`
- **Config:** `phase:str` (`pre`|`comp`|`sim`)
- **Out:** `("go", payload)` | `("stop", result)`
- **Log idiom:** port-routed `stop` `result` (`EarlyStopResults`); no log call (a normal terminal, not a failure). See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

### ~~`fan-in-results`~~ / ~~`aggregate-results`~~ — removed (TODO #15)

> **Removed by the TODO #15 redesign (2026-06-10).** Both nodes are gone. The summary table
> and the exit code are no longer produced by a graph sink:
>
> - **Summary** is rendered by a per-graph `SummaryProcessor` (a stateful structlog processor
>   in `log/summary.py`, **not** a `logging.Handler`) from the outcome events each terminal logs
>   at emission — `test_result` from the otherwise-silent paths, the failure terminals' own
>   `compile_failed`/`sim_timeout`/`*_failed` (collected via a `Config` watch-list) — **outcomes
>   only**. It renders the table in its `finalise()` teardown hook. The `git_state` event from
>   `git-status` is not collected; it falls through to the console. See
>   [05 — Re-convergence](05-branching-and-results.md#re-convergence-the-summary-is-a-logging-concern-not-a-graph-node).
> - **Exit code** is driven solely by the per-emission `log.error` at each failure site —
>   the old belt-and-braces `aggregate-results.finalise()` `log.error` is gone.
> - The 13 terminal ports that used to feed `fan-in-results` are now **unwired** (the
>   harness logs `no_destination` at INFO); their modules' signatures are unchanged.
>
> The `any` contract that `fan-in-results` used is retained as a reusable (plain) contract but
> has no consumer in the `test` graph. The `SummaryProcessor` plugin is
> specified in [spec 10](specs/10-control-aggregate-modules.md). (The interim parallel-safety
> lock shim that once hung off `any.release_lock` was removed entirely by
> [TODO #30](../implementation-test-todos.md) in favour of per-tag artefact naming.)

## Module → rtl_buddy provenance

All modules **reimplement** the rtl_buddy source natively; only the config schema is kept
identical (07, item 1). Paths below are relative to `rtl_buddy/src/rtl_buddy/`, anchored to
**v1.4.0** (`a69d962`).

This table is a **derived at-a-glance index**: it names the *primary* site each module
mirrors. The per-module `- **Source:**` line above remains authoritative — it carries the
full set of sites for multi-source modules (e.g. `run-process`, `interpret-compile`/`-sim`,
`build-compile-cmd`) and the supporting helpers. If the two ever disagree, the inline line
wins; keep this table in step when a range there changes.

| module | primary rtl_buddy site |
|---|---|
| `discover-config-file` | `config/root.py:16-36` — `_discover_root_cfg` |
| `prepend-cwd-path` | `rtl_buddy.py:100-102` — `RtlBuddy.__init__` PATH prepend |
| `parse-root-config` | `config/root.py:38-48` — `RootConfigFile` serde (load `:84-90`) |
| `select-platform` | `config/root.py:107-118` — `uname` / platform match |
| `resolve-builder` | `config/platform.py:63-84` — `PlatformConfigFile.initialise` |
| `check-suite-cwd` | *no analogue — new check (cf. `rtl_buddy.py:166-209` vs `do_rtl_regression` `:404`)* |
| `ensure-logs-dir` | `tools/vlog_sim.py:55-59` — `VlogSim.__init__` `logs/` mkdir |
| `parse-suite-config` | `config/suite.py:26-50` — `SuiteConfig.__init__` (+ bind) |
| `derive-seed-mode` | `rtl_buddy.py:188-194` — `do_cmd_test` seed-mode block |
| `git-status` | `rtl_buddy.py:500-522` — `show_git_rev` |
| `route-list-mode` | `rtl_buddy.py:182-184` — `do_cmd_test` `--list` branch |
| `list-test-names` | `rtl_buddy.py:183` + `config/suite.py:69-76` — `get_test_names` |
| `select-tests` | `config/suite.py:52-67` — `SuiteConfig.get_tests` |
| `filter-reglvl` | `rtl_buddy.py:349-357` — `_do_test_suite` filter (`get_reglvl` `config/test.py:287-299`) |
| `load-model` | `config/model.py:66-100` — `ModelConfigLoader` |
| `expand-sweep` | `rtl_buddy.py:264-283` — `_expand_tests_with_sweep` |
| `run-preproc` | `tools/vlog_sim.py:119-139` — `VlogSim.pre` |
| `write-filelist` | `tools/vlog_filelist.py:137-159` — `VlogFilelist.write_output` (`vlog_sim.py:88-93`) |
| `build-compile-cmd` | `tools/vlog_sim.py:141-159` — `VlogSim.compile` argv |
| `run-process` | `tools/vlog_sim.py:162-179` + `:240-281` — `compile`/`execute` subprocess |
| `interpret-compile` | `runner/test_runner.py:63-65` — compile-rc branch (`CompileFailResults` `runner/test_results.py:44-51`) |
| `expand-runs` | `runner/test_runner.py:82-117` — `run_multiple` run-id loop |
| `resolve-seed` | `tools/vlog_sim.py:191-219` — `VlogSim.execute` seed resolution |
| `build-sim-cmd` | `tools/vlog_sim.py:195,221-235` — `VlogSim.execute` argv + timeout |
| `write-randseed` | `tools/vlog_sim.py:263-269` — `.randseed` write |
| `link-latest` | `tools/vlog_sim.py:271-273` — `force_symlink` (helper `:26-30`) |
| `interpret-sim` | `runner/test_runner.py:72-73` — `rc==4444` branch (`SimTimeoutResults` `runner/test_results.py:62-69`) |
| `route-post` | `tools/vlog_sim.py:293-298` — `VlogSim.post` uvm dispatch |
| `parse-log` | `tools/vlog_post.py:23-45` — `VlogPost.get_results` |
| `parse-uvm-log` | `tools/vlog_post.py:58-81` — `UvmVlogPost.get_results` |
| `early-stop-gate` | `runner/test_runner.py:59-76` — `RunDepth` checkpoints (enum `:14-18`) |

For the rtl_buddy behaviour each departure in this plan leaves behind, see
[07 — Notable divergences](07-ambiguities-and-assumptions.md).

> `fan-in-results` and `aggregate-results` were removed by the TODO #15 redesign — the
> `do_cmd_test` summary (`rtl_buddy.py:203-207`) is now reproduced by the `SummaryProcessor`
> logging plugin and the OR-accumulated exit (`rtl_buddy.py:206`) by per-emission
> `log.error`. See
> [05](05-branching-and-results.md#re-convergence-the-summary-is-a-logging-concern-not-a-graph-node).
