# Overview

## Goal

Port `rtl_buddy`'s `do_rtl_regression` command as a sibling `rtl-comrade` graph, derived from the existing `test` graph (`graphs/test.yaml`). This is the larger of the two sibling ports — multiple suites, per-suite working directories, level filtering, and a streaming suite pipeline all interact with the existing test graph's persistent-input wiring.

> **Baseline.** This plan depends on the completed `test` graph and all modules in `modules/rtl_buddy/`. The pinned rtl_buddy version and the `Compatibility source:` citation rules are those of [implementation-test's overview](../implementation-test/00-overview.md#goal).

## Why a sibling graph

`regression` differs from `test` in five ways:

1. **Suite pipeline.** `test` reads one suite config from the CLI. `regression` reads a `regressions.yaml` listing N suite configs, resolves each path, and streams them into `parse-suite-config` under a `default` contract (not `unit`).
2. **Per-suite `work_dir` and `logs_dir`.** `test` emits `Path.cwd().resolve()` once via `work-dir` and fans it out as a persistent input. Regression has no single CWD — each suite's working directory is `suite_dir` from `parse-suite-config`. Two `ExtractSuiteDirMod` instances (pre- and post-fan-out) replace `work-dir` and `ensure-logs`.
3. **Suite-key prefixing.** The correlation key becomes `<suite>/<test>#<sweep>#<run>` to distinguish same-named tests across suites and group the summary table by suite.
4. **Seed mode.** Always `SeedMode.DEFAULT` — no `--rnd-new`/`--rnd-last` CLI flags. A `constant` node replaces `derive-seed-mode`.
5. **No list mode.** The `route-list` / `list-names` / `list` CLI edge set is absent.

Everything else carries over unchanged — setup chain (minus `work-dir` and `ensure-logs`), selection/expansion, filelist pipeline, compile, sim, post, logging.

## Full graph

The full dataflow of the `regression` graph. Colour key: solid blue = main line, amber dashed = persistent config, purple = env, green = CLI inputs, red = delta nodes/edges (new or rewired vs `test.yaml`).

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

  const_seed["const-seed-mode<br/>(constant, SeedMode.DEFAULT)"] d4@-->|"seed_mode:SeedMode"| seed

  gate_pre d5@-->|"test:TestConfig"| extract_dir["extract-dir<br/>(extract-suite-dir)"]
  extract_dir d6@-->|"work_dir:KeyedValue[Path]"| cc_build
  extract_dir d7@-->|"work_dir:KeyedValue[Path]"| cc_run
  extract_dir d8@-->|"base_dir:KeyedValue[Path]"| fl_tb
  extract_dir d9@-->|"base_dir:KeyedValue[Path]"| fl_norm
  extract_dir d10@-->|"work_dir:KeyedValue[Path]"| fl_path
  extract_dir d11@-->|"logs_dir:KeyedValue[Path]"| cc_build

  runs d12@-->|"test:TestConfig"| extract_dir_post["extract-dir-post<br/>(extract-suite-dir)"]
  extract_dir_post d13@-->|"work_dir:KeyedValue[Path]"| sim_run
  extract_dir_post d14@-->|"work_dir:KeyedValue[Path]"| randseed
  extract_dir_post d15@-->|"work_dir:KeyedValue[Path]"| link_latest
  extract_dir_post d16@-->|"logs_dir:KeyedValue[Path]"| sim_build
  extract_dir_post d17@-->|"logs_dir:KeyedValue[Path]"| seed

  discover_root["discover-root"] c1@-->|"path:Path"| parse_root["parse-root"]
  parse_root c2@-->|"root_cfg:RootConfig"| select_platform["select-platform"]
  select_platform c3@-->|"platform_cfg:PlatformConfig"| resolve_builder["resolve-builder"]
  parse_root d18@-->|"root_cfg:RootConfig"| resolve_reg
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
  class load_model,fl_model_root,fl_model,fl_tb,fl_merge,fl_norm,fl_dedup,fl_path,filelist,cc_build,cc_int,seed,sim_build,randseed,link_latest,sim_int,gate_comp,gate_sim,route_post,parse_log,parse_uvm join;
  class c_reg_config,c_reg_level,c_start_level,c_logs_dir,c_builder,c_builder_mode,c_early_stop cli;
  class resolve_reg,parse_reg,parse_suite,const_seed,extract_dir,extract_dir_post delta;

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
  class d1,d2,d3,d4,d5,d6,d7,d8,d9,d10,d11,d12,d13,d14,d15,d16,d17,d18,g1,g2,g3,g4,g4b deltaEdge;
```

## Graph delta summary

### Nodes removed (vs `test.yaml`)

| ID | Module | Reason |
|---|---|---|
| `seed-mode` | `derive-seed-mode` | Replaced by `const-seed-mode` |
| `route-list` | `flag-gate` | No list mode in regression |
| `list-names` | `list-test-names` | No list mode in regression |
| `work-dir` | `work-dir` | Per-suite `suite_dir` replaces global CWD |
| `ensure-logs` | `ensure-logs-dir` | Absorbed by `extract-dir` / `extract-dir-post` |

### Nodes added

| ID | Module | Contract |
|---|---|---|
| `resolve-reg-path` | `resolve-reg-config-path` | `unit` |
| `parse-reg` | `parse-reg-config` | `default` |
| `const-seed-mode` | `constant` (config: `SeedMode.DEFAULT`) | `default` |
| `extract-dir` | `extract-suite-dir` | `{ name: default, config: { persistent_inputs: [logs_dir] } }` |
| `extract-dir-post` | `extract-suite-dir` | `{ name: default, config: { persistent_inputs: [logs_dir] } }` |

### Nodes changed

| ID | Change |
|---|---|
| `parse-suite` | Contract switches from `unit` to `default`; config adds `prefix_suite: true` |
| `cc-build` | Remove `work_dir` and `logs_dir` from `persistent_inputs` |
| `cc-run` | Remove `work_dir` from `persistent_inputs` |
| `sim-build` | Remove `logs_dir` from `persistent_inputs` |
| `seed` | Remove `logs_dir` from `persistent_inputs` |
| `sim-run` | Remove `work_dir` from `persistent_inputs` |
| `randseed` | Remove `work_dir` from `persistent_inputs` |
| `link-latest` | Remove `work_dir` from `persistent_inputs` |
| `fl-tb` | Remove `base_dir` from `persistent_inputs` |
| `fl-norm` | Remove `base_dir` from `persistent_inputs` |
| `fl-path` | Remove `work_dir` from `persistent_inputs` |

### Edges removed

```yaml
# seed-mode
- { src: { cli: rnd_new, ... },  dst: { node: seed-mode, port: rnd_new } }
- { src: { cli: rnd_last, ... }, dst: { node: seed-mode, port: rnd_last } }
- { src: { node: seed-mode },    dst: { node: seed, port: seed_mode } }

# list-mode
- { src: { cli: list, ... },              dst: { node: route-list, port: flag } }
- { src: { node: parse-suite },           dst: { node: route-list, port: value } }
- { src: { node: route-list, port: "on" },  dst: { node: list-names, port: suite_cfg } }
- { src: { node: route-list, port: "off" }, dst: { node: select, port: suite_cfg } }

# test_name, test_config CLI edges
- { src: { cli: test_name, ... }, dst: { node: select, port: test_name } }
- { src: { cli: test_config, ... }, dst: { node: parse-suite, port: test_config } }

# work-dir fan-out (all edges from work-dir node)
- { src: { node: work-dir }, dst: { node: ensure-logs, port: work_dir } }
- { src: { node: work-dir }, dst: { node: cc-build,    port: work_dir } }
- { src: { node: work-dir }, dst: { node: cc-run,      port: work_dir } }
- { src: { node: work-dir }, dst: { node: sim-run,     port: work_dir } }
- { src: { node: work-dir }, dst: { node: randseed,    port: work_dir } }
- { src: { node: work-dir }, dst: { node: link-latest, port: work_dir } }
- { src: { node: work-dir }, dst: { node: fl-tb,       port: base_dir } }
- { src: { node: work-dir }, dst: { node: fl-norm,     port: base_dir } }
- { src: { node: work-dir }, dst: { node: fl-path,     port: work_dir } }

# ensure-logs (node removed; role absorbed by extract-dir)
- { src: { cli: logs_dir, ... },             dst: { node: ensure-logs, port: logs_dir } }
- { src: { node: ensure-logs, port: logs_dir }, dst: { node: cc-build,  port: logs_dir } }
- { src: { node: ensure-logs, port: logs_dir }, dst: { node: sim-build, port: logs_dir } }
- { src: { node: ensure-logs, port: logs_dir }, dst: { node: seed,      port: logs_dir } }
```

### Edges added

**Suite stream:**

```yaml
- { src: { cli: reg_config, type: str, default: "" }, dst: { node: resolve-reg-path, port: reg_config } }
- { src: { node: parse-root },       dst: { node: resolve-reg-path, port: root_cfg } }
- { src: { node: resolve-reg-path }, dst: { node: parse-reg,        port: reg_config_path } }
- { src: { node: parse-reg },        dst: { node: parse-suite,      port: test_config } }
- { src: { node: parse-suite },      dst: { node: select,           port: suite_cfg } }
```

**Level filtering:**

```yaml
- { src: { cli: reg_level,   type: int, default: 0 }, dst: { node: filter, port: reg_level } }
- { src: { cli: start_level, type: int, default: 0 }, dst: { node: filter, port: start_level } }
```

**Seed mode:**

```yaml
- { src: { node: const-seed-mode }, dst: { node: seed, port: seed_mode } }
```

**`extract-dir` — pre-fan-out:**

```yaml
- { src: { node: gate-pre, port: test }, dst: { node: extract-dir, port: test } }
- { src: { cli: logs_dir, type: str, default: "logs" }, dst: { node: extract-dir, port: logs_dir } }
- { src: { node: extract-dir, port: work_dir }, dst: { node: cc-build, port: work_dir } }
- { src: { node: extract-dir, port: work_dir }, dst: { node: cc-run,   port: work_dir } }
- { src: { node: extract-dir, port: base_dir }, dst: { node: fl-tb,    port: base_dir } }
- { src: { node: extract-dir, port: base_dir }, dst: { node: fl-norm,  port: base_dir } }
- { src: { node: extract-dir, port: work_dir }, dst: { node: fl-path,  port: work_dir } }
- { src: { node: extract-dir, port: logs_dir }, dst: { node: cc-build, port: logs_dir } }
```

**`extract-dir-post` — post-fan-out:**

```yaml
- { src: { node: runs, port: test },   dst: { node: extract-dir-post, port: test } }
- { src: { cli: logs_dir, type: str, default: "logs" }, dst: { node: extract-dir-post, port: logs_dir } }
- { src: { node: extract-dir-post, port: work_dir }, dst: { node: sim-run,     port: work_dir } }
- { src: { node: extract-dir-post, port: work_dir }, dst: { node: randseed,    port: work_dir } }
- { src: { node: extract-dir-post, port: work_dir }, dst: { node: link-latest, port: work_dir } }
- { src: { node: extract-dir-post, port: logs_dir }, dst: { node: sim-build, port: logs_dir } }
- { src: { node: extract-dir-post, port: logs_dir }, dst: { node: seed,      port: logs_dir } }
```

### Everything else

All of the following carry over unchanged from `test.yaml`:

- setup chain: `discover-root`, `prepend-path`, `parse-root`, `select-platform`, `resolve-builder`, `git-status` (`work-dir` and `ensure-logs` are removed — absorbed by `extract-dir`)
- selection / expansion: `select`, `filter`, `model-ref`, `load-model`, `sweep`
- per-test prep: `preproc`, `gate-pre`
- filelist pipeline: `unroll`, `fl-model-ref`, `fl-model-root`, `fl-model`, `fl-tb`, `fl-merge`, `fl-norm`, `fl-dedup`, `fl-path`, `filelist` (contract configs change for `fl-tb`, `fl-norm`, `fl-path` per above)
- compile: `cc-build`, `cc-run`, `cc-int`, `gate-comp` (contract configs change for `cc-build`, `cc-run` — `work_dir` and `logs_dir` move from persistent to keyed)
- sim: `runs`, `seed`, `sim-build`, `sim-run`, `randseed`, `link-latest`, `sim-int`, `gate-sim` (contract configs change for `sim-run`, `randseed`, `link-latest` — `work_dir` keyed; `sim-build`, `seed` — `logs_dir` keyed)
- post: `route-post`, `parse-log`, `parse-uvm-log`
- `logging:` block (both summary processors)
- all `env_ready`, `builder_cfg`, `root_cfg` fan-out edges

## CLI surface

Matching rtl_buddy's `do_rtl_regression` signature.

| arg | flag | type | default | destination |
|---|---|---|---|---|
| `reg_config` | `-c/--reg-config` | str | `""` | `resolve-reg-path.reg_config` |
| `reg_level` | `-l/--reg-level` | int | 0 | `filter.reg_level` |
| `start_level` | `-s/--start-level` | int | 0 | `filter.start_level` |
| `logs_dir` | `--logs-dir` | str | `logs` | `extract-dir.logs_dir`, `extract-dir-post.logs_dir` |
| `builder` | `--builder` | str | `""` | `resolve-builder.builder` |
| `builder_mode` | `-M/--builder-mode` | str | **`reg`** | `cc-build.builder_mode`, `sim-build.builder_mode` |
| `early_stop` | `--early-stop` | str | `post` | `gate-pre`, `gate-comp`, `gate-sim` |

**Removed from test:** `test_name`, `list`, `rnd_new`, `rnd_last`, `test_config`.

**Changed from test:** `builder_mode` default changes from `"debug"` to `"reg"`.

## Structural notes

### Early-stop / skip row count

`gate-pre`/`gate-comp` sit before the `runs` fan-out, so a pre/comp early-stop or a level skip emits one summary row per test, not R duplicate rows.

### No process-wide `chdir`

No node calls `os.chdir`. Each compile/sim subprocess runs with `cwd=work_dir` via `RunProcessMod`'s `cwd=work_dir` parameter. Concurrent suites' tests can run with different `work_dir`s without racing a shared process CWD.

### Summary aggregation

The `ConsoleSummaryProcessor` and `FileSummaryProcessor` logging plugins match diagnostic log events by name, accumulate one row per test, and render the table at end of run. With the suite name stamped into the correlation key at `parse-suite-config` (`<suite>/<test>#<sweep>#<run>`, via `prefix_suite: true`), every row carries its suite. The table groups naturally on that prefix. No plugin change needed.

### Pre/post fan-out key mismatch

`expand-runs` re-keys everything from `test_key` to `test_key#run_id`. A keyed `work_dir` emitted with `test_key` won't match `test_key#run_id` in `keyed_join` on post-fan-out nodes. Since `TestConfig.suite_dir` rides the object through the fan-out, the solution is two `ExtractSuiteDirMod` instances — one before and one after `expand-runs`:

- **`extract-dir`** (after `gate-pre`): emits with key `test_key`, serves pre-fan-out consumers.
- **`extract-dir-post`** (after `runs`): receives the re-keyed `test` from `expand-runs`, emits with key `test_key#run_id`, serves post-fan-out consumers.

## Acceptance criteria

- All new module unit tests pass.
- `graphs/regression.yaml` loads without structural validation errors at startup.
- The `regression` subcommand appears in `rtl-comrade --help`.
- A basic `regression` run against the fixture project:
  - creates per-suite `logs/` directories under each suite's directory
  - runs all suites' tests
  - produces a summary table with suite-prefixed keys
  - returns exit code 0 when all tests pass
- Level filtering correctly includes/excludes tests based on `reg_level` and `start_level`.
- `builder_mode` defaults to `"reg"`, not `"debug"`.
- The `parse-suite-config` module remains contract-agnostic and backwards-compatible: existing test and randtest graphs (no `config` block, `prefix_suite` defaults to `False`) are unaffected.

## Settled decisions

1. **Per-suite `work_dir` and `logs_dir` routing:** `ExtractSuiteDirMod` extracts `test.suite_dir` per test and emits keyed `work_dir`, `base_dir`, and `logs_dir` values. Two instances: `extract-dir` (pre-fan-out, key = `test_key`) and `extract-dir-post` (post-fan-out, key = `test_key#run_id`). Downstream nodes move `work_dir`/`base_dir`/`logs_dir` from `persistent_inputs` to regular keyed inputs. No downstream module changes — only graph-YAML contract configs.

2. **Suite-key prefixing:** config flag (`prefix_suite: true`) on `ParseSuiteConfigMod`. No separate `stamp-suite-key` module. The key becomes `<suite_dir.name>/<test_name>` at construction time. Same leaf-name collision behaviour as rtl_buddy.

3. **`ensure-logs` removal:** `ensure-logs` is dropped from the regression graph. Its role (create the logs directory, emit resolved `logs_dir` Path) is absorbed by `ExtractSuiteDirMod`, which creates `suite_dir / logs_dir` and emits the resolved path as a keyed value. Per-test `mkdir -p` is idempotent.
