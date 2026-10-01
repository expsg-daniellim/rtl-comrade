# `regression` Graph Dataflow Diagram

[Back to the `regression` graph](regression.md) · [graphs index](index.md)

The full dataflow of the `regression` graph, rendered inline by GitHub. Node labels note the pairing contract in parentheses; edge labels show the payloads carried (`port:Type`, with `#124;` rendering as `|`). Colour key: solid blue = main line, amber dashed = persistent config, purple = env, green = CLI inputs, red = delta nodes/edges (new or rewired vs [`test`](test-dataflow-diagram.md)).

```mermaid
flowchart TD
  resolve_reg["resolve-reg-path"] d1@-->|"reg_config_path:Path"| parse_reg["parse-reg"]
  parse_reg d2@-->|"test_config:Path"| parse_suite["parse-suite<br/>(prefix_suite: true,<br/>default)"]
  parse_suite d3@-->|"suite_cfg:SuiteConfig"| select["select"]
  select m2@-->|"test:TestConfig"| filter["filter"]
  filter m3@-->|"test:TestConfig"| model_ref["model-ref"]
  filter m3a@-->|"test:TestConfig"| load_model["load-model<br/>(keyed_join)"]
  filter m3b@-->|"test:TestConfig"| sweep["sweep<br/>(keyed_join)"]
  model_ref m3c@-->|"model_name:KeyedValue[str] + model_path:KeyedValue[Path]"| load_model
  load_model m4@-->|"model:KeyedValue[ModelConfig]"| sweep
  sweep m5@-->|"test:TestConfig + model:KeyedValue[ModelConfig]"| preproc["preproc<br/>(keyed_join)"]
  preproc m6@-->|"test:TestConfig + model:KeyedValue[ModelConfig]"| gate_pre["gate-pre<br/>(keyed_join)"]

  gate_pre p1@-->|"test:TestConfig"| fl_model_ref["fl-model-ref"]
  gate_pre p2@-->|"model:KeyedValue[ModelConfig]"| fl_model["fl-model<br/>(keyed_join)"]
  gate_pre p3@-->|"test:TestConfig"| fl_tb["fl-tb<br/>(keyed_join)"]
  gate_pre p9@-->|"test:TestConfig"| fl_path["fl-path<br/>(keyed_join)"]
  gate_pre p10@-->|"test:TestConfig"| filelist["filelist<br/>(keyed_join)"]
  fl_model_ref p4@-->|"model_path:KeyedValue[Path]"| fl_model_root["fl-model-root<br/>(keyed_join)"]
  fl_model_root p5@-->|"base_dir:Path"| fl_model
  fl_model p6@-->|"entries:list[entry]"| fl_merge["fl-merge<br/>(keyed_join)"]
  fl_tb p7@-->|"entries:list[entry]"| fl_merge
  fl_merge p8@-->|"entries:list[entry]"| fl_norm["fl-norm<br/>(keyed_join)"]
  fl_norm p11@-->|"entries:list[entry]"| fl_dedup["fl-dedup<br/>(keyed_join)"]
  fl_dedup p12@-->|"entries:list[entry]"| filelist
  fl_path p13@-->|"path:Path"| filelist
  filelist m8@-->|"filelist:KeyedValue[Path]"| cc_build["cc-build<br/>(keyed_join)"]

  gate_pre m7@-->|"test:TestConfig"| cc_build
  cc_build m9@-->|"command:Command"| cc_run["cc-run<br/>(keyed_join)"]
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

  const_seed["const-seed-mode<br/>(constant, SeedMode.DEFAULT)"] d4@-->|"seed_mode:SeedMode"| seed

  gate_pre d5@-->|"test:TestConfig"| extract_dir["extract-dir<br/>(extract-suite-dir)"]
  extract_dir d6@-->|"base_dir:KeyedValue[Path]"| cc_build
  extract_dir d7@-->|"base_dir:KeyedValue[Path]"| cc_run
  extract_dir d8@-->|"base_dir:KeyedValue[Path]"| fl_tb
  extract_dir d9@-->|"base_dir:KeyedValue[Path]"| fl_norm
  extract_dir d10@-->|"base_dir:KeyedValue[Path]"| fl_path
  extract_dir d11@-->|"logs_dir:KeyedValue[Path]"| cc_build

  runs d12@-->|"test:TestConfig"| extract_dir_post["extract-dir-post<br/>(extract-suite-dir)"]
  extract_dir_post d13@-->|"base_dir:KeyedValue[Path]"| sim_run
  extract_dir_post d14@-->|"base_dir:KeyedValue[Path]"| randseed
  extract_dir_post d15@-->|"base_dir:KeyedValue[Path]"| link_latest
  extract_dir_post d16@-->|"logs_dir:KeyedValue[Path]"| sim_build
  extract_dir_post d17@-->|"logs_dir:KeyedValue[Path]"| seed

  discover_root["discover-root"] c1@-->|"path:Path"| parse_root["parse-root"]
  parse_root c2@-->|"root_cfg:RootConfig"| select_platform["select-platform"]
  select_platform c3@-->|"platform_cfg:PlatformConfig"| resolve_builder["resolve-builder"]
  parse_root d18@-->|"root_cfg:RootConfig"| resolve_reg
  discover_root d19@-->|"root_cfg_path:Path"| resolve_reg
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

  c_reg_config(["reg_config"]) g1@-->|"reg_config:str"| resolve_reg
  c_reg_level(["reg_level"]) g2@-->|"reg_level:int"| filter
  c_start_level(["start_level"]) g3@-->|"start_level:int"| filter
  c_logs_dir(["logs_dir (name)"]) g4@-->|"logs_dir:str"| extract_dir
  c_logs_dir g4b@-->|"logs_dir:str"| extract_dir_post
  c_builder(["builder"]) g5@-->|"builder:str"| resolve_builder
  c_builder_mode(["builder_mode<br/>(default: reg)"]) g6@-->|"builder_mode:str"| cc_build
  c_builder_mode g7@-->|"builder_mode:str"| sim_build
  c_early_stop(["early_stop"]) g8@-->|"early_stop:str"| gate_pre
  c_early_stop g9@-->|"early_stop:str"| gate_comp
  c_early_stop g10@-->|"early_stop:str"| gate_sim

  git_status["git-status"] gs1@-. "log git_state (→ console)" .-> GS(["console"])

  classDef fanout fill:#e6f2ff,stroke:#1f6feb;
  classDef join fill:#fff3cd,stroke:#bf8700;
  classDef cli fill:#eef7ee,stroke:#2da44e;
  classDef delta fill:#fde8e8,stroke:#cf222e,stroke-width:2px;
  class select,sweep,runs fanout;
  class load_model,fl_model_root,fl_model,fl_tb,fl_merge,fl_norm,fl_dedup,fl_path,filelist,cc_build,cc_run,cc_int,seed,sim_build,randseed,link_latest,sim_int,gate_comp,gate_sim,route_post,parse_log,parse_uvm join;
  class c_reg_config,c_reg_level,c_start_level,c_logs_dir,c_builder,c_builder_mode,c_early_stop cli;
  class resolve_reg,parse_reg,parse_suite,const_seed,extract_dir,extract_dir_post,cc_run delta;

  classDef mainEdge stroke:#1f6feb,stroke-width:2px;
  classDef cfgEdge stroke:#bf8700,stroke-width:1.5px;
  classDef envEdge stroke:#8250df,stroke-width:1.5px;
  classDef cliEdge stroke:#1a7f37,stroke-width:1.5px;
  classDef gitEdge stroke:#6e7781,stroke-width:1px;
  classDef deltaEdge stroke:#cf222e,stroke-width:2px;
  class m2,m3,m3a,m3b,m3c,m4,m5,m6,p1,p2,p3,p4,p5,p6,p7,p8,p9,p10,p11,p12,p13,m7,m8,m9,m10,m11,m12,m13,m14,m15,m16,m17,m17b,m17c,m18,m18b,m18c,m19,m21,m22,m23,m24 mainEdge;
  class c1,c2,c3,c5,c6,c7,c8,c9,c10 cfgEdge;
  class e1,e2,u1,u2 envEdge;
  class g5,g6,g7,g8,g9,g10 cliEdge;
  class gs1 gitEdge;
  class d1,d2,d3,d4,d5,d6,d7,d8,d9,d10,d11,d12,d13,d14,d15,d16,d17,d18,d19,g1,g2,g3,g4,g4b deltaEdge;
```
