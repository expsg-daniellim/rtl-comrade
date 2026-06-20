# Concrete graph YAML and manifests

A proposed `graphs/test.yaml` plus the manifest entries for the new modules and the per-graph
`SummaryProcessor` logging plugin. Node ids match [04](04-pipeline-and-contracts.md); payload
shapes and ports match [02](02-payload-conventions.md)/[03](03-module-catalog.md).

This doc is the **wiring authority**: the `graphs/test.yaml` below carries the split-edge model
(per-field keyed edges, no `ctx`/`test_run`/`sim_cmd` bags). Spec
[11](specs/11-graph-and-manifests.md) assembles exactly this graph.

**Edge payload shapes (the split model).** Single-value edges carry `{key, value}` (`test`,
`simv`, `run_id`, `seed`, `timeout`, `filelist`); read `test["value"]`, and the key is
`<port>["key"]` (all joined ports share it). Cohesive multi-field messages keep named fields:
`command{key,argv,stdout_path,stderr_path}`, `proc{key,rc,timed_out,stdout_path,stderr_path}`,
`randseed{key,seed,randseed_path,argv}`. The unwired result-diversion ports (`skip`/`fail`/`timeout`)
carry `{key, result}`. There is **no** `ctx` / `test_run` / `sim_cmd` bag — bags assembled across the
graph were split into these keyed edges, while bags produced whole by one node (`proc`, `command`,
`filelist`, `randseed`, `seed`) stay whole. Every router co-gates every edge a downstream `keyed_join`
needs on its success branch, so a fail/stop never dangles a join.

## `rtl_comrade_config.yaml` (add the command)

```yaml
commands:
  test:
    path: "graphs/test.yaml"
    help: "Compile and simulate a SystemVerilog/UVM test suite."
```

## `graphs/test.yaml`

```yaml
modules:
- "../modules"
contracts:
- "../contracts"

nodes:
# --- setup: root config (run once, reimplemented) ---
- id: discover-root
  module: discover-config-file
  contract: unit
  config: { filename: root_config.yaml }
- { id: prepend-path,    module: prepend-cwd-path,  contract: unit }
- { id: parse-root,      module: parse-root-config, contract: unit }
- { id: select-platform, module: select-platform,   contract: unit }
- { id: resolve-builder, module: resolve-builder,   contract: unit }
# --- setup: suite + seed mode ---
- { id: check-cwd,    module: check-suite-cwd,    contract: unit }
- { id: ensure-logs,  module: ensure-logs-dir,    contract: unit }
- { id: parse-suite,  module: parse-suite-config, contract: unit }
- { id: seed-mode,    module: derive-seed-mode,   contract: unit }
- { id: git-status,   module: git-status,         contract: unit }

# --- list mode vs run ---
- { id: route-list, module: route-list-mode, contract: unit }
# select/list-names: default, not unit — the unfired branch leaves them fed only EndSentinel; unit would log missing_required_inputs → exit 1 (see 04)
- { id: list-names, module: list-test-names, contract: default }

# --- selection / expansion ---
- { id: select, module: select-tests, contract: default }   # default, not unit — empty `run` branch in list-mode must drain silently (see 04)
- id: filter
  module: filter-reglvl
  contract: default
  contract_config: { persistent_inputs: [ builder_cfg, reg_level, start_level ] }
- { id: load-model, module: load-model, contract: default }
- id: sweep
  module: expand-sweep
  contract: default
  contract_config: { persistent_inputs: [ root_cfg ] }

# --- per-test prep ---
- id: preproc
  module: run-preproc
  contract: default
  contract_config: { persistent_inputs: [ root_cfg ] }
- id: gate-pre
  module: early-stop-gate
  contract: default
  config: { phase: pre }
  contract_config: { persistent_inputs: [ early_stop ] }
- id: filelist
  module: write-filelist
  contract: default
  contract_config: { persistent_inputs: [ work_dir ] }   # writes <work_dir>/run.<tag>.f (per-tag)

# --- compile (run-process #1) ---
- id: cc-build
  module: build-compile-cmd
  contract: keyed_join                                       # keyed_join(test, filelist); singletons persistent
  contract_config: { key_field: key, persistent_inputs: [ builder_cfg, builder_mode, logs_dir, work_dir ] }
- id: cc-run
  module: run-process
  contract: default                                          # default(command); timeout unwired on the compile leg
  contract_config: { persistent_inputs: [ env_ready ] }   # caches prepend-path's token; edge is required: true (see env-setup block)
- id: cc-int
  module: interpret-compile
  contract: keyed_join                                       # keyed_join(test, simv, proc)
  contract_config: { key_field: key }
- id: gate-comp
  module: early-stop-gate
  contract: keyed_join                                       # wired {test, simv} — co-gates both so expand-runs' join can't dangle
  config: { phase: comp }
  contract_config: { key_field: key, persistent_inputs: [ early_stop ] }

# --- run-id fan-out + sim (run-process #2) ---
- id: runs
  module: expand-runs
  contract: keyed_join                                       # keyed_join(test, simv) at the test key; re-keys per run_id
  contract_config: { key_field: key, persistent_inputs: [ run_ids ] }
- id: seed
  module: resolve-seed
  contract: keyed_join                                       # keyed_join(test, run_id, simv)
  contract_config: { key_field: key, persistent_inputs: [ seed_mode, builder_cfg, logs_dir ] }
- id: sim-build
  module: build-sim-cmd
  contract: keyed_join                                       # keyed_join(test, run_id, simv, seed) — the bag-dissolution point
  contract_config: { key_field: key, persistent_inputs: [ builder_cfg, builder_mode, logs_dir ] }
- id: sim-run
  module: run-process
  contract: keyed_join                                       # keyed_join(command, timeout) — sim leg pairs the per-test timeout
  contract_config: { key_field: key, persistent_inputs: [ env_ready ] }   # caches prepend-path's token; edge is required: true (see env-setup block)
- id: randseed
  module: write-randseed
  contract: keyed_join                                       # keyed_join(randseed, proc-gate); side-effect leaf
  contract_config: { key_field: key }
- id: link-latest
  module: link-latest
  contract: keyed_join                                       # keyed_join(randseed, proc, randseed_done); terminal side-effect
  contract_config: { key_field: key }
- id: sim-int
  module: interpret-sim
  contract: keyed_join                                       # keyed_join(test, proc)
  contract_config: { key_field: key }
- id: gate-sim
  module: early-stop-gate
  contract: keyed_join                                       # wired {test, proc} — co-gates both
  config: { phase: sim }
  contract_config: { key_field: key, persistent_inputs: [ early_stop ] }

# --- post (terminal nodes; result ports left unwired, summary via logging plugin) ---
- id: route-post
  module: route-post
  contract: keyed_join                                       # keyed_join(test, proc); co-routes both to one parser branch
  contract_config: { key_field: key }
- id: parse-log
  module: parse-log
  contract: keyed_join                                       # keyed_join(test, proc)
  contract_config: { key_field: key }
- id: parse-uvm-log
  module: parse-uvm-log
  contract: keyed_join                                       # keyed_join(test, proc)
  contract_config: { key_field: key }
# (no fan-in / agg nodes; summary is a logging concern, see below)

# --- per-graph logging: accumulate result rows, render the summary table ---
logging:
  include_default: true
  handlers:
  - { path: log/summary.py, name: SummaryProcessor }      # processor: collect test_result rows + DropEvent them; render table in finalise(). git_state falls through.

edges:
# ---- CLI edges (subcommand options) ----
- { src: { cli: test_config, type: str,  default: "tests.yaml" }, dst: { node: check-cwd,       port: test_config } }
# --logs-dir is the subdir NAME, consumed only by ensure-logs; the resolved Path fans out below.
- { src: { cli: logs_dir,    type: str,  default: "logs" },        dst: { node: ensure-logs,    port: logs_dir } }
- { src: { cli: builder,      type: str,  default: "" },          dst: { node: resolve-builder, port: builder } }
- { src: { cli: test_name, option: false, type: str, default: "" }, dst: { node: select,        port: test_name } }
- { src: { cli: list,         type: bool, default: false },       dst: { node: route-list,      port: list } }
- { src: { cli: rnd_new,      type: bool, default: false },       dst: { node: seed-mode,       port: rnd_new } }
- { src: { cli: rnd_last,     type: bool, default: false },       dst: { node: seed-mode,       port: rnd_last } }
- { src: { cli: builder_mode, type: str,  default: "debug" },     dst: { node: cc-build,        port: builder_mode } }
- { src: { cli: builder_mode, type: str,  default: "debug" },     dst: { node: sim-build,       port: builder_mode } }
- { src: { cli: early_stop,   type: str,  default: "post" },      dst: { node: gate-pre,        port: early_stop } }
- { src: { cli: early_stop,   type: str,  default: "post" },      dst: { node: gate-comp,       port: early_stop } }
- { src: { cli: early_stop,   type: str,  default: "post" },      dst: { node: gate-sim,        port: early_stop } }

# ---- setup chain ----
- { src: { node: discover-root },     dst: { node: parse-root,      port: path } }
- { src: { node: parse-root },        dst: { node: select-platform, port: root_cfg } }
- { src: { node: parse-root },        dst: { node: resolve-builder, port: root_cfg } }
- { src: { node: select-platform },   dst: { node: resolve-builder, port: platform_cfg } }
- { src: { node: check-cwd },         dst: { node: parse-suite,     port: test_config_path } }

# ---- env setup: PATH prepend (token, direct) + logs/ bootstrap (data) — two independent edges ----
# PATH-readiness has no data carrier, so prepend-path emits an env_ready token wired DIRECTLY to
# each run-process (no relay through ensure-logs). The edge is marked `required: true` AND env_ready
# is in each run-process's persistent_inputs: `required` suppresses the module's `env_ready=True`
# default so the FIRST invocation blocks until prepend-path has mutated PATH (a hard ordering),
# while `persistent` caches that one token and replays it on every later invocation (prepend-path
# emits once; cc-run/sim-run are streaming). This is the logs_dir pattern; the module keeps its
# default for isolation testing. The logs/ mkdir is ordered separately by the logs_dir DATA edge below.
- { src: { node: prepend-path }, dst: { node: cc-run,  port: env_ready, required: true } }
- { src: { node: prepend-path }, dst: { node: sim-run, port: env_ready, required: true } }
- { src: { node: check-cwd,   port: work_dir }, dst: { node: ensure-logs, port: work_dir } }
# check-cwd's work_dir also roots the CWD-relative artefacts the logs/ tree doesn't cover:
# write-filelist's run.<tag>.f and build-compile-cmd's obj_dir_<tag>/ (load-bearing persistent
# inputs — same provider model as logs_dir, so a relocation stays a check-cwd-only change).
- { src: { node: check-cwd,   port: work_dir }, dst: { node: filelist,    port: work_dir } }
- { src: { node: check-cwd,   port: work_dir }, dst: { node: cc-build,    port: work_dir } }
# Resolved artefact dir (a Path) fans out to the path composers as a first-run-required persistent
# input (no Python default): cc-build/sim-build/seed block until ensure-logs — after its mkdir —
# emits logs_dir. That data dependency is what orders the mkdir before any subprocess redirect, so
# no env_ready token is needed for it. The CWD-relative assumption lives only in check-cwd/ensure-logs.
- { src: { node: ensure-logs, port: logs_dir }, dst: { node: cc-build,    port: logs_dir } }
- { src: { node: ensure-logs, port: logs_dir }, dst: { node: sim-build,   port: logs_dir } }
- { src: { node: ensure-logs, port: logs_dir }, dst: { node: seed,        port: logs_dir } }

# ---- config fan-out (persistent inputs; one output → many inputs is allowed) ----
- { src: { node: parse-root },      dst: { node: sweep,     port: root_cfg } }
- { src: { node: parse-root },      dst: { node: preproc,   port: root_cfg } }
- { src: { node: resolve-builder }, dst: { node: filter,    port: builder_cfg } }
- { src: { node: resolve-builder }, dst: { node: cc-build,  port: builder_cfg } }
- { src: { node: resolve-builder }, dst: { node: seed,      port: builder_cfg } }
- { src: { node: resolve-builder }, dst: { node: sim-build, port: builder_cfg } }
- { src: { node: seed-mode },       dst: { node: seed,      port: seed_mode } }

# ---- list mode vs run ----
- { src: { node: parse-suite },            dst: { node: route-list, port: suite_cfg } }
- { src: { node: route-list, port: list }, dst: { node: list-names, port: suite_cfg } }
- { src: { node: route-list, port: run },  dst: { node: select,     port: suite_cfg } }

# ---- main line: split per-test / per-run keyed edges (no ctx / test_run / sim_cmd bags) ----
# Pre-sim per-test chain (single keyed `test` edge; routers co-gate every edge a downstream join needs).
- { src: { node: select,     port: test }, dst: { node: filter,     port: test } }
- { src: { node: filter,     port: test }, dst: { node: load-model, port: test } }   # filter.skip → ∅
- { src: { node: load-model, port: test }, dst: { node: sweep,      port: test } }   # load-model.fail → ∅
- { src: { node: sweep,      port: test }, dst: { node: preproc,    port: test } }   # sweep.fail → ∅
- { src: { node: preproc,    port: test }, dst: { node: gate-pre,   port: test } }   # preproc.fail → ∅
- { src: { node: gate-pre,   port: test }, dst: { node: filelist,   port: test } }   # gate-pre.stop → ∅
- { src: { node: filelist,   port: test },     dst: { node: cc-build, port: test } }     # filelist.fail → ∅
- { src: { node: filelist,   port: filelist }, dst: { node: cc-build, port: filelist } }
# Compile: cc-build emits test+simv+command; cc-int joins test+simv+proc, co-gates test+simv on success.
- { src: { node: cc-build, port: command }, dst: { node: cc-run, port: command } }
- { src: { node: cc-build, port: test },    dst: { node: cc-int, port: test } }
- { src: { node: cc-build, port: simv },    dst: { node: cc-int, port: simv } }
- { src: { node: cc-run },                  dst: { node: cc-int, port: proc } }      # cc-run emits proc on default
- { src: { node: cc-int,   port: test }, dst: { node: gate-comp, port: test } }      # cc-int.fail → ∅
- { src: { node: cc-int,   port: simv }, dst: { node: gate-comp, port: simv } }
- { src: { node: gate-comp, port: test }, dst: { node: runs, port: test } }          # gate-comp.stop → ∅ (drops test+simv together)
- { src: { node: gate-comp, port: simv }, dst: { node: runs, port: simv } }
# Run fan-out: expand-runs joins test+simv at the test key, re-keys test/run_id/simv per run_id.
- { src: { node: runs, port: test },   dst: { node: seed, port: test } }
- { src: { node: runs, port: run_id }, dst: { node: seed, port: run_id } }
- { src: { node: runs, port: simv },   dst: { node: seed, port: simv } }
- { src: { node: seed, port: test },   dst: { node: sim-build, port: test } }        # seed.fail → ∅ (REPLAY only)
- { src: { node: seed, port: run_id }, dst: { node: sim-build, port: run_id } }
- { src: { node: seed, port: simv },   dst: { node: sim-build, port: simv } }
- { src: { node: seed, port: seed },   dst: { node: sim-build, port: seed } }
# Sim build (bag-dissolution): emits command + separate timeout{key,value} + randseed + test; simv/run_id/seed die here.
- { src: { node: sim-build, port: command },  dst: { node: sim-run,     port: command } }
- { src: { node: sim-build, port: timeout },  dst: { node: sim-run,     port: timeout } }
- { src: { node: sim-build, port: randseed }, dst: { node: randseed,    port: randseed } }
- { src: { node: sim-build, port: randseed }, dst: { node: link-latest, port: randseed } }
- { src: { node: sim-build, port: test },     dst: { node: sim-int,     port: test } }
- { src: { node: sim-run },                   dst: { node: randseed,    port: proc } }   # proc fans out to all three post-sim consumers
- { src: { node: sim-run },                   dst: { node: link-latest, port: proc } }
- { src: { node: sim-run },                   dst: { node: sim-int,     port: proc } }
# Post-sim — side-effect branch (write-randseed → link-latest, ordered by randseed_done).
- { src: { node: randseed, port: randseed_done }, dst: { node: link-latest, port: randseed_done } }
# link-latest is terminal (no output).
# Post-sim — classification branch (interpret-sim → gate-sim → route-post → parse-*).
- { src: { node: sim-int,  port: test }, dst: { node: gate-sim, port: test } }       # sim-int.timeout → ∅
- { src: { node: sim-int,  port: proc }, dst: { node: gate-sim, port: proc } }
- { src: { node: gate-sim, port: test }, dst: { node: route-post, port: test } }     # gate-sim.stop → ∅ (drops test+proc together)
- { src: { node: gate-sim, port: proc }, dst: { node: route-post, port: proc } }
- { src: { node: route-post, port: uvm_test },   dst: { node: parse-uvm-log, port: test } }
- { src: { node: route-post, port: uvm_proc },   dst: { node: parse-uvm-log, port: proc } }
- { src: { node: route-post, port: plain_test }, dst: { node: parse-log, port: test } }
- { src: { node: route-post, port: plain_proc }, dst: { node: parse-log, port: proc } }
# parse-log.default / parse-uvm-log.default → ∅

# ---- terminal result ports are UNWIRED ----
# The 13 terminal outcomes below have NO edge: filter.skip, gate-pre.stop, cc-int.fail,
# gate-comp.stop, sim-int.timeout, gate-sim.stop, parse-log.default, parse-uvm-log.default,
# load-model.fail, sweep.fail, preproc.fail, filelist.fail, seed.fail. The silent paths
# (parse-*, filter.skip, gate-*.stop) log `test_result`; the failure terminals (the *.fail
# ports and sim-int.timeout) log.error their own domain event (compile_failed/sim_timeout/…)
# carrying result/desc. The harness reports `no_destination` at INFO for each unwired port and
# the item leaves the graph. The SummaryProcessor logging plugin (see the `logging` block
# above) accumulates the watch-list rows and renders the results table in finalise(); the
# per-emission log.error drives the exit. git-status likewise logs `git_state` with no edge —
# it falls through to the console.
```

Notes:

- **No fan-in / aggregate node.** The 13 terminal ports are unwired; the summary **results**
  table is rendered by the `SummaryProcessor` logging plugin (`logging` block above) in its
  `finalise()` hook, and the exit code is driven by the per-emission `log.error` at
  each failure site. `git_state` is not part of the table — it falls through to the console. See [05 — Re-convergence](05-branching-and-results.md#re-convergence-the-summary-is-a-logging-concern-not-a-graph-node)
  and [07 settled 27](07-ambiguities-and-assumptions.md). Adding a new terminal source means
  one new `log.info("test_result", ...)` call — no edge, no module signature change.
- The five `*_fail` ports (`load-model.fail`, `sweep.fail`, `preproc.fail`, `filelist.fail`,
  `seed.fail`) carry per-test config-domain failures via the `fail` output on each of those
  source modules; each `log.error`s once (the sole exit driver) and `log.info`s its
  `test_result` row. See [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).
- `run_ids` (→ `runs`) is unwired for plain `test`; the module defaults it to `[None]`
  (single run). `randtest` wires it from a `rnd_cnt`-derived CLI edge.
- `filter`'s `reg_level`/`start_level` are persistent but unwired for `test`; the module's
  Python defaults (`None`) make it a pass-through. The `regression` graph wires them.
- `cc-int` `keyed_join`s three keyed edges (`test`, `simv`, `proc`) by key and co-gates
  `test`+`simv` on compile success; `simv` (born at `cc-build`) threads through `gate-comp`
  and `expand-runs` to `sim-build`.
- `gate-comp` is wired `{test, simv}` (so it is `keyed_join`, not `default`) — `expand-runs`
  needs `simv`, and co-gating requires `simv` to travel through the gate rather than bypass it,
  so a stop drops `test`+`simv` together. (`gate-pre` is `{test}`/`default`; `gate-sim` is
  `{test, proc}`/`keyed_join`.)
- `randseed` (`write-randseed`) `keyed_join`s `randseed` + a `proc` completion gate and is a
  side-effect leaf — it writes the `.randseed` file and emits a `randseed_done` ordering signal;
  there is **no** `test_run` bag. Post-sim is two parallel branches off `proc`: the side-effect
  branch (`randseed` → `link-latest`) and the classification branch (`sim-int` → `route-post` →
  `parse-*`), each `keyed_join`ing `test`/`proc` by key.
- `run-process` writes the `.log`/`.err` files itself (redirect, paths supplied in
  `command`) — there is no separate "write logs" node. `link-latest` only forces symlinks.
- **Artefact location is decided once and flows as data.** `--logs-dir` (the subdir *name*) is
  a CLI edge to `ensure-logs` only. `ensure-logs` roots it on `check-cwd`'s `work_dir` and emits
  the **resolved directory `Path`** on its `logs_dir` port, which fans out as a persistent input
  to the three composers `cc-build` / `sim-build` / `seed`. They join filenames onto that
  directory and never read the ambient CWD. The non-`logs/` CWD-relative artefacts follow the
  same model off `check-cwd`'s `work_dir` directly: `filelist` roots `run.<tag>.f` and `cc-build`
  roots `obj_dir_<tag>/` on `work_dir` (load-bearing persistent inputs), so the rtl_buddy
  "everything is CWD-relative" assumption lives only in `check-cwd` and its `ensure-logs`
  sub-rooting (relocating artefacts is a change there alone). `write-randseed` does **not** take
  `logs_dir` — `sim-build` pre-composes `randseed_path` onto the `randseed` edge (and `log`/`err`
  become `command`'s redirect paths, echoed back on `proc`), which `randseed`/`link-latest` read by key.
  The default `"logs"` matches rtl_buddy's hard-coded literal; override is a small Notable
  divergence (see [07 settled 26](07-ambiguities-and-assumptions.md)).
- `load-model` sits after `filter` so models for skipped tests aren't loaded — a deliberate
  lazy-vs-eager change from rtl_buddy (07, item on model loading).

## Manifest additions — `modules/config.yaml`

```yaml
- file: rtl_buddy/setup.py
  plugins:
  - { name: discover-config-file, class_name: DiscoverConfigFileMod }
  - { name: prepend-cwd-path,     class_name: PrependCwdPathMod }
  - { name: parse-root-config,    class_name: ParseRootConfigMod }
  - { name: select-platform,      class_name: SelectPlatformMod }
  - { name: resolve-builder,      class_name: ResolveBuilderMod }
  - { name: check-suite-cwd,      class_name: CheckSuiteCwdMod }
  - { name: ensure-logs-dir,      class_name: EnsureLogsDirMod }
  - { name: parse-suite-config,   class_name: ParseSuiteConfigMod }
  - { name: derive-seed-mode,     class_name: DeriveSeedModeMod }
  - { name: git-status,           class_name: GitStatusMod }
  - { name: route-list-mode,      class_name: RouteListModeMod }
  - { name: list-test-names,      class_name: ListTestNamesMod }
  - { name: select-tests,         class_name: SelectTestsMod }
  - { name: filter-reglvl,        class_name: FilterRegLvlMod }
  - { name: load-model,           class_name: LoadModelMod }
  - { name: expand-sweep,         class_name: ExpandSweepMod }
- file: rtl_buddy/build.py
  plugins:
  - { name: run-preproc,       class_name: RunPreprocMod }
  - { name: write-filelist,    class_name: WriteFilelistMod }
  - { name: build-compile-cmd, class_name: BuildCompileCmdMod }
  - { name: run-process,       class_name: RunProcessMod }
  - { name: interpret-compile, class_name: InterpretCompileMod }
- file: rtl_buddy/sim.py
  plugins:
  - { name: expand-runs,       class_name: ExpandRunsMod }
  - { name: resolve-seed,      class_name: ResolveSeedMod }
  - { name: build-sim-cmd,     class_name: BuildSimCmdMod }
  - { name: write-randseed,    class_name: WriteRandseedMod }
  - { name: link-latest,       class_name: LinkLatestMod }
  - { name: interpret-sim,     class_name: InterpretSimMod }
  - { name: route-post,        class_name: RoutePostMod }
  - { name: parse-log,         class_name: ParseLogMod }
  - { name: parse-uvm-log,     class_name: ParseUvmLogMod }
- file: rtl_buddy/control.py
  plugins:
  - { name: early-stop-gate,   class_name: EarlyStopGateMod }
  # no fan-in-results / aggregate-results node — summary is a logging plugin
```

## Logging plugin — `graphs/log/summary.py`

Referenced by the `logging` block in `graphs/test.yaml`. Contains the single `SummaryProcessor`
(a stateful structlog processor — **not** a `logging.Handler`; it accumulates `test_result`
rows, `DropEvent`s them, and renders the results table in `finalise()`; sketch in
[05](05-branching-and-results.md#the-summaryprocessor-logging-plugin); spec in
[specs/10](idx-10-control-aggregate.md)). It is selected by `path`/`name`, not via a
plugin manifest — per-graph logging entries resolve files relative to the graph file's
directory (`docs/harness_configs/graph.md`).

## Manifest addition — `contracts/config.yaml`

```yaml
- file: any.py
  plugins:
  - { name: any, class_name: AnyContract }
```

`any.py` contains `AnyContract` (sketch in [spec 02](specs/02-any-contract-and-fan-in.md)),
a plain general-purpose contract. **It is registered for reuse but is not wired in the
`test` graph.** There is **no** `serial.py` / `serial_acquire` contract; parallel safety comes
from per-tag artefact naming (`write-filelist` writes `run.<tag>.f`; see
[05 — Interim CWD-collision posture](05-branching-and-results.md#interim-cwd-collision-posture--per-tag-artefact-naming)).
Do not re-introduce a lock for the residual CWD collisions — those are the job of the upstream
per-invocation-subdir change ([07](07-ambiguities-and-assumptions.md) item 17).

The modules **reimplement** `rtl_buddy` natively; only the config-schema dataclasses are kept
identical, so existing `root_config.yaml`/`tests.yaml`/`models.yaml` load drop-in — see
[07](07-ambiguities-and-assumptions.md) item 1. The package name (`modules/rtl_buddy/`) and
the file grouping above are **pinned**, not a suggestion — see
[specs/README.md — Module package layout](specs/README.md#module-package-layout-pinned).
