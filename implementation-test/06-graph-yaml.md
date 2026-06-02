# Concrete graph YAML and manifests

A proposed `graphs/test.yaml` plus the manifest entries for the new modules and the new
`merge` contract. Node ids match [04](04-pipeline-and-contracts.md); payload shapes and
ports match [02](02-payload-conventions.md)/[03](03-module-catalog.md).

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

# --- list mode vs run ---
- { id: route-list, module: route-list-mode, contract: unit }
- { id: list-names, module: list-test-names, contract: unit }

# --- selection / expansion ---
- { id: select, module: select-tests, contract: unit }
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
  contract: serial_acquire
  contract_config: { lock_name: compile-sim }

# --- compile (run-process #1) ---
- id: cc-build
  module: build-compile-cmd
  contract: default
  contract_config: { persistent_inputs: [ builder_cfg, builder_mode, logs_dir ] }
- { id: cc-run, module: run-process, contract: default }
- id: cc-int
  module: interpret-compile
  contract: keyed_join
  contract_config: { key_field: key }
- id: gate-comp
  module: early-stop-gate
  contract: default
  config: { phase: comp }
  contract_config: { persistent_inputs: [ early_stop ] }

# --- run-id fan-out + sim (run-process #2) ---
- id: runs
  module: expand-runs
  contract: default
  contract_config: { persistent_inputs: [ run_ids ] }
- id: seed
  module: resolve-seed
  contract: default
  contract_config: { persistent_inputs: [ seed_mode, builder_cfg, logs_dir ] }
- id: sim-build
  module: build-sim-cmd
  contract: default
  contract_config: { persistent_inputs: [ builder_cfg, builder_mode, logs_dir ] }
- { id: sim-run, module: run-process, contract: default }
- id: randseed
  module: write-randseed
  contract: keyed_join
  contract_config: { key_field: key }
- { id: link-latest, module: link-latest,   contract: default }
- { id: sim-int,     module: interpret-sim, contract: default }
- id: gate-sim
  module: early-stop-gate
  contract: default
  config: { phase: sim }
  contract_config: { persistent_inputs: [ early_stop ] }

# --- post + aggregate ---
- { id: route-post,    module: route-post,        contract: default }
- { id: parse-log,     module: parse-log,         contract: default }
- { id: parse-uvm-log, module: parse-uvm-log,     contract: default }
- id: agg
  module: aggregate-results
  contract: merge
  contract_config: { fan_in: result, release_lock: compile-sim }

edges:
# ---- CLI edges (subcommand options) ----
- { src: { cli: test_config, type: str,  default: "tests.yaml" }, dst: { node: check-cwd,       port: test_config } }
- { src: { cli: logs_dir,    type: str,  default: "logs" },        dst: { node: ensure-logs,    port: logs_dir } }
- { src: { cli: logs_dir,    type: str,  default: "logs" },        dst: { node: cc-build,       port: logs_dir } }
- { src: { cli: logs_dir,    type: str,  default: "logs" },        dst: { node: sim-build,      port: logs_dir } }
- { src: { cli: logs_dir,    type: str,  default: "logs" },        dst: { node: seed,           port: logs_dir } }
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
- { src: { node: select-platform },   dst: { node: resolve-builder, port: platform_cfg } }
- { src: { node: check-cwd },         dst: { node: parse-suite,     port: test_config } }

# ---- env setup: PATH-prepend + logs/ bootstrap sequenced upstream of every subprocess ----
# Chain: prepend-path → ensure-logs → cc-run/sim-run. ensure-logs additionally takes the
# CWD-validated signal from check-cwd as a sequencing input (`_cwd`).
- { src: { node: prepend-path },      dst: { node: ensure-logs,     port: env_ready } }
- { src: { node: check-cwd },         dst: { node: ensure-logs,     port: _cwd } }
- { src: { node: ensure-logs },       dst: { node: cc-run,          port: env_ready } }
- { src: { node: ensure-logs },       dst: { node: sim-run,         port: env_ready } }

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

# ---- main line: continue-ports (ctx + local work payloads) ----
- { src: { node: select },                   dst: { node: filter,     port: ctx } }
- { src: { node: filter,    port: keep },    dst: { node: load-model, port: ctx } }
- { src: { node: load-model },               dst: { node: sweep,      port: ctx } }
- { src: { node: sweep },                    dst: { node: preproc,  port: ctx } }
- { src: { node: preproc },                  dst: { node: gate-pre, port: ctx } }
- { src: { node: gate-pre,  port: go },      dst: { node: filelist, port: ctx } }
- { src: { node: filelist,  port: ctx },     dst: { node: cc-build, port: ctx } }
- { src: { node: filelist,  port: filelist },dst: { node: cc-build, port: filelist } }
- { src: { node: cc-build,  port: ctx },     dst: { node: cc-int,   port: ctx } }
- { src: { node: cc-build,  port: command }, dst: { node: cc-run,   port: command } }
- { src: { node: cc-run },                   dst: { node: cc-int,   port: proc } }
- { src: { node: cc-int,    port: ok },      dst: { node: gate-comp,port: ctx } }
- { src: { node: gate-comp, port: go },      dst: { node: runs,     port: ctx } }
- { src: { node: runs },                     dst: { node: seed,     port: ctx } }
- { src: { node: seed,      port: ctx },     dst: { node: sim-build,port: ctx } }
- { src: { node: seed,      port: seed },    dst: { node: sim-build,port: seed } }
- { src: { node: sim-build, port: ctx },     dst: { node: randseed,    port: ctx } }
- { src: { node: sim-build, port: command }, dst: { node: sim-run,     port: command } }
- { src: { node: sim-build, port: timeout }, dst: { node: sim-run,     port: timeout } }
- { src: { node: sim-run },                  dst: { node: randseed,    port: proc } }
- { src: { node: randseed },                 dst: { node: link-latest, port: ctx } }
- { src: { node: link-latest },              dst: { node: sim-int,     port: ctx } }
- { src: { node: sim-int,   port: ok },      dst: { node: gate-sim,   port: ctx } }
- { src: { node: gate-sim,  port: go },      dst: { node: route-post, port: ctx } }
- { src: { node: route-post,port: plain },   dst: { node: parse-log,     port: ctx } }
- { src: { node: route-post,port: uvm },     dst: { node: parse-uvm-log, port: ctx } }

# ---- terminal ports → the merge collector (one input port per source) ----
- { src: { node: filter,     port: skip },    dst: { node: agg, port: skip } }
- { src: { node: gate-pre,   port: stop },    dst: { node: agg, port: es_pre } }
- { src: { node: cc-int,     port: fail },    dst: { node: agg, port: cc_fail } }
- { src: { node: gate-comp,  port: stop },    dst: { node: agg, port: es_comp } }
- { src: { node: sim-int,    port: timeout }, dst: { node: agg, port: sim_to } }
- { src: { node: gate-sim,   port: stop },    dst: { node: agg, port: es_sim } }
- { src: { node: parse-log },                 dst: { node: agg, port: post_plain } }
- { src: { node: parse-uvm-log },             dst: { node: agg, port: post_uvm } }
# ---- per-test config-domain fail ports (see [05 — Log idioms]) ----
- { src: { node: load-model, port: fail },    dst: { node: agg, port: model_fail } }
- { src: { node: sweep,      port: fail },    dst: { node: agg, port: sweep_fail } }
- { src: { node: preproc,    port: fail },    dst: { node: agg, port: preproc_fail } }
- { src: { node: filelist,   port: fail },    dst: { node: agg, port: filelist_fail } }
- { src: { node: seed,       port: fail },    dst: { node: agg, port: seed_fail } }
```

Notes:

- `aggregate-results.run(self, result)` has a single module input port. The 13 graph
  edges below land on **contract-declared** input ports — names defined on `MergeContract`'s
  Config, not on the module signature. The `fan_in: result` collapses every contract-side
  input onto `result` before invoking the module. This depends on the harness change
  called out as a prerequisite in [05](05-branching-and-results.md) (the current harness
  builds the node's port set strictly from the module's `run()` signature; see
  `src/rtl_comrade/node.py:122`). Adding a new terminal source means extending
  `Config.fan_in`'s input list and adding one edge here — the module signature does not
  change. See [07](07-ambiguities-and-assumptions.md) item 19 for the design history.
- The five `*_fail` ports (`model_fail`, `sweep_fail`, `preproc_fail`, `filelist_fail`,
  `seed_fail`) carry per-test config-domain failures routed via the new `fail` output on
  each of those source modules; see [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).
- `run_ids` (→ `runs`) is unwired for plain `test`; the module defaults it to `[None]`
  (single run). `randtest` wires it from a `rnd_cnt`-derived CLI edge.
- `filter`'s `reg_level`/`start_level` are persistent but unwired for `test`; the module's
  Python defaults (`None`) make it a pass-through. The `regression` graph wires them.
- `cc-int`/`randseed` take only their two keyed ports (`ctx`,`proc`); `simv`, `seed`, and
  `log` were folded into `ctx` upstream precisely so the joins carry no config port.
- `run-process` writes the `.log`/`.err` files itself (redirect, paths supplied in
  `command`) — there is no separate "write logs" node. `link-latest` only forces symlinks.
- `--logs-dir` is broadcast as a CLI edge to **four** consumers: `ensure-logs` (creates
  the directory once at startup), and `cc-build` / `sim-build` / `seed` (compose paths
  inside it). `write-randseed` does **not** take `logs_dir` as a persistent input — the
  `keyed_join` contract joins every port by key and cannot also carry persistent config;
  instead, `sim-build` folds `randseed_path` into `ctx` so the join carries the path. The
  default `"logs"` matches rtl_buddy's hard-coded literal; override is a small Notable
  divergence (see [07 settled 26](07-ambiguities-and-assumptions.md)).
- `load-model` sits after `filter` so models for skipped tests aren't loaded — a deliberate
  lazy-vs-eager change from rtl_buddy (07, item on model loading).

## Manifest additions — `modules/config.yaml`

```yaml
- file: rtl_test/setup.py
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
  - { name: route-list-mode,      class_name: RouteListModeMod }
  - { name: list-test-names,      class_name: ListTestNamesMod }
  - { name: select-tests,         class_name: SelectTestsMod }
  - { name: filter-reglvl,        class_name: FilterRegLvlMod }
  - { name: load-model,           class_name: LoadModelMod }
  - { name: expand-sweep,         class_name: ExpandSweepMod }
- file: rtl_test/build.py
  plugins:
  - { name: run-preproc,       class_name: RunPreprocMod }
  - { name: write-filelist,    class_name: WriteFilelistMod }
  - { name: build-compile-cmd, class_name: BuildCompileCmdMod }
  - { name: run-process,       class_name: RunProcessMod }
  - { name: interpret-compile, class_name: InterpretCompileMod }
- file: rtl_test/sim.py
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
- file: rtl_test/control.py
  plugins:
  - { name: early-stop-gate,   class_name: EarlyStopGateMod }
  - { name: aggregate-results, class_name: AggregateResultsMod }
```

## Manifest addition — `contracts/config.yaml`

```yaml
- file: merge.py
  plugins:
  - { name: merge, class_name: MergeContract }
- file: serial.py
  plugins:
  - { name: serial_acquire, class_name: SerialAcquireContract }
```

`merge.py` contains the `MergeContract` sketched in [05](05-branching-and-results.md),
extended with the optional `release_lock` Config field described in
[05 — Serialising contracts](05-branching-and-results.md#serialising-contracts--interim-parallel-safety-posture).
`serial.py` contains `SerialAcquireContract` and the module-level `_LOCKS` registry it shares
with `MergeContract` for the `release_lock` lookup. **Both `serial_acquire` and `merge`'s
`release_lock` field are interim** — to be removed once upstream `rtl_buddy` per-test
artefact dirs land (see [07](07-ambiguities-and-assumptions.md) item 17). The modules
**reimplement** `rtl_buddy` natively; only the config-schema dataclasses are kept identical,
so existing `root_config.yaml`/`tests.yaml`/`models.yaml` load drop-in — see
[07](07-ambiguities-and-assumptions.md) item 1. File grouping is a suggestion.

> **Cross-file lock state.** `SerialAcquireContract` and `MergeContract`'s `release_lock`
> branch must reach the **same** `_LOCKS` dict at runtime. Put both contracts in `serial.py`
> and have `MergeContract` import the registry from there (or define the registry in a third
> shared module both import). Splitting across plugin files that the loader imports
> separately would give them distinct `_LOCKS` instances and the lock would never actually
> serialise anything.
