# Module catalog

Each module is the smallest sensible unit of node-local work. Every `run()` parameter is
one input port the harness can see; branches are expressed as named output ports; **no
module contains scheduling** (no guards, no awareness of other items). Signatures follow
the repo style (no space before the annotation colon, British spelling). "Tags" are
documentation-level labels (the manifest has no tag field — see
[07](07-ambiguities-and-assumptions.md)); they replace the old phase structure.

Conventions: `test`, `model`, `simv`, `run_id`, `seed`, `timeout`, `filelist`, `command`, `proc`, `randseed`, `randseed_done`, `result`
are the split per-test/per-run payload shapes from [02](02-payload-conventions.md) (no `ctx`/`test_run`/`sim_cmd` bags). **Contract** is the recommended pairing
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

### `discover-config-file`  · tags: setup · contract: `default`
Walk up the directory tree from CWD for a filename, stopping at the filesystem root (no `.git`
boundary — rtl_buddy's `_discover_root_cfg` walks purely by `max_levels`). Generic and reusable
(the harness itself locates `rtl_comrade_config.yaml` this way).

- **Source:** `rtl_buddy/src/rtl_buddy/config/root.py:16-36` — `_discover_root_cfg`, the upward `os.path.dirname` walk bounded by `max_levels`, `log.fatal` when nothing is found.
- **Config:** `filename:str` (e.g. `root_config.yaml`), `max_levels:int = 8`
- **In:** — (zero-input; runs once)
- **Out:** default → `Path`
- **Log idiom:** `log.fatal` if no `root_config.yaml` found; immediate `SystemExit(1)`. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

### `prepend-cwd-path`  · tags: setup · contract: `default`
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

### `work-dir`  · tags: setup · contract: `default`
Provide the artefact **base directory** `work_dir` as a single data source so the leaf writers and
the subprocess `cwd` root on a *provided* directory instead of each reading the ambient CWD.
Zero-input; emits `work_dir = Path.cwd().resolve()`. For `test`/`randtest` that **is** the CWD —
faithful to `do_cmd_test`, which never `chdir`s (run here, output here): `logs/`, `run.<tag>.f`,
`obj_dir_<tag>/`, the `test.*` symlinks, and `HierInstanceSeed.txt` all land in CWD. `regression`
does **not** wire this node; it feeds the same `work_dir` ports a per-suite `suite_dir` from
`parse-suite-config`. The future `--work-dir` override lives here.

- **Source:** rtl_buddy `do_cmd_test` (`rtl_buddy.py:166-209`) never `chdir`s — the test command works in, and writes to, the ambient CWD. Contrast `do_rtl_regression`'s per-suite `os.chdir` (`rtl_buddy.py:404`), mirrored by regression's per-suite `work_dir`. (The suite-config path resolution the former `resolve-suite-config` node did is folded into `parse-suite-config`, which opens the file and derives `suite_dir` from it anyway.)
- **In:** (none)
- **Out:** default → `Path` (the artefact base = `Path.cwd().resolve()`)
- **Log idiom:** none (no I/O that can fail). Zero-input → `default` (not `unit`). Not wired in the
  regression graph (regression sources a per-suite `work_dir` — see [08](08-sibling-graphs.md)).

### `ensure-logs-dir`  · tags: setup · contract: `unit`
Bootstrap the artefact directory (`<work_dir>/logs` by default) that downstream subprocess
nodes and randseed writers redirect into, **and emit its resolved path as data** so the path
composers join onto a provided directory instead of the ambient CWD. Mirrors
`rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:55-59`
(`output_dir = "logs"; if not os.path.exists(...): os.makedirs(...)`), lifted out of
`VlogSim.__init__`'s per-test lazy mkdir into a single explicit setup node so no downstream
writer needs to `mkdir`, the directory is created exactly once per invocation, and artefact
location is decided once (by the `work-dir` provider's `work_dir`). Takes `work_dir:Path` from
the `work-dir` node (the artefact base — **load-bearing**, joined under `logs_dir`,
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
- **In:** `test_config:str = "tests.yaml"` (raw locator: CLI in test/randtest, or `parse-reg-config`'s
  suite path in regression — see [08](08-sibling-graphs.md)); the module resolves it against CWD itself
- **Out:** default → `suite_cfg`
- **Log idiom:** `log.fatal` on `tests.yaml` missing/malformed or testbench bind failure. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

### `derive-seed-mode`  · tags: setup · contract: `unit`
Collapse the two bool flags into one `SeedMode` (`rnd_new` wins, else `DEFAULT`).

- **Source:** `rtl_buddy/src/rtl_buddy/rtl_buddy.py:188-194` — the `seed_mode = SeedMode.DEFAULT … if rnd_new: NEW elif rnd_last: REPLAY` block in `do_cmd_test`; the enum is `seed_mode.py:4-7`.
- **In:** `rnd_new:bool = False`, `rnd_last:bool = False`
- **Out:** default → `SeedMode`

### `git-status`  · tags: setup · contract: `default`
Record the repository's git state once at run start, for reproducibility and bug triage
(rtl_buddy logs git state alongside results). Zero-input; reads `git` via subprocess (or
`subprocess.run(["git", "rev-parse", ...])`) and emits a single structured log event
`log.info("git_state", branch=..., sha=..., dirty=...)`. It routes **nothing through the
graph**: `git_state` is not a terminal result, so it does not reach `results-summary` — it
falls through to the console, printing at run start (see
[05 — Re-convergence](05-branching-and-results.md#re-convergence-the-summary-returns-as-a-graph-node)).
Git state is recorded as a log event, not a
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
Select one test or all (`get_tests(test_name)`) and yield one `test` edge per test (the bare
self-keyed `TestConfig`, `key` already `= name` from construction — select does not stamp it).
No mode logic — `--list` is handled upstream by `route-list-mode`. `default` (not `unit`)
so the unfired `run` branch in list-mode drains an empty stream silently — see
[04 — Why each contract](04-pipeline-and-contracts.md#default--the-post-branch-run-once-nodes-select-list-names).

- **Source:** `rtl_buddy/src/rtl_buddy/config/suite.py:52-67` — `SuiteConfig.get_tests`: returns `[self.tests[test_name]]` for a named test (with `log.fatal` if absent) or `self.tests.values()` for all.
- **In:** `suite_cfg`, `test_name:str = ""`
- **Out:** `("test", test)` per selected test (the bare self-keyed `TestConfig`, `.key` already `= name` from construction; no `run_id` yet)
- **Log idiom:** `log.fatal` if `test_name` is given but not found in the suite (matches `rtl_buddy`'s `typer.Abort`). See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

```python
class SelectTestsMod:
    def run(self, suite_cfg, test_name:str = ""):
        for t in suite_cfg.get_tests(test_name or None):
            yield ("test", t)                    # bare, self-keyed (key=name set at construction); run_id is born later, at expand-runs
```

### `filter-reglvl`  · tags: select · contract: `default` (persistent: `builder_cfg`,`reg_level`,`start_level`)
`TestConfig.get_reglvl(builder_cfg.get_name())`. Emits on `skip` (a `result` payload)
when outside the `[start_level, reg_level]` window, else forwards the `test` edge. For `test`,
`reg_level`/`start_level` default to `None`, so it always forwards `test`; the node exists
so `regression` reuses it. Only the builder *name* is read off `builder_cfg` (see spec
[01a](specs/01a-builder-schema.md)); the port carries the whole object — `resolve-builder`'s
single output — because there is no name-only port, not because this node needs more than the name.

- **Source:** `rtl_buddy/src/rtl_buddy/rtl_buddy.py:349-357` — the `_do_test_suite` level filter (`t_lvl > reg_level` / `t_lvl < start_level` → `_append_skip_results`). Level resolution is `TestConfig.get_reglvl` at `config/test.py:287-299`; the SKIP payload is `SkipResults` at `runner/test_results.py:71-78`.
- **In:** `test`, `builder_cfg`, `reg_level=None`, `start_level=None`
- **Out:** `("test", test)` (forwarded unchanged) | `("skip", result)`
- **Log idiom:** port-routed `skip` `result` (→ `results-summary`); on skip emits its `TestResult` (a skip is not an error, so no `log.error`; the summary row rides the payload). See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

### `load-model`  · tags: select · contract: `default`
Load the test's `models.yaml` (resolving `model_path` relative to the suite dir recorded by
`parse-suite-config`) and emit the resolved `ModelConfig` on its **own `model` edge** — it is
**not** stored on the test object (split-edge model; `keyed_join`ed at `write-filelist`).
Deferred from suite parse so it is per-test (the `filelist` command needs the model), but
positioned **after `filter` and before the `sweep`/`preproc` hooks** — they expose the resolved
`ModelConfig` to their scripts as `test_cfg.model` (rtl_buddy parity), so it must be resolved
first. The `model` edge then rides alongside `test` (re-keyed `#i` across the sweep fan-out) to
`write-filelist`, its final consumer.

- **Source:** `rtl_buddy/src/rtl_buddy/config/model.py:53-100` — `ModelConfigFile`/`ModelConfigLoader`. rtl_buddy's loader (read + name lookup + `path` stamp) is **unrolled into `run`** (the node is the unit of functionality); the read shape is split into a raw `ModelConfigFileItem` (no `path`) and the frozen runtime `ModelConfig` is **constructed** from the matched item with `path=str(resolved)` (no mutation). This plan **raises** instead of rtl_buddy's `log.fatal` so the module can route a per-test FAIL ([07 settled 10](07-ambiguities-and-assumptions.md)).
- **In:** `test`
- **Out:** `("test", test)` (forwarded unchanged) + `("model", {key, value})` (the resolved `ModelConfig`) | `("fail", result)`
- **Log idiom:** port-routed `fail` `result` on missing/malformed `models.yaml`; `log.error` at emission. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

### `expand-sweep`  · tags: expand · contract: `keyed_join` (`key_field: key`; persistent: `root_cfg`)
Reimplements `_expand_tests_with_sweep`'s `exec` pattern. `keyed_join`s the joined `model` edge
(from the now-upstream `load-model`) and, for the duration of the `exec`, sets `test_cfg.model`
to the resolved `ModelConfig` so the sweep script sees the same model view rtl_buddy gives it
(restored to the name string after). No sweep → forward the `test` **and** `model` edges
unchanged. Else yield one refined `test` edge per produced `TestConfig` plus its re-keyed `model`.

- **Source:** `rtl_buddy/src/rtl_buddy/rtl_buddy.py:264-283` — `_expand_tests_with_sweep`: the no-sweep early return, the `exec(code, ns)` of the sweep script with the `{logger, TestConfig, test_cfg, root_cfg, out_test_cfgs}` namespace, and `return ns["out_test_cfgs"]`.
- **In:** `test`, `model` (`keyed_join` by key — the resolved `ModelConfig` from `load-model`), `root_cfg`
- **Out:** `("test", variant)` + `("model", {key, value})` per variant (key suffixed `#i`) | `("fail", result)`
- **Log idiom:** port-routed `fail` `result` on sweep script `exec` crash; `log.error` at emission. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

---

## Per-test preparation

### `run-preproc`  · tags: pre · contract: `keyed_join` (`key_field: key`; persistent: `root_cfg`)
Reimplements `VlogSim.pre`: if the test has a `preproc` script, `exec` it to mutate the test in
place. `keyed_join`s the joined `model` edge and, for the duration of the `exec`, sets
`test_cfg.model` to the resolved `ModelConfig` (restored after) so the script sees rtl_buddy's
model view; mutations land on the real test. Forwards `test` **and** `model`.

- **Source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:119-139` — `VlogSim.pre`: the no-preproc early return and the `exec(code, ns)` of the preproc script with the `{logger, test_cfg, root_cfg}` namespace.
- **In:** `test`, `model` (`keyed_join` by key — the resolved `ModelConfig` from `load-model`), `root_cfg`
- **Out:** `("test", test)` + `("model", {key, value})` | `("fail", result)`
- **Log idiom:** port-routed `fail` `result` on preproc script `exec` crash; `log.error` at emission. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

### `write-filelist`  · tags: compile · contract: `keyed_join` (`key_field: key`; persistent: `work_dir`)
Reimplements `VlogFilelist.write_output(unroll=True, deduplicate=True)`. Writes the filelist
to a **per-tag** path `Path(work_dir) / f"run.{test_tag}.f"` (computing `test_tag =
re.sub(r"[^A-Za-z0-9_.-]", "_", test.get_name())`, the same regex `build-compile-cmd`
uses) so concurrent tests don't collide on a shared `run.f`, rooted on the `work_dir` provider
(`work-dir`) rather than the ambient CWD. Emits the `test` edge unchanged **and** the filelist
`Path` on a
second port (both consumed in lockstep by `build-compile-cmd`, which reads
`filelist.value` straight into `-f`). The resolved `ModelConfig` arrives on the joined
`model` edge from `load-model`, not on the test object.

- **Source:** `rtl_buddy/src/rtl_buddy/tools/vlog_filelist.py:137-159` — `VlogFilelist.write_output` (model + test filelist `_extract`, `_process`, write). Called from `VlogSim._write_filelist` at `tools/vlog_sim.py:88-93` with `unroll=True, deduplicate=True`. The per-tag `run.{test_tag}.f` name is a divergence in this plan (rtl_buddy hard-codes `"run.f"` at `vlog_sim.py:157`).
- **In:** `test`, `model` (`keyed_join` by key — the resolved `ModelConfig` from `load-model`), `work_dir:Path` (artefact base from `work-dir`; **load-bearing** persistent input)
- **Out:** `("test", test)`, `("filelist", {key, value})` | `("fail", result)`
- **Log idiom:** port-routed `fail` `result` on filelist generation failure (e.g. unresolved source file); `log.error` at emission. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).
- **Concurrency:** the per-tag `run.{test_tag}.f` name is the graph-local interim mitigation;
  rooting it on `work_dir` (R14) brings it under
  the same artefact-location provider model as `logs/`. The residual shared-CWD artefacts neither
  covers (non-verilator configured `simv`, `test.*` symlinks, tool-internal files) wait on the
  upstream per-invocation-subdir change — see [07 item 17](07-ambiguities-and-assumptions.md) and
  [05 — Interim CWD-collision posture](05-branching-and-results.md#interim-cwd-collision-posture--per-tag-artefact-naming).

---

## The reusable subprocess core

### `build-compile-cmd`  · tags: compile · contract: `keyed_join` (`key_field: key`; persistent: `builder_cfg`,`builder_mode`,`logs_dir`,`work_dir`)
Assembles the compiler argv as `VlogSim.compile`:
`[exe] + compile_time_opts(mode) + (["--Mdir", obj_dir] if verilator) + plusdefines + ["-f", run.f]`.
Computes `test_tag`, `build_dir = str(Path(work_dir) / f"obj_dir_{test_tag}")` (rooted on the
`work_dir` provider, not the ambient CWD), and `simv` for use in the argv and log paths; puts the
compile log paths into `command` so `run-process` redirects there. Emits `simv` on its own `{key, value}` edge so downstream nodes carry it without re-derivation; does not emit
`build_dir` (not needed downstream). Does not `mkdir` — `ensure-logs-dir` has already
bootstrapped the directory, and this node blocks on its `logs_dir` (first-run-required) before
composing the command, so the directory exists by the time `run-process` redirects into it.

- **Source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:141-159` — `VlogSim.compile` argv assembly (`[get_exe()] + get_compile_time_opts(mode) + (["--Mdir", build_dir] if verilator) + plusdefines + ["-f", run.f]`), up to but excluding the `subprocess.run`. Supporting helpers: `_get_build_tag` regex `vlog_sim.py:65`, `_get_build_dir` `:67-71`, `_get_simv_path` verilator switch `:73-80`, `_get_plusdefines` `:107-117`.
- **In:** `test`, `filelist` (`keyed_join` by key), `builder_cfg`, `logs_dir:Path` (resolved artefact dir from `ensure-logs-dir`), `work_dir:Path` (artefact base from `work-dir`), `builder_mode:str = "debug"`
- **Out:** `("test", test)`, `("simv", {key, value})`, `("command", {key, argv, stdout_path, stderr_path})`

### `run-process`  · tags: compile, sim  ← **the reusable star**
Run a command's argv as an async subprocess, **redirecting** stdout/stderr to the files named
in the command (not buffering them in memory). Returns `rc` (the child's return code, or `None`
on timeout) and echoes the paths. Redirecting means a timed-out run keeps whatever it wrote
before the SIGQUIT, and memory is bounded regardless of log size. Optionally enforces a timeout:
SIGQUIT to the process group, then SIGKILL after a `_TIMEOUT_GRACE_S` grace period, returning
`rc = None` as the timeout indicator. Used as two node instances (compile: no timeout;
sim: with timeout). See [specs/03-run-process.md](specs/03-run-process.md) for the full
lifecycle and cancellation semantics.

- **Source:**
  - `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:162-179` — `VlogSim.compile`'s `subprocess.run(run_cmd, capture_output=True)` + `FileNotFoundError` handling (the no-timeout compile leg).
  - `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:240-281` — `VlogSim.execute`'s `Popen(preexec_fn=os.setpgrp, stdout=…, stderr=…)`, `process.wait(timeout)`, and the timeout→`SIGQUIT`/`rc=4444` block (the with-timeout sim leg). This plan diverges on signal target + SIGKILL escalation, and returns `rc=None` rather than the `4444` sentinel — see [specs/03-run-process.md](specs/03-run-process.md) and [07 settled 23](07-ambiguities-and-assumptions.md).
- **In:** `command:{key,argv,stdout_path,stderr_path}`, `timeout:float | None = None`, `env_ready:bool = True`
- **Out:** default → `proc:{key,rc:int|None,stdout_path,stderr_path}` (`rc is None` ⟺ timed out)
- **Log idiom:** `log.fatal` if the subprocess fails to *launch* (binary not on PATH, permission denied) — system-wide condition, not per-test. Non-zero `rc` and `rc is None` (timeout) are not failures here; they are interpreted downstream by `interpret-compile` / `interpret-sim` as per-test results. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).
- **`env_ready`** is a generic sequencing input. The Python default `True` keeps the module testable in isolation (and the graph valid if no env-setup node is wired). In the production graph the edge `prepend-cwd-path → run-process.env_ready` is marked **`required: true`** and the node lists `env_ready` in `persistent_inputs`: `required` suppresses the default so the **first** invocation blocks until the PATH mutation is done (a hard dependency, not best-effort), and `persistent` caches that single token and replays it for the streaming later invocations. Wired **directly** from `prepend-cwd-path` (no relay through `ensure-logs`). The value is never read or branched on. Pairs with [07 settled 25](07-ambiguities-and-assumptions.md).

```python
class RunProcessMod:
    async def run(self, command:dict, timeout:float | None = None):
        with open(command.stdout_path, "wb") as out, open(command.stderr_path, "wb") as err:
            proc = await asyncio.create_subprocess_exec(*command.argv,
                     stdout=out, stderr=err, preexec_fn=os.setpgrp)
            try:
                await asyncio.wait_for(proc.wait(), timeout)
                rc = proc.returncode
            except asyncio.TimeoutError:
                # spec 03 step 3a: SIGQUIT to group, grace, SIGKILL escalation
                rc = None   # the timeout indicator
        return Proc(command.key, rc=rc, stdout_path=command.stdout_path, stderr_path=command.stderr_path)
```

It emits **paths, not open handles** — the files close when the process exits and live
handles don't survive across async queue edges; downstream re-opens by path. The opaque `key`
is carried for correlation only — `run-process` never reads or branches on it.

### `interpret-compile`  · tags: compile · contract: `keyed_join` (`key_field: key`)
Joins `test`, `simv` (born at `build-compile-cmd`), and the subprocess `proc` by key.
`rc == 0` → forward `test` and `simv` unchanged (co-gated, so `simv` proceeds only on compile
success and the downstream `expand-runs` join cannot dangle). `rc != 0` → emit `fail`
(`TestResult.compile_fail(key, test_name)`; reads `proc.stderr_path`/`stdout_path` and logs at ERROR), dropping
`test`/`simv`. Takes only the three keyed ports — no config port, since `keyed_join`
joins *every* port by key.

- **Source:** `rtl_buddy/src/rtl_buddy/runner/test_runner.py:63-65` — the `compile_returncode != 0 → CompileFailResults` branch in `TestRunner.run`. The rc check + error dump it interprets is `tools/vlog_sim.py:168-171`; the FAIL payload is `CompileFailResults` at `runner/test_results.py:44-51`.
- **In:** `test`, `simv`, `proc`
- **Out:** `("test", test)`, `("simv", simv)` | `("fail", result)`
- **Log idiom:** port-routed `fail` `result` (`TestResult.compile_fail`, `type_=COMPILE_FAIL`) when `rc != 0`; `log.error` at emission with the compile `rc` and stderr path. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

---

## Run expansion (fan-out per run-id)

### `expand-runs`  · tags: sim · contract: `keyed_join` (`key_field: key`; persistent: `run_ids`)
Joins `test`+`simv` at the test-level key, then per run-id re-emits a per-run
`dataclasses.replace(test, key=…)` copy of the `TestConfig` (one fresh object per run, sharing
`pa`/`pd`/`tb`), `run_id` (born here), and `simv` at a `key` suffixed `#run_id`. For `test`,
`run_ids=[None]` → a single copy with `run_id=None` and key unchanged.

- **Source:** `rtl_buddy/src/rtl_buddy/runner/test_runner.py:82-117` — `TestRunner.run_multiple`'s `for run_id in run_ids:` loop (vs the single-run `run` at `:51-80`); the `len(run_ids) == 1 → [run()] else run_multiple` dispatch is `rtl_buddy.py:297-299`. `run_ids` themselves are set in `do_cmd_test` (`rtl_buddy.py:188`, `[None]`).
- **In:** `test`, `simv` (joined by key), `run_ids=[None]`
- **Out:** `("test", replace(test, key=nk))`, `("run_id", {key, value})`, `("simv", simv)` per run-id (key re-suffixed `#run_id` when `run_id is not None`)

---

## Simulation

### `resolve-seed`  · tags: sim · contract: `keyed_join` (`key_field: key`; persistent: `seed_mode`,`builder_cfg`,`logs_dir`)
`VlogSim.execute` seed logic: `NEW`→`random.randrange(1_000_000)`,
`DEFAULT`→`builder_cfg.get_seed()`, `REPLAY`→read `<logs_dir>/<test>[_NNNN].randseed`
(default `logs/...`, matching rtl_buddy). Forwards `test`, `run_id`, `simv` unchanged and
emits the `seed` edge, all keyed so `build-sim-cmd` joins them.

- **Source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:191-219` — `VlogSim.execute`'s seed resolution: REPLAY reads `<path>.randseed` with `(FileNotFoundError, ValueError)` handling (`:197-213`), NEW does `random.randrange(1000000)` (`:214-216`), DEFAULT uses `get_seed()` (`:218-219`). This plan routes REPLAY failure as a per-test FAIL `result` rather than rtl_buddy's inline FAIL-stub-and-return (`:203-212`).
- **In:** `test`, `run_id`, `simv` (joined by key), `seed_mode`, `builder_cfg`, `logs_dir:Path` (resolved artefact dir from `ensure-logs-dir`)
- **Out:** `("test", test)`, `("run_id", run_id)`, `("simv", simv)`, `("seed", {key, value})` | `("fail", result)` *(REPLAY only)*
- **Log idiom:** port-routed `fail` `result` in REPLAY mode when `<logs_dir>/<test>[_NNNN].randseed` is missing or malformed; `log.error` at emission with the path. `NEW`/`DEFAULT` modes have no failure path. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

### `build-sim-cmd`  · tags: sim · contract: `keyed_join` (`key_field: key`; persistent: `builder_cfg`,`builder_mode`,`logs_dir`)
`VlogSim.execute` argv: `[simv] + run_time_opts(mode, seed) + plusdefines + plusargs`; also
computes the per-test `timeout` from `TestConfig.get_timeout()` and the sim log/randseed
paths. Reads `simv` from the `simv` edge (`simv.value`, born at `build-compile-cmd`).
Puts log paths into `command` (so `run-process` redirects there; `proc` later echoes them to
the post-sim chain), and the seed / randseed-path / argv into the cohesive `randseed` message
for `write-randseed`. Does not `mkdir` — `ensure-logs-dir` has already done so.

- **Source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:195,221-235` — `VlogSim.execute` argv assembly (`[_get_simv_path()] + get_run_time_opts(mode, seed) + plusdefines + plusargs`) and `timeout, is_custom = test_cfg.get_timeout()`. `get_timeout` is `config/test.py:210-219`; `get_run_time_opts` (seed appended via `sim_rand_prefix`) is `config/rtl.py:104-123`.
- **In:** `test`, `run_id`, `simv`, `seed` (joined) · persistent: `builder_cfg`, `builder_mode`, `logs_dir:Path` (resolved artefact dir from `ensure-logs-dir`)
- **Out:** `("test", test)` (forwarded), `("command", Command(key, argv, stdout_path, stderr_path))`, `("timeout", KeyedValue(key, float | None))`, `("randseed", RandSeed(key, seed, randseed_path, argv))`. `argv` rides `randseed` (as well as `command`) so the `write-randseed` `keyed_join` can run the `"hier_inst_seed" in argv` check — `keyed_join` cannot take a persistent config port (see [02 — Shape 2](02-payload-conventions.md), specs [08c](specs/08c-build-sim-cmd.md)/[08d](specs/08d-write-randseed.md)).

*(then `run-process` again, wired with the `timeout` input)*

> The sim `.log`/`.err` are written by `run-process` itself (it redirects there), so there
> is no separate "write-sim-logs" module — the log writer **is** the generic runner. The two
> remaining post-sim concerns (per directive 1: randseed and symlinks are distinct) become
> their own nodes. The first of them, `write-randseed`, holds the `randseed ⋈ proc` join (`proc` as a completion gate).

### `write-randseed`  · tags: sim · contract: `keyed_join` (`key_field: key`)
A post-sim **side-effect leaf**: persist the seed record. `keyed_join`s `randseed` with `proc`
— `proc` is a completion gate (joined so the sim has finished, but its `rc` goes
unread; that drives the parallel classification branch). Writes `randseed.randseed_path` from
`randseed.seed`, then appends `HierInstanceSeed.txt` **iff** `"hier_inst_seed" in randseed.argv`
(rtl_buddy parity). Emits a `("randseed_done", RandSeedDone(randseed.key))` ordering signal so
`link-latest` sequences after the file is on disk. **No `test_run` assembly** — the post-sim
split dissolved that bag (spec [08d](specs/08d-write-randseed.md)); this node reads neither
`test` nor `run_id` and builds no result record. The directory was created at startup by
`ensure-logs-dir`.

- **Source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:263-269` — the `with open(f"{log_path}.randseed", "w")` block in `VlogSim.execute`: writes the seed and appends `HierInstanceSeed.txt` when `hier_inst_seed` is in the run cmd.
- **In:** `randseed`, `proc` (gate) — 2-port `keyed_join`
- **Out:** `("randseed_done", RandSeedDone(randseed.key))`

### `link-latest`  · tags: sim · contract: `keyed_join` (`key_field: key`)
Force the stable `test.log`/`test.err`/`test.randseed` symlinks **under `work_dir`** to this run's
files (`log`/`err` from `proc.stdout_path`/`proc.stderr_path`, the randseed target from
`randseed.randseed_path`). `work_dir` (`work-dir`) is a persistent input, so the
pointers sit beside the `logs/` tree, not in the ambient CWD. The `randseed_done` ordering signal
sequences it after `write-randseed` so the `.randseed` target exists; it is otherwise unread.
Terminal leaf of the side-effect branch — distinct functionality from randseed writing.

- **Source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:271-273` — the three `force_symlink(f"{log_path}.{ext}", "test.{ext}")` calls in `VlogSim.execute`; the helper `force_symlink` (lexists-then-remove-then-symlink) is `vlog_sim.py:26-30`.
- **In:** `randseed`, `proc`, `randseed_done` (3-port `keyed_join`; `randseed_done` is the ordering gate)
- **Out:** none — terminal side-effect leaf

### `interpret-sim`  · tags: sim · contract: `keyed_join` (`key_field: key`)
Pure routing on `proc.rc is None`: on a clean run forward `test`+`proc` (co-gated for the
classification chain); on timeout drop them and emit a `TestResult.sim_timeout`. No side-effects —
the artifacts were written upstream.

- **Source:** `rtl_buddy/src/rtl_buddy/runner/test_runner.py:72-73` — the `execute_returncode == 4444 → SimTimeoutResults` branch in `TestRunner.run`. rtl_buddy's `4444` sentinel is set in `tools/vlog_sim.py:258-261`; the FAIL payload is `SimTimeoutResults` at `runner/test_results.py:62-69`. This plan keys on `proc.rc is None` rather than the magic `rc`.
- **In:** `test`, `proc` (joined by key)
- **Out:** `("test", test)` + `("proc", proc)` (clean run, co-gated) | `("timeout", TestResult.sim_timeout(key, test_name))`
- **Log idiom:** port-routed `timeout` `result` (`TestResult.sim_timeout`, `type_=SIM_TIMEOUT`) when `proc.rc is None`; `log.error` at emission with the sim stderr path. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

---

## Post-processing

### `route-post`  · tags: post · contract: `keyed_join` (`key_field: key`)
Classifies on `test.uvm`: route to the `uvm` branch when a `UVMConfig` is present, else
`plain`. `test`+`proc` are **co-routed** (both always go to the same parser, so the unchosen
parser's `keyed_join` can't dangle). Pure data classification expressed as a named-port
return — not scheduling. This is the only place the uvm/plain decision lives.

- **Source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:293-298` — the `if self.test_cfg.uvm: UvmVlogPost(...) else: VlogPost(...)` dispatch in `VlogSim.post` (here a pure named-port classifier ahead of the two parse nodes).
- **In:** `test`, `proc` (joined by key)
- **Out:** `("uvm_test", test)` + `("uvm_proc", proc)` | `("plain_test", test)` + `("plain_proc", proc)`

### `parse-log`  · tags: post · contract: `keyed_join` (`key_field: key`)
Reimplements `VlogPost` with corrections (see [07 settled 15](07-ambiguities-and-assumptions.md)):
the `PASS/FAIL/ERR/FAT` regex scan on `proc.stdout_path` (the log `proc` echoes). Emits the self-keyed `TestResult.parse(key, test_name, verdict, desc)` (`type_=PARSE`).

- **Source:** `rtl_buddy/src/rtl_buddy/tools/vlog_post.py:23-45` — `VlogPost.get_results`: the per-line `^PASS` / `^FAIL` / `^(ERR|FAT):` searches and the `NA`/`FAIL`/`PASS` precedence. This plan **corrects** the quirks (PASS-after-FAIL override, partial-match `match_err` crash) — see [07 settled 15](07-ambiguities-and-assumptions.md).
- **In:** `test`, `proc` (joined by key — plain branch of `route-post`)
- **Out:** default → `result`
- **Log idiom:** port-routed `result`; `log.error` at emission when the parsed result is FAIL. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).
- **Note:** no `postproc` script is run (parity with rtl_buddy). See [07 settled 14](07-ambiguities-and-assumptions.md).

### `parse-uvm-log`  · tags: post · contract: `keyed_join` (`key_field: key`)
Reimplements `UvmVlogPost`: parse the UVM Report Summary severity counts from
`proc.stdout_path` and compare against `test.uvm.max_warns`/`max_errors`
(FATAL must be 0). Emits the self-keyed `TestResult.parse(key, test_name, verdict, desc)` (`type_=PARSE`).

- **Source:** `rtl_buddy/src/rtl_buddy/tools/vlog_post.py:58-81` — `UvmVlogPost.get_results`: the `UVM Report Summary` regex, the severity-count `finditer`, the missing/invalid-summary FAILs, and the `WARNING <= max_warns and ERROR <= max_errors and FATAL <= 0` PASS rule. Thresholds come from `UVMConfig` (`config/uvm.py:3-19`).
- **In:** `test`, `proc` (joined by key — uvm branch of `route-post`)
- **Out:** default → `result`
- **Log idiom:** port-routed `result`; `log.error` at emission when the parsed result is FAIL. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

---

## Control / aggregation

### `early-stop-gate`  · tags: (cross-cutting) · contract: `default` (gate-pre) / `keyed_join` (gate-comp, gate-sim) (persistent: `early_stop`)
Compare the global `early_stop` phase against this gate's configured `phase`. Stop here →
emit `stop` (`TestResult.early_stop(key, test_name, desc)`); else forward. One module serves three instances via
`**edges`: it **co-gates** by forwarding *every* input edge on its same-named port on "go",
and drops them all on "stop". Wired `{test}` at `gate-pre`, `{test, simv}` at `gate-comp`,
`{test, proc}` at `gate-sim`; identity comes from the always-present `test` edge.

- **Source:** `rtl_buddy/src/rtl_buddy/runner/test_runner.py:59-76` — the three `if self.run_depth == RunDepth.{PRE,COMP,SIM}: return EarlyStopResults(...)` checkpoints in `TestRunner.run`. The `RunDepth` enum is `test_runner.py:14-18`; the `--early-stop` flag is `rtl_buddy.py:121`; the payload is `EarlyStopResults` at `runner/test_results.py:53-60`.
- **In:** `**edges` (per instance: `{test}` / `{test, simv}` / `{test, proc}`), `early_stop:str = "post"` (persistent)
- **Config:** `phase:str` (`pre`|`comp`|`sim`)
- **Out:** each input edge forwarded on its same-named port (on "go") | `("stop", TestResult.early_stop(key, test_name, desc))`
- **Log idiom:** **none** at the `stop` emission — a user-requested stop is NA but **not** a failure, so no `log.error` (deliberate exit-0 divergence; the `stop` port is wired to `results-summary`, the emitted `TestResult` is the summary row, and an NA row is not a FAIL row so it drives no exit). See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

### The terminal-aggregation node (`results-summary`)

> The `test` graph's 13 terminal results re-converge at one `results-summary` node (spec
> [10d](specs/10d-summarise-results.md)), fanned in by the `any` contract:
>
> - **Summary** is rendered by `results-summary.finalise()` from the 13 terminal `TestResult`s
>   fanned into it (the contract *is* the fan-in; no relay) — **outcomes only**. The `git_state`
>   event from `git-status` is not a terminal, so it does not reach the node; it falls through to
>   the console. See
>   [05 — Re-convergence](05-branching-and-results.md#re-convergence-the-summary-returns-as-a-graph-node).
> - **Exit code** is driven by `log.error` at two layers: each failure terminal's own **per-case**
>   event at origin (`compile_failed`/`sim_timeout`/`model_*`/`sweep_*`/`preproc_*`/`filelist_*`/`replay_seed_*`/`parse_log_*`/`parse_uvm_*`), plus
>   the consolidated `log.error("test_failures", count=…)` that `finalise()` emits on any FAIL row.
>   No terminal uses the generic `test_result` (retired).
> - The 13 result ports are **wired** to `results-summary` (via `contract_port_mappings`).
>
> The `any` contract backs this fan-in and stays reusable by other graphs. The node is specified in
> [spec 10d](specs/10d-summarise-results.md); the dormant out-of-graph `SummaryProcessor` plugin in
> [spec 10c](specs/10c-summary-handler.md).

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
| `work-dir` | `rtl_buddy.py:166-209` — `do_cmd_test` works in CWD (never `chdir`s); hoisted to a single `work_dir = Path.cwd()` provider |
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

> The `do_cmd_test` summary (`rtl_buddy.py:203-207`) is reproduced by the in-graph `results-summary`
> node's `finalise()`, and the OR-accumulated exit (`rtl_buddy.py:206`) by each terminal's per-case
> `log.error` plus the node's consolidated `test_failures` error. See
> [05](05-branching-and-results.md#re-convergence-the-summary-returns-as-a-graph-node).
