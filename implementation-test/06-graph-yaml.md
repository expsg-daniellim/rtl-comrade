# Concrete graph YAML and manifests

A proposed `graphs/test.yaml` plus the manifest entries for the new modules and the in-graph
`results-summary` node (the 13 terminal `TestResult` ports fanned in by the `any` contract). Node
ids match [04](04-pipeline-and-contracts.md); payload shapes and ports match
[02](02-payload-conventions.md)/[03](03-module-catalog.md).

This doc is the **wiring authority**: the `graphs/test.yaml` below carries the split-edge model
(per-field keyed edges, no `ctx`/`test_run`/`sim_cmd` bags). Spec
[11](specs/11-graph-and-manifests.md) assembles exactly this graph.

**Edge payload shapes (the split model).** The `test` edge carries a **bare self-keyed
`TestConfig`** (read fields directly — `test.get_name()`, `test.key`). The other single-value
edges carry the `KeyedValue` envelope `{key, value}` (`model`, `simv`, `run_id`, `seed`,
`timeout`, `filelist`); read `<port>.value`. The key is `<port>.key` on each (all joined ports
share it; `keyed_join` reads it attribute-first, so a field on `TestConfig` or on the envelope
are both fine). Cohesive multi-field messages keep named fields:
`command{key,argv,stdout_path,stderr_path}`, `proc{key,rc,stdout_path,stderr_path}` (`rc is None` ⟺ timed out),
`randseed{key,seed,randseed_path,argv}`. The result-diversion ports (`skip`/`fail`/`timeout`/`stop`/`default`)
carry a self-keyed `TestResult` (`{key, test_name, type_, result, desc}`) → `results-summary`. There is **no** `ctx` / `test_run` / `sim_cmd` bag — bags assembled across the
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
  contract: default
  config: { filename: root_config.yaml }
- { id: prepend-path,    module: prepend-cwd-path,  contract: default }
- { id: parse-root,      module: parse-root-config, contract: unit }
- { id: select-platform, module: select-platform,   contract: unit }
- { id: resolve-builder, module: resolve-builder,   contract: unit }
# --- setup: suite + seed mode ---
- { id: work-dir,     module: work-dir,           contract: default }   # zero-input artefact-base provider (= Path.cwd().resolve()); default (not unit) — zero-input convention; regression swaps in per-suite suite_dir
- { id: ensure-logs,  module: ensure-logs-dir,    contract: unit }
- { id: parse-suite,  module: parse-suite-config, contract: unit }
- { id: seed-mode,    module: derive-seed-mode,   contract: unit }
- { id: git-status,   module: git-status,         contract: default }

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
- { id: load-model, module: load-model, contract: default }   # resolves the model BEFORE the sweep/preproc hooks (mirrors rtl_buddy's suite-load resolution) so both can expose the resolved ModelConfig to their scripts; sits after `filter` so skipped tests don't load; emits a 1:1 `model` edge that rides through to write-filelist
- id: sweep
  module: expand-sweep
  contract: keyed_join                                       # keyed_join(test, model); root_cfg persistent
  contract_config: { key_field: key, persistent_inputs: [ root_cfg ] }

# --- per-test prep ---
- id: preproc
  module: run-preproc
  contract: keyed_join                                       # keyed_join(test, model); root_cfg persistent
  contract_config: { key_field: key, persistent_inputs: [ root_cfg ] }
- id: gate-pre
  module: early-stop-gate
  contract: keyed_join                                       # wired {test, model} — co-gates both so write-filelist's join can't dangle
  config: { phase: pre }
  contract_config: { key_field: key, persistent_inputs: [ early_stop ] }
- id: filelist
  module: write-filelist
  contract: keyed_join                                       # keyed_join(test, model); work_dir persistent
  contract_config: { key_field: key, persistent_inputs: [ work_dir ] }   # writes <work_dir>/run.<tag>.f (per-tag)

# --- compile (run-process #1) ---
- id: cc-build
  module: build-compile-cmd
  contract: keyed_join                                       # keyed_join(test, filelist); singletons persistent
  contract_config: { key_field: key, persistent_inputs: [ builder_cfg, builder_mode, logs_dir, work_dir ] }
- id: cc-run
  module: run-process
  contract: default                                          # default(command); timeout unwired on the compile leg
  contract_config: { persistent_inputs: [ env_ready, work_dir ] }   # env_ready caches prepend-path's token (edge required: true); work_dir is the subprocess cwd
  # no `config: { grace_s }` — the compile leg never times out, so the escalation grace is inert (module default applies)
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
  config: { grace_s: 5.0 }                                   # SIGQUIT→SIGKILL escalation grace; optional, defaults to 5.0s (only the sim leg times out)
  contract: keyed_join                                       # keyed_join(command, timeout) — sim leg pairs the per-test timeout
  contract_config: { key_field: key, persistent_inputs: [ env_ready, work_dir ] }   # env_ready caches prepend-path's token (edge required: true); work_dir is the subprocess cwd
- id: randseed
  module: write-randseed
  contract: keyed_join                                       # keyed_join(randseed, proc-gate); side-effect leaf; work_dir persistent (reads HierInstanceSeed.txt from it)
  contract_config: { key_field: key, persistent_inputs: [ work_dir ] }
- id: link-latest
  module: link-latest
  contract: keyed_join                                       # keyed_join(randseed, proc, randseed_done); terminal side-effect; work_dir persistent (test.* symlinks placed under it)
  contract_config: { key_field: key, persistent_inputs: [ work_dir ] }
- id: sim-int
  module: interpret-sim
  contract: keyed_join                                       # keyed_join(test, proc)
  contract_config: { key_field: key }
- id: gate-sim
  module: early-stop-gate
  contract: keyed_join                                       # wired {test, proc} — co-gates both
  config: { phase: sim }
  contract_config: { key_field: key, persistent_inputs: [ early_stop ] }

# --- post (terminal nodes; result ports fan into results-summary, see below) ---
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
# --- results summary (in-graph): the 13 terminal TestResult ports fan in via the any contract ---
- id: results-summary
  module: summarise-results
  contract: any
  contract_config: { mapping: result }                    # n→1: every input port funnels onto the `result` output port → run(result=<TestResult>)
  contract_port_mappings:                                  # the node's 13-port surface; each contract port forwards to module param `result`
    compile_fail: [result]
    sim_timeout:  [result]
    load_model:   [result]
    filelist:     [result]
    sweep:        [result]
    preproc:      [result]
    seed:         [result]
    parse_plain:  [result]
    parse_uvm:    [result]
    skip:         [result]
    stop_pre:     [result]
    stop_comp:    [result]
    stop_sim:     [result]
# (no separate fan-in / aggregate node — the `any` contract IS the fan-in; the SummaryProcessor logging plugin is retired/dormant, see 10c/10d)

edges:
# ---- CLI edges (subcommand options) ----
- { src: { cli: test_config, type: str,  default: "tests.yaml" }, dst: { node: parse-suite,         port: test_config } }   # parse-suite resolves it against CWD (no separate resolve node)
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
# parse-suite's test_config comes straight from the CLI edge above — it resolves the path itself.

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
- { src: { node: work-dir },   dst: { node: ensure-logs, port: work_dir } }
# work-dir (= Path.cwd().resolve()) is the single artefact base. It roots every leaf path AND the
# subprocess cwd, so test/randtest work in (and output to) CWD — run here, output here (a relocation
# stays a work-dir-only change; regression feeds these same ports its per-suite suite_dir). Consumers:
#   filelist  — run.<tag>.f filename + its contents (relpath base)
#   cc-build  — obj_dir_<tag>/ and the verilator simv
#   cc-run/sim-run — the subprocess cwd (compiler/sim resolve relative inputs/outputs here)
#   randseed  — reads HierInstanceSeed.txt from work_dir
#   link-latest — places the test.* "latest" symlinks under work_dir
- { src: { node: work-dir },   dst: { node: filelist,    port: work_dir } }
- { src: { node: work-dir },   dst: { node: cc-build,    port: work_dir } }
- { src: { node: work-dir },   dst: { node: cc-run,      port: work_dir } }
- { src: { node: work-dir },   dst: { node: sim-run,     port: work_dir } }
- { src: { node: work-dir },   dst: { node: randseed,    port: work_dir } }
- { src: { node: work-dir },   dst: { node: link-latest, port: work_dir } }
# Resolved artefact dir (a Path) fans out to the path composers as a first-run-required persistent
# input (no Python default): cc-build/sim-build/seed block until ensure-logs — after its mkdir —
# emits logs_dir. That data dependency is what orders the mkdir before any subprocess redirect, so
# no env_ready token is needed for it. The artefact base is provided once by work-dir (= CWD).
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
# Pre-sim per-test chain. load-model adds the 1:1 `model` edge right after `filter`; it then rides alongside `test` through sweep → preproc → gate-pre (each keyed_joins it to `test` by key and co-gates it) to write-filelist, where it is consumed. Routers co-gate every edge a downstream join needs.
- { src: { node: select,     port: test }, dst: { node: filter,     port: test } }
- { src: { node: filter,     port: test }, dst: { node: load-model, port: test } }   # filter.skip → results-summary
- { src: { node: load-model, port: test },  dst: { node: sweep, port: test } }       # load-model.fail → results-summary (drops test+model together)
- { src: { node: load-model, port: model }, dst: { node: sweep, port: model } }      # 1:1 model edge; rides through to write-filelist
- { src: { node: sweep,      port: test },  dst: { node: preproc, port: test } }     # sweep.fail → results-summary (drops test+model together)
- { src: { node: sweep,      port: model }, dst: { node: preproc, port: model } }    # re-keyed #i per sweep variant (one model edge per variant)
- { src: { node: preproc,    port: test },  dst: { node: gate-pre, port: test } }    # preproc.fail → results-summary (drops test+model together)
- { src: { node: preproc,    port: model }, dst: { node: gate-pre, port: model } }
- { src: { node: gate-pre,   port: test },  dst: { node: filelist, port: test } }    # gate-pre.stop → results-summary (drops test+model together)
- { src: { node: gate-pre,   port: model }, dst: { node: filelist, port: model } }   # joined by key at write-filelist (model consumed here)
- { src: { node: filelist,   port: test },     dst: { node: cc-build, port: test } }     # filelist.fail → results-summary
- { src: { node: filelist,   port: filelist }, dst: { node: cc-build, port: filelist } }
# Compile: cc-build emits test+simv+command; cc-int joins test+simv+proc, co-gates test+simv on success.
- { src: { node: cc-build, port: command }, dst: { node: cc-run, port: command } }
- { src: { node: cc-build, port: test },    dst: { node: cc-int, port: test } }
- { src: { node: cc-build, port: simv },    dst: { node: cc-int, port: simv } }
- { src: { node: cc-run },                  dst: { node: cc-int, port: proc } }      # cc-run emits proc on default
- { src: { node: cc-int,   port: test }, dst: { node: gate-comp, port: test } }      # cc-int.fail → results-summary
- { src: { node: cc-int,   port: simv }, dst: { node: gate-comp, port: simv } }
- { src: { node: gate-comp, port: test }, dst: { node: runs, port: test } }          # gate-comp.stop → results-summary (drops test+simv together)
- { src: { node: gate-comp, port: simv }, dst: { node: runs, port: simv } }
# Run fan-out: expand-runs joins test+simv at the test key, re-keys test/run_id/simv per run_id.
- { src: { node: runs, port: test },   dst: { node: seed, port: test } }
- { src: { node: runs, port: run_id }, dst: { node: seed, port: run_id } }
- { src: { node: runs, port: simv },   dst: { node: seed, port: simv } }
- { src: { node: seed, port: test },   dst: { node: sim-build, port: test } }        # seed.fail → results-summary (REPLAY only)
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
- { src: { node: sim-int,  port: test }, dst: { node: gate-sim, port: test } }       # sim-int.timeout → results-summary
- { src: { node: sim-int,  port: proc }, dst: { node: gate-sim, port: proc } }
- { src: { node: gate-sim, port: test }, dst: { node: route-post, port: test } }     # gate-sim.stop → results-summary (drops test+proc together)
- { src: { node: gate-sim, port: proc }, dst: { node: route-post, port: proc } }
- { src: { node: route-post, port: uvm_test },   dst: { node: parse-uvm-log, port: test } }
- { src: { node: route-post, port: uvm_proc },   dst: { node: parse-uvm-log, port: proc } }
- { src: { node: route-post, port: plain_test }, dst: { node: parse-log, port: test } }
- { src: { node: route-post, port: plain_proc }, dst: { node: parse-log, port: proc } }
# parse-log.default / parse-uvm-log.default → results-summary

# ---- terminal result ports → results-summary (the `any` contract fans them in) ----
# Each of the 13 terminal outcomes is wired to its own results-summary contract port. The edges are
# required: false (the default) — the `any` contract fires on whichever is ready and requires none.
# Only the failure terminals log (a node logs only the errors it encounters): log.error
# (compile_failed/sim_timeout/model_*/sweep_*/preproc_*/filelist_*/replay_seed_*/parse_log_*/parse_uvm_*)
# — an exit driver, alongside results-summary.finalise()'s consolidated log.error("test_failures")
# on any FAIL row. The pass-like outcomes (parse-* PASS, filter.skip, gate-*.stop) are recorded by
# their TestResult only. git-status logs `git_state` with no edge (not a terminal) — console only.
- { src: { node: cc-int,        port: fail },    dst: { node: results-summary, port: compile_fail } }
- { src: { node: sim-int,       port: timeout }, dst: { node: results-summary, port: sim_timeout } }
- { src: { node: load-model,    port: fail },    dst: { node: results-summary, port: load_model } }
- { src: { node: filelist,      port: fail },    dst: { node: results-summary, port: filelist } }
- { src: { node: sweep,         port: fail },    dst: { node: results-summary, port: sweep } }
- { src: { node: preproc,       port: fail },    dst: { node: results-summary, port: preproc } }
- { src: { node: seed,          port: fail },    dst: { node: results-summary, port: seed } }
- { src: { node: parse-log,     port: default }, dst: { node: results-summary, port: parse_plain } }
- { src: { node: parse-uvm-log, port: default }, dst: { node: results-summary, port: parse_uvm } }
- { src: { node: filter,        port: skip },    dst: { node: results-summary, port: skip } }
- { src: { node: gate-pre,      port: stop },    dst: { node: results-summary, port: stop_pre } }
- { src: { node: gate-comp,     port: stop },    dst: { node: results-summary, port: stop_comp } }
- { src: { node: gate-sim,      port: stop },    dst: { node: results-summary, port: stop_sim } }
```

Notes:

- **One fan-in node, no relay.** The 13 result ports are wired to the `results-summary` node;
  the `any` contract *is* the fan-in (no separate `fan-in-results` relay), and the node renders the
  summary **results** table from the fanned-in `TestResult`s in its `finalise()` hook. The exit code
  is driven by `log.error` at two layers — each failure terminal's per-case event at origin, plus the
  consolidated `test_failures` error `finalise()` emits on any FAIL row. `git_state` is not a
  terminal — it falls through to the console, not into the table. See
  [05 — Re-convergence](05-branching-and-results.md#re-convergence-the-summary-returns-as-a-graph-node),
  [spec 10d](specs/10d-summarise-results.md), and [07 settled 27](07-ambiguities-and-assumptions.md).
  Adding a new terminal source means one new edge to a new `results-summary` contract port (declared
  in its `contract_port_mappings`) plus a `log.error` for the exit.
- The five `*_fail` ports (`load-model.fail`, `sweep.fail`, `preproc.fail`, `filelist.fail`,
  `seed.fail`) carry per-test config-domain failures via the `fail` output on each of those
  source modules → `results-summary`; each `log.error`s once under its own event name (an exit
  driver, alongside `results-summary.finalise()`'s consolidated `test_failures` check). See
  [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).
- `run_ids` (→ `runs`) is unwired for plain `test`; the module defaults it to `[None]`
  (single run). `randtest` wires it from a `rnd_cnt`-derived CLI edge.
- `filter`'s `reg_level`/`start_level` are persistent but unwired for `test`; the module's
  Python defaults (`None`) make it a pass-through. The `regression` graph wires them.
- `cc-int` `keyed_join`s three keyed edges (`test`, `simv`, `proc`) by key and co-gates
  `test`+`simv` on compile success; `simv` (born at `cc-build`) threads through `gate-comp`
  and `expand-runs` to `sim-build`.
- `gate-comp` is wired `{test, simv}` (so it is `keyed_join`, not `default`) — `expand-runs`
  needs `simv`, and co-gating requires `simv` to travel through the gate rather than bypass it,
  so a stop drops `test`+`simv` together. (`gate-pre` is now `{test, model}`/`keyed_join` — it
  co-gates the `model` edge load-model put in flight upstream, so a pre-phase stop drops
  `test`+`model` together and write-filelist's join can't dangle; `gate-sim` is
  `{test, proc}`/`keyed_join`.)
- `randseed` (`write-randseed`) `keyed_join`s `randseed` + a `proc` completion gate and is a
  side-effect leaf — it writes the `.randseed` file and emits a `randseed_done` ordering signal;
  there is **no** `test_run` bag. Post-sim is two parallel branches off `proc`: the side-effect
  branch (`randseed` → `link-latest`) and the classification branch (`sim-int` → `route-post` →
  `parse-*`), each `keyed_join`ing `test`/`proc` by key.
- `run-process` writes the `.log`/`.err` files itself (redirect, paths supplied in
  `command`) — there is no separate "write logs" node. `link-latest` only forces symlinks.
- **Artefact location is decided once and flows as data.** The artefact base is provided by the
  zero-input `work-dir` node (`work_dir = Path.cwd().resolve()` — test/randtest work in, and output
  to, CWD). `--logs-dir` (the subdir *name*) is a CLI edge to `ensure-logs` only. `ensure-logs`
  roots it on `work-dir`'s `work_dir` and emits the **resolved directory `Path`** on its `logs_dir`
  port, which fans out as a persistent input to the three composers `cc-build` / `sim-build` /
  `seed`. They join filenames onto that directory and never read the ambient CWD. Every other
  artefact follows the same model off `work-dir`'s `work_dir` directly: `filelist` roots
  `run.<tag>.f` (filename **and** contents), `cc-build` roots `obj_dir_<tag>/`, `randseed` reads
  `HierInstanceSeed.txt` from `work_dir`, `link-latest` places the `test.*` symlinks under it, and
  `cc-run`/`sim-run` launch the subprocess with `cwd=work_dir` — so the rtl_buddy "everything is
  CWD-relative" assumption is hoisted into the single `work-dir` provider (relocating artefacts is a
  `work-dir`-only change; regression feeds these ports its per-suite `suite_dir` instead).
  `write-randseed` does **not** take `logs_dir` —
  `sim-build` pre-composes `randseed_path` onto the `randseed` edge (and `log`/`err` become
  `command`'s redirect paths, echoed back on `proc`), which `randseed`/`link-latest` read by key;
  `randseed` takes `work_dir` only for the `HierInstanceSeed.txt` read. The default `"logs"`
  matches rtl_buddy's hard-coded literal; override is a small Notable divergence (see
  [07 settled 26](07-ambiguities-and-assumptions.md)).
- `load-model` sits after `filter` (so models for skipped tests aren't loaded) but **before**
  `sweep`/`preproc` — the resolved `ModelConfig` must exist when those hooks run so each can
  expose it to its script as `test_cfg.model`, matching rtl_buddy, which resolves the model at
  suite-load (`config/suite.py:46` → `test.py:320-323`) before sweep/preproc run. The `model`
  edge then rides alongside `test` (re-keyed `#i` across the sweep fan-out, co-gated by
  `gate-pre`) to `write-filelist`, its consumer. Still lazier than rtl_buddy's eager-for-all-tests
  load (07, item on model loading).

## Manifest additions — `modules/config.yaml`

```yaml
- file: rtl_buddy/setup.py
  plugins:
  - { name: discover-config-file, class_name: DiscoverConfigFileMod }
  - { name: prepend-cwd-path,     class_name: PrependCwdPathMod }
  - { name: parse-root-config,    class_name: ParseRootConfigMod }
  - { name: select-platform,      class_name: SelectPlatformMod }
  - { name: resolve-builder,      class_name: ResolveBuilderMod }
  - { name: work-dir,             class_name: WorkDirMod }
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
- file: rtl_buddy/summarise_results.py
  plugins:
  - { name: summarise-results, class_name: SummariseResultsMod }   # the in-graph results-summary sink (10d); no fan-in-results / aggregate-results relay
```

## Logging plugin — `graphs/log/summary.py` (dormant, not wired)

`graphs/test.yaml` has **no `logging` block** — the in-graph `results-summary` node renders the
table. The `SummaryProcessor` plugin (a stateful structlog processor — **not** a `logging.Handler`)
is retained as reference/standby infra but **dormant**: it would be referenced by `path`/`name` in a
`logging` block (per-graph logging entries resolve files relative to the graph file's directory,
`docs/harness_configs/graph.md`), but `test` does not opt in. Sketch in
[05](05-branching-and-results.md#the-summaryprocessor-logging-plugin); spec in
[10c](specs/10c-summary-handler.md) (superseded by [10d](specs/10d-summarise-results.md)).

## Manifest addition — `contracts/config.yaml`

```yaml
- file: any.py
  plugins:
  - { name: any, class_name: AnyContract }
```

`any.py` contains `AnyContract` (sketch in [spec 02](specs/02-any-contract-and-fan-in.md)),
a plain general-purpose contract. **It backs the `results-summary` fan-in** (spec
[10d](specs/10d-summarise-results.md)) — its 13 input ports are the terminal `TestResult` edges,
funnelled onto `result` by `contract_config: { mapping: result }` — and stays reusable by any other
graph. There is **no** `serial.py` / `serial_acquire` contract; parallel safety comes
from per-tag artefact naming (`write-filelist` writes `run.<tag>.f`; see
[05 — Interim CWD-collision posture](05-branching-and-results.md#interim-cwd-collision-posture--per-tag-artefact-naming)).
Do not re-introduce a lock for the residual CWD collisions — those are the job of the upstream
per-invocation-subdir change ([07](07-ambiguities-and-assumptions.md) item 17).

The modules **reimplement** `rtl_buddy` natively; only the config-schema dataclasses are kept
identical, so existing `root_config.yaml`/`tests.yaml`/`models.yaml` load drop-in — see
[07](07-ambiguities-and-assumptions.md) item 1. The package name (`modules/rtl_buddy/`) and
the file grouping above are **pinned**, not a suggestion — see
[specs/README.md — Module package layout](specs/README.md#module-package-layout-pinned).
