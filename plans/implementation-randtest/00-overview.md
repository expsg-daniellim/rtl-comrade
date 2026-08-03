# Overview

## Goal

Port `rtl_buddy`'s `do_rand_test` command as a sibling `rtl-comrade` graph, derived from the existing `test` graph (`graphs/test.yaml`). The changes are small: one new module, CLI rewiring, removal of list mode.

> **Baseline.** This plan depends on the completed `test` graph and all modules in `modules/rtl_buddy/`. The pinned rtl_buddy version and the `Compatibility source:` citation rules are those of [implementation-test's overview](../implementation-test/00-overview.md#goal).

## Why a sibling graph

`randtest` differs from `test` in three ways:

1. **Seed derivation.** `test` wires `derive-seed-mode` (two booleans `rnd_new`/`rnd_last` → `SeedMode`). `randtest` replaces it with `derive-randtest-runs`, which collapses `rnd_cnt`/`rnd_rpt` into `run_ids` + `seed_mode` — a different CLI surface driving the same downstream `runs`/`seed` nodes.
2. **No list mode.** `test` has `route-list` (`flag-gate`) routing `parse-suite` to either `list-names` or `select`. `randtest` drops the gate and wires `parse-suite` directly to `select`.
3. **Required test name.** `test` defaults `test_name` to `""`. `randtest` makes it a required positional (no `default` field in the CLI edge).

Everything else carries over unchanged — setup chain, selection/expansion, filelist pipeline, compile, sim, post, logging, persistent-input configs.

## Full graph

The full dataflow of the `randtest` graph. Colour key: solid blue = main line, amber dashed = persistent config, purple = env / work-dir, green = CLI inputs, red = delta nodes/edges (new or rewired vs `test.yaml`).

```mermaid
flowchart TD
  parse_suite["parse-suite"] m1@-->|"suite_cfg:SuiteConfig"| select["select"]
  select m2@-->|"test:TestConfig"| filter["filter"]
  filter m3@-->|"test:TestConfig"| model_ref["model-ref"]
  filter m3a@-->|"test:TestConfig"| load_model["load-model<br/>(keyed_join)"]
  filter m3b@-->|"test:TestConfig"| sweep["sweep<br/>(keyed_join)"]
  model_ref m3c@-->|"model_name:KeyedValue[str] + model_path:KeyedValue[Path]"| load_model
  load_model m4@-->|"model:KeyedValue[ModelConfig]"| sweep
  sweep m5@-->|"test:TestConfig + model:KeyedValue[ModelConfig]"| preproc["preproc<br/>(keyed_join)"]
  preproc m6@-->|"test:TestConfig + model:KeyedValue[ModelConfig]"| gate_pre["gate-pre<br/>(keyed_join)"]
  gate_pre p1@-->|"test:TestConfig"| fl_model_ref["fl-model-ref"]
  gate_pre p2@-->|"model:KeyedValue[ModelConfig]"| fl_model["fl-model<br/>(filelist-extract, keyed_join)"]
  gate_pre p3@-->|"test:TestConfig"| fl_tb["fl-tb<br/>(filelist-extract, keyed_join)"]
  gate_pre p9@-->|"test:TestConfig"| fl_path["fl-path<br/>(filelist-path, keyed_join)"]
  gate_pre p10@-->|"test:TestConfig"| filelist["filelist<br/>(write-filelist, keyed_join)"]
  fl_model_ref p4@-->|"model_path:KeyedValue[Path]"| fl_model_root["fl-model-root<br/>(dirname, keyed_join)"]
  fl_model_root p5@-->|"base_dir:Path"| fl_model
  fl_model p6@-->|"entries:list[entry]"| fl_merge["fl-merge<br/>(prioritised-merge, keyed_join)"]
  fl_tb p7@-->|"entries:list[entry]"| fl_merge
  fl_merge p8@-->|"entries:list[entry]"| fl_norm["fl-norm<br/>(filelist-normalise, keyed_join)"]
  fl_norm p11@-->|"entries:list[entry]"| fl_dedup["fl-dedup<br/>(filelist-dedup, keyed_join)"]
  fl_dedup p12@-->|"entries:list[entry]"| filelist
  fl_path p13@-->|"path:Path"| filelist
  filelist m8@-->|"filelist:KeyedValue[Path]"| cc_build["cc-build<br/>(keyed_join)"]
  gate_pre m7@-->|"test:TestConfig"| cc_build
  cc_build m9@-->|"command:Command"| cc_run["cc-run<br/>(run-process)"]
  cc_build m10@-->|"test:TestConfig + simv:KeyedValue[str]"| cc_int["cc-int<br/>(keyed_join)"]
  cc_run m11@-->|"proc:Proc"| cc_int
  cc_int m12@-->|"test:TestConfig + simv:KeyedValue[str]"| gate_comp["gate-comp<br/>(keyed_join)"]
  gate_comp m13@-->|"test:TestConfig + simv:KeyedValue[str]"| runs["runs<br/>(keyed_join)"]
  runs m14@-->|"test:TestConfig + run_id:KeyedValue[int#124;None] + simv:KeyedValue[str]"| seed["seed<br/>(keyed_join)"]
  seed m15@-->|"test:TestConfig + run_id:KeyedValue[int#124;None] + simv:KeyedValue[str] + seed:KeyedValue[int]"| sim_build["sim-build<br/>(keyed_join)"]
  sim_build m16@-->|"command:Command + timeout:KeyedValue[float#124;None]"| sim_run["sim-run<br/>(keyed_join)"]
  sim_build m17@-->|"randseed:RandSeed"| randseed["write-randseed<br/>(keyed_join)"]
  sim_build m17b@-->|"randseed:RandSeed"| link_latest["link-latest<br/>(keyed_join)"]
  sim_build m17c@-->|"test:TestConfig"| sim_int["sim-int<br/>(keyed_join)"]
  sim_run m18@-->|"proc:Proc (gate)"| randseed
  sim_run m18b@-->|"proc:Proc"| link_latest
  sim_run m18c@-->|"proc:Proc"| sim_int
  randseed m19@-->|"randseed_done:RandSeedDone"| link_latest
  sim_int m21@-->|"test:TestConfig + proc:Proc"| gate_sim["gate-sim<br/>(keyed_join)"]
  gate_sim m22@-->|"test:TestConfig + proc:Proc"| route_post["route-post<br/>(keyed_join)"]
  route_post m23@-->|"plain: test:TestConfig + proc:Proc"| parse_log["parse-log<br/>(keyed_join)"]
  route_post m24@-->|"uvm: test:TestConfig + proc:Proc"| parse_uvm["parse-uvm-log<br/>(keyed_join)"]

  derive_runs["derive-runs<br/>(derive-randtest-runs, unit)"] d1@-->|"run_ids:list[int]"| runs
  derive_runs d2@-->|"seed_mode:SeedMode"| seed

  discover_root["discover-root"] c1@-->|"path:Path"| parse_root["parse-root"]
  parse_root c2@-->|"root_cfg:RootConfig"| select_platform["select-platform"]
  select_platform c3@-->|"platform_cfg:PlatformConfig"| resolve_builder["resolve-builder"]
  work_dir_node["work-dir"] e12@-->|"work_dir:Path"| ensure_logs["ensure-logs"]
  parse_root c5@-. "root_cfg:RootConfig" .-> sweep
  parse_root c6@-. "root_cfg:RootConfig" .-> preproc
  resolve_builder c7@-. "builder_cfg:RtlBuilderConfig" .-> filter
  resolve_builder c8@-. "builder_cfg:RtlBuilderConfig" .-> cc_build
  resolve_builder c9@-. "builder_cfg:RtlBuilderConfig" .-> seed
  resolve_builder c10@-. "builder_cfg:RtlBuilderConfig" .-> sim_build

  unroll_node["unroll<br/>(constant)"] u1@-->|"unroll:bool"| fl_model
  unroll_node u2@-->|"unroll:bool"| fl_tb
  prepend_path["prepend-path"] e1@-->|"env_ready:bool"| cc_run
  prepend_path e2@-->|"env_ready:bool"| sim_run
  work_dir_node e3@-->|"base_dir:Path"| fl_tb
  work_dir_node e3b@-->|"base_dir:Path"| fl_norm
  work_dir_node e3c@-->|"work_dir:Path"| fl_path
  work_dir_node e4@-->|"work_dir:Path"| cc_build
  work_dir_node e5@-->|"work_dir:Path"| cc_run
  work_dir_node e9@-->|"work_dir:Path"| sim_run
  work_dir_node e10@-->|"work_dir:Path"| randseed
  work_dir_node e11@-->|"work_dir:Path"| link_latest
  ensure_logs e6@-->|"logs_dir:Path"| cc_build
  ensure_logs e7@-->|"logs_dir:Path"| sim_build
  ensure_logs e8@-->|"logs_dir:Path"| seed

  c_test_config(["test_config"]) g1@-->|"test_config:str"| parse_suite
  c_logs_dir(["logs_dir (name)"]) g2@-->|"logs_dir:str"| ensure_logs
  c_builder(["builder"]) g3@-->|"builder:str"| resolve_builder
  c_test_name(["test_name<br/>(required)"]) g4@-->|"test_name:str"| select
  c_rnd_cnt(["rnd_cnt"]) g5@-->|"rnd_cnt:int"| derive_runs
  c_rnd_rpt(["rnd_rpt"]) g6@-->|"rnd_rpt:int"| derive_runs
  c_builder_mode(["builder_mode"]) g8@-->|"builder_mode:str"| cc_build
  c_builder_mode g9@-->|"builder_mode:str"| sim_build
  c_early_stop(["early_stop"]) g10@-->|"early_stop:str"| gate_pre
  c_early_stop g11@-->|"early_stop:str"| gate_comp
  c_early_stop g12@-->|"early_stop:str"| gate_sim

  git_status["git-status"] gs1@-. "log git_state (→ console)" .-> GS(["console"])

  classDef fanout fill:#e6f2ff,stroke:#1f6feb;
  classDef join fill:#fff3cd,stroke:#bf8700;
  classDef cli fill:#eef7ee,stroke:#2da44e;
  classDef delta fill:#fde8e8,stroke:#cf222e,stroke-width:2px;
  class select,sweep,runs fanout;
  class load_model,fl_model_root,fl_model,fl_tb,fl_merge,fl_norm,fl_dedup,fl_path,filelist,cc_build,cc_int,seed,sim_build,randseed,link_latest,sim_int,gate_comp,gate_sim,route_post,parse_log,parse_uvm join;
  class c_test_config,c_logs_dir,c_builder,c_test_name,c_rnd_cnt,c_rnd_rpt,c_builder_mode,c_early_stop cli;
  class derive_runs delta;

  classDef mainEdge stroke:#1f6feb,stroke-width:2px;
  classDef cfgEdge stroke:#bf8700,stroke-width:1.5px;
  classDef envEdge stroke:#8250df,stroke-width:1.5px;
  classDef cliEdge stroke:#1a7f37,stroke-width:1.5px;
  classDef gitEdge stroke:#6e7781,stroke-width:1px;
  classDef deltaEdge stroke:#cf222e,stroke-width:2px;
  class m2,m3,m3a,m3b,m3c,m4,m5,m6,p1,p2,p3,p4,p5,p6,p7,p8,p9,p10,p11,p12,p13,m7,m8,m9,m10,m11,m12,m13,m14,m15,m16,m17,m17b,m17c,m18,m18b,m18c,m19,m21,m22,m23,m24 mainEdge;
  class c1,c2,c3,c5,c6,c7,c8,c9,c10 cfgEdge;
  class e1,e2,e3,e3b,e3c,e4,e5,e6,e7,e8,e9,e10,e11,e12,u1,u2 envEdge;
  class g1,g2,g3,g4,g8,g9,g10,g11,g12 cliEdge;
  class gs1 gitEdge;
  class m1,d1,d2,g5,g6 deltaEdge;
```

## Graph delta summary

### Nodes removed (vs `test.yaml`)

| ID | Module | Reason |
|---|---|---|
| `seed-mode` | `derive-seed-mode` | Replaced by `derive-runs` |
| `route-list` | `flag-gate` | No list mode in randtest |
| `list-names` | `list-test-names` | No list mode in randtest |

### Nodes added

| ID | Module | Contract |
|---|---|---|
| `derive-runs` | `derive-randtest-runs` | `unit` |

### Edges removed

```yaml
# seed-mode wiring
- { src: { cli: rnd_new, ... },  dst: { node: seed-mode, port: rnd_new } }
- { src: { cli: rnd_last, ... }, dst: { node: seed-mode, port: rnd_last } }
- { src: { node: seed-mode },    dst: { node: seed, port: seed_mode } }

# list-mode wiring
- { src: { cli: list, ... },              dst: { node: route-list, port: flag } }
- { src: { node: parse-suite },           dst: { node: route-list, port: value } }
- { src: { node: route-list, port: "on" },  dst: { node: list-names, port: suite_cfg } }
- { src: { node: route-list, port: "off" }, dst: { node: select, port: suite_cfg } }
```

### Edges added

```yaml
# derive-randtest-runs CLI inputs
- { src: { cli: rnd_cnt, option: false, type: int, default: 2 }, dst: { node: derive-runs, port: rnd_cnt } }
- { src: { cli: rnd_rpt, type: int, default: -1 },              dst: { node: derive-runs, port: rnd_rpt } }

# derive-randtest-runs outputs
- { src: { node: derive-runs, port: run_ids },   dst: { node: runs, port: run_ids } }
- { src: { node: derive-runs, port: seed_mode }, dst: { node: seed, port: seed_mode } }

# parse-suite direct to select (no route-list)
- { src: { node: parse-suite }, dst: { node: select, port: suite_cfg } }
```

### Edges changed

```yaml
# test_name: remove default to make it required
- { src: { cli: test_name, option: false, type: str }, dst: { node: select, port: test_name } }
# (was: { cli: test_name, option: false, type: str, default: "" })
```

### Everything else

All of the following carry over unchanged from `test.yaml`:

- setup chain: `discover-root`, `prepend-path`, `parse-root`, `select-platform`, `resolve-builder`, `work-dir`, `ensure-logs`, `parse-suite`, `git-status`
- selection / expansion: `select`, `filter`, `model-ref`, `load-model`, `sweep`
- per-test prep: `preproc`, `gate-pre`
- filelist pipeline: `unroll`, `fl-model-ref`, `fl-model-root`, `fl-model`, `fl-tb`, `fl-merge`, `fl-norm`, `fl-dedup`, `fl-path`, `filelist`
- compile: `cc-build`, `cc-run`, `cc-int`, `gate-comp`
- sim: `runs`, `seed`, `sim-build`, `sim-run`, `randseed`, `link-latest`, `sim-int`, `gate-sim`
- post: `route-post`, `parse-log`, `parse-uvm-log`
- `logging:` block (both summary processors)
- all persistent-input contract configs
- all `work_dir`, `env_ready`, `logs_dir`, `builder_cfg`, `root_cfg` fan-out edges

## CLI surface

Matching rtl_buddy's `do_rand_test` signature.

| arg | flag / position | type | default | destination |
|---|---|---|---|---|
| `test_name` | positional (**required**) | str | — | `select.test_name` |
| `rnd_cnt` | positional | int | 2 | `derive-runs.rnd_cnt` |
| `rnd_rpt` | `-r/--rnd-rpt` | int | -1 | `derive-runs.rnd_rpt` |
| `test_config` | `-c/--test-config` | str | `tests.yaml` | `parse-suite.test_config` |
| `logs_dir` | `--logs-dir` | str | `logs` | `ensure-logs.logs_dir` |
| `builder` | `--builder` | str | `""` | `resolve-builder.builder` |
| `builder_mode` | `-M/--builder-mode` | str | `debug` | `cc-build.builder_mode`, `sim-build.builder_mode` |
| `early_stop` | `--early-stop` | str | `post` | `gate-pre`, `gate-comp`, `gate-sim` |

**Removed from test:** `rnd_new`, `rnd_last` (replaced by `derive-randtest-runs`), `list` (randtest has no list mode).

**Changed from test:** `test_name` becomes required (no `default` field in the CLI edge — the harness infers a required positional).

## Acceptance criteria

- `DeriveRandtestRunsMod` unit tests pass.
- `graphs/randtest.yaml` loads without structural validation errors at startup.
- The `randtest` subcommand appears in `rtl-comrade --help`.
- A basic `randtest` run against the fixture project completes with the expected number of sim invocations.
- The graph is structurally identical to `test.yaml` except for the documented deltas above — no accidental omissions or additions.
