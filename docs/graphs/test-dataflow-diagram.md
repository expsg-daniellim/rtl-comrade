# `test` Graph Dataflow Diagram

[Back to the `test` graph](test.md) · [graphs index](index.md)

The full dataflow of the `test` graph, rendered inline by GitHub. Node labels note the pairing contract in parentheses; edge labels show the payloads carried (`port:Type`, with `#124;` rendering as `|`). Colour key: solid blue = main line, amber dashed = persistent config, purple = env / work-dir, green = CLI inputs.

```mermaid
flowchart TD
  route_list["route-list"] m1@-->|"run:SuiteConfig"| select["select"]
  select m2@-->|"test:TestConfig"| filter["filter"]
  filter m3@-->|"test:TestConfig"| model_ref["model-ref"]
  filter m3a@-->|"test:TestConfig"| load_model["load-model<br/>(keyed_join)"]
  filter m3b@-->|"test:TestConfig"| sweep["sweep<br/>(keyed_join)"]
  model_ref m3c@-->|"model_name:KeyedValue[str] + model_path:KeyedValue[Path]"| load_model
  load_model m4@-->|"model:KeyedValue[ModelConfig]"| sweep
  sweep m5@-->|"test:TestConfig + model:KeyedValue[ModelConfig]"| preproc["preproc<br/>(keyed_join)"]
  preproc m6@-->|"test:TestConfig + model:KeyedValue[ModelConfig]"| gate_pre["gate-pre<br/>(keyed_join)"]
  gate_pre m7@-->|"test:TestConfig + model:KeyedValue[ModelConfig]"| filelist["filelist<br/>(keyed_join)"]
  filelist m8@-->|"test:TestConfig + filelist:KeyedValue[Path]"| cc_build["cc-build<br/>(keyed_join)"]
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
  route_list m25@-->|"list:SuiteConfig"| list_names["list-names<br/>(prints names; exit 0)"]

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
  seed_mode["seed-mode"] c11@-. "seed_mode:SeedMode" .-> seed
  parse_suite["parse-suite"] c12@-. "suite_cfg:SuiteConfig" .-> route_list

  prepend_path["prepend-path"] e1@-->|"env_ready:bool"| cc_run
  prepend_path e2@-->|"env_ready:bool"| sim_run
  work_dir_node e3@-->|"work_dir:Path"| filelist
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
  c_test_name(["test_name"]) g4@-->|"test_name:str"| select
  c_list(["list"]) g5@-->|"list:bool"| route_list
  c_rnd_new(["rnd_new"]) g6@-->|"rnd_new:bool"| seed_mode
  c_rnd_last(["rnd_last"]) g7@-->|"rnd_last:bool"| seed_mode
  c_builder_mode(["builder_mode"]) g8@-->|"builder_mode:str"| cc_build
  c_builder_mode g9@-->|"builder_mode:str"| sim_build
  c_early_stop(["early_stop"]) g10@-->|"early_stop:str"| gate_pre
  c_early_stop g11@-->|"early_stop:str"| gate_comp
  c_early_stop g12@-->|"early_stop:str"| gate_sim

  git_status["git-status"] gs1@-. "log git_state (→ console)" .-> GS(["console"])

  classDef fanout fill:#e6f2ff,stroke:#1f6feb;
  classDef join fill:#fff3cd,stroke:#bf8700;
  classDef cli fill:#eef7ee,stroke:#2da44e;
  class select,sweep,runs fanout;
  class load_model,filelist,cc_build,cc_int,seed,sim_build,randseed,link_latest,sim_int,gate_comp,gate_sim,route_post,parse_log,parse_uvm join;
  class c_test_config,c_logs_dir,c_builder,c_test_name,c_list,c_rnd_new,c_rnd_last,c_builder_mode,c_early_stop cli;

  %% edge styling by class — each styled edge has a unique ID; per-type class lists below.
  %% Inserting/removing an edge: add/remove its ID in one list; no positional renumbering.
  classDef mainEdge stroke:#1f6feb,stroke-width:2px;
  classDef cfgEdge stroke:#bf8700,stroke-width:1.5px;
  classDef envEdge stroke:#8250df,stroke-width:1.5px;
  classDef cliEdge stroke:#1a7f37,stroke-width:1.5px;
  classDef gitEdge stroke:#6e7781,stroke-width:1px;
  class m1,m2,m3,m3a,m3b,m3c,m4,m5,m6,m7,m8,m9,m10,m11,m12,m13,m14,m15,m16,m17,m17b,m17c,m18,m18b,m18c,m19,m21,m22,m23,m24,m25 mainEdge;
  class c1,c2,c3,c5,c6,c7,c8,c9,c10,c11,c12 cfgEdge;
  class e1,e2,e3,e4,e5,e6,e7,e8,e9,e10,e11,e12 envEdge;
  class g1,g2,g3,g4,g5,g6,g7,g8,g9,g10,g11,g12 cliEdge;
  class gs1 gitEdge;
```
