# Overview

## Goal

Reproduce the behaviour of `rtl_buddy test` as an `rtl-comrade` graph.

> **Source baseline.** This plan mirrors **rtl_buddy `v1.4.0`** (commit
> `a69d962f5c42f859f320984129cca0435b0cba36`), expected as a sibling checkout at
> `rtl_buddy/` in the repo root. Every `Source:` / `Compatibility source:` file:line
> citation across these docs and `specs/` is anchored to that version; if rtl_buddy is
> updated, re-verify every cited range.

`rtl_buddy test` (traced from `rtl_buddy/src/rtl_buddy/`) does, in one sequential
in-process pass:

1. load `root_config.yaml` (walk up the tree, pick a platform by `uname`, resolve a builder)
2. load the suite `tests.yaml` (and each test's `models.yaml` + testbenches)
3. select one test or all tests
4. (regression only) filter tests by regression level
5. expand each test through an optional `sweep` script into N variants
6. for each test: run an optional `preproc` script, write a filelist (`run.f`), compile
7. for each run-id: resolve a seed, simulate (with timeout), parse the log into a result
8. aggregate all results, print a summary, exit `0` iff every result is PASS/SKIP

The whole thing is sequential, mutation-heavy, and short-circuits on the first failure
of each test (compile fail → no sim; timeout → no post; `--early-stop` → stop at a phase).

## Design philosophy

1. **Phases are tags, not structure.** `pre`/`compile`/`sim`/`post` are labels on the
   modules that happen to do that kind of work, not structural boundaries. The real unit
   is the smallest piece of node-local work.

2. **Atomic modules; coordination in contracts.** Every module declares exactly the inputs
   it consumes as **granular named ports** the harness can see and validate, does its work,
   and emits named outputs. Modules contain **no scheduling** — no "should I run", no
   passthrough guards, no awareness of the graph. *All* coordination (when a node runs,
   which inputs are matched, how branches re-converge) lives in contracts, and **we author
   the contracts the design needs** — contracts are plugins, not framework internals.

3. **Branching is data routing via output ports; the summary is a logging concern.** A stage
   that produces a terminal outcome (skip, early-stop, compile-fail, timeout, parsed result)
   emits it on a dedicated output port that routes the item *off the main line*. Items that
   continue stay on the main line. Because terminal items leave, downstream stages never see
   them — which is why no module needs a guard. There is **no collector node**: each terminal
   port is left unwired and its module additionally **logs its outcome** — the otherwise-silent
   paths (`parse-log`/`parse-uvm-log`, `filter.skip`, `early-stop`) emit a `test_result` event,
   while the failure terminals add `result`/`desc` to their existing `log.error`. A per-graph
   **`SummaryProcessor` logging plugin** collects those events via a configured watch-list and
   renders the table in its `finalise()` hook. `git-status` logs its git stateline separately and
   it falls through to the console. The exit code is driven by per-emission `log.error`. This is
   the TODO #15 redesign — see [05](05-branching-and-results.md).

4. **`compile` and `sim` are one reusable module.** `run-process` — `run(self, command,
   timeout=None) -> {rc, timed_out, stdout_path, stderr_path}` — is the single subprocess
   primitive, wired twice. It **redirects** stdout/stderr to caller-supplied files (paths in
   `command`), so partial output survives a timeout and memory stays bounded.

5. **Reimplement rtl_buddy, preserve only the config surface.** Modules reimplement
   `rtl_buddy`'s behaviour natively rather than wrapping its classes; only the config-file
   schema (`root_config.yaml`, `tests.yaml`, `models.yaml` field names/structure) is kept
   identical, so existing config files run drop-in. This is what frees the monolithic
   `RootConfig`/`SuiteConfig` loaders to be split into atomic nodes (`discover-config-file`,
   `parse-root-config`, `select-platform`, `resolve-builder`, `parse-suite-config`,
   `load-model`). See [07](07-ambiguities-and-assumptions.md) item 1.

## Correlation: a minimal context record + joins only where streams diverge

With no god-object carrying everything, a stage needs its inputs *matched up* under
concurrency. The chosen strategy (see [02](02-payload-conventions.md)):

- A stable **`ctx` record** `{key, test, run_id}` rides the main line from `select` through
  `write-randseed`. It is assembled at fan-out points and never modified: no stage adds
  fields. `simv` is set by `build-compile-cmd` and carried in `ctx` to `sim-build`.
  `seed`/`log`/`err`/`randseed_path` travel as `sim_cmd`, a keyed
  payload from `sim-build` to `write-randseed`. `write-randseed` assembles `test_run` once
  (from `ctx`, `proc`, and `sim_cmd`); the post-sim chain receives `test_run` in place of
  `ctx`. No `result` field ever enters either record.
- A stable **correlation key** is stamped at each fan-out (`select`→`name`,
  `sweep`→`name#i`, `runs`→`name#i#run`).
- **Joins happen only where a fast path meets a slow path**: the direct `ctx` edge meets
  the subprocess `proc` result at `interpret-compile` and `write-randseed` (the first sim-side
  node needing both). Those two nodes use `keyed_join` on the key. Everywhere else, a stage's
  inputs come from a single upstream in lockstep, so a plain `default` contract suffices.

This is the explicit difference from the rejected single-envelope design: `ctx` is a
*minimal, bounded* record of genuinely-pervasive values (not an accumulator), modules read
only the ports they declare, and no module contains scheduling.

## End-to-end dataflow at a glance

The whole graph in one Mermaid flowchart, rebuilt from the authoritative edge list in
[`06-graph-yaml.md`](06-graph-yaml.md). Edges are **colour- and style-coded by type** so a
reviewer can trace any one type without another crossing it:

Each edge is labelled `name:type` (lockstep multi-payload edges as `a:type + b:type`); the
work-spine payloads (`ctx`, `test_run`, `command`, `proc`, `filelist`, `seed`, `sim_cmd`,
`result`) are plain dicts whose shapes are pinned in [02](02-payload-conventions.md), while
config/setup edges carry concrete classes (`RootConfig`, `RtlBuilderConfig`, `SuiteConfig`, …)
or scalars (`Path`, `bool`, `str`). Colours:

- **blue, bold** — main-line continue ports (the work spine), each labelled with its payload;
- **grey, dashed** — the 13 **unwired** terminal ports routing an item *off the main line*
  (and `git-status`, which falls through to the console);
- **orange** — setup chain + persistent config broadcasts (`root_cfg`, `builder_cfg`, …);
- **purple** — env-setup sequencing (`env_ready`) plus artefact-dir provenance: `check-cwd`
  emits `work_dir`, `ensure-logs` roots `logs/` on it and emits the resolved directory `Path`
  to the path composers — ordering the `$PATH` prepend and `logs/` `mkdir` upstream of every
  subprocess;
- **green** — CLI subcommand options (rounded nodes).

`select`/`sweep`/`runs` are the only fan-out generators; `cc-int`/`randseed` the only joins
(`keyed_join`). The same node names appear in the [04 node table](04-pipeline-and-contracts.md#node-table).

```mermaid
flowchart TD
  route_list["route-list"] -->|"run:SuiteConfig"| select["select<br/>(fan-out)"]
  select -->|"ctx:dict"| filter["filter"]
  filter -->|"keep:dict"| load_model["load-model"]
  load_model -->|"ctx:dict"| sweep["sweep<br/>(fan-out)"]
  sweep -->|"ctx:dict"| preproc["preproc"]
  preproc -->|"payload:dict"| gate_pre["gate-pre"]
  gate_pre -->|"go:dict"| filelist["filelist"]
  filelist -->|"ctx:dict + filelist:dict"| cc_build["cc-build"]
  cc_build -->|"command:dict"| cc_run["cc-run<br/>(run-process)"]
  cc_build -->|"ctx:dict"| cc_int["cc-int<br/>(keyed_join)"]
  cc_run -->|"proc:dict"| cc_int
  cc_int -->|"ok:dict"| gate_comp["gate-comp"]
  gate_comp -->|"go:dict"| runs["runs<br/>(fan-out)"]
  runs -->|"ctx:dict"| seed["seed"]
  seed -->|"ctx:dict + seed:dict"| sim_build["sim-build"]
  sim_build -->|"command:dict + timeout:Optional[float]"| sim_run["sim-run<br/>(run-process)"]
  sim_build -->|"ctx:dict + sim_cmd:dict"| randseed["randseed<br/>(keyed_join)"]
  sim_run -->|"proc:dict"| randseed
  randseed -->|"test_run:dict"| link_latest["link-latest"]
  link_latest -->|"test_run:dict"| sim_int["sim-int"]
  sim_int -->|"ok:dict"| gate_sim["gate-sim"]
  gate_sim -->|"go:dict"| route_post["route-post"]
  route_post -->|"plain:dict"| parse_log["parse-log"]
  route_post -->|"uvm:dict"| parse_uvm["parse-uvm-log"]
  route_list -->|"list:SuiteConfig"| list_names["list-names<br/>(prints names; exit 0)"]

  filter -."skip:SkipResults".-> TERM["unwired terminal ports<br/>each edge carries result:dict = {key:str, result:TestResults}<br/>pass-like: log.info(test_result); fail/timeout: log.error(domain event w/ result,desc) → exit 1<br/>SummaryProcessor watch-list collects them; renders the table in finalise()"]
  load_model -."fail:TestResults(FAIL)".-> TERM
  sweep -."fail:TestResults(FAIL)".-> TERM
  preproc -."fail:TestResults(FAIL)".-> TERM
  gate_pre -."stop:EarlyStopResults".-> TERM
  filelist -."fail:TestResults(FAIL)".-> TERM
  cc_int -."fail:CompileFailResults".-> TERM
  gate_comp -."stop:EarlyStopResults".-> TERM
  seed -."fail:TestResults(FAIL)".-> TERM
  sim_int -."timeout:SimTimeoutResults".-> TERM
  gate_sim -."stop:EarlyStopResults".-> TERM
  parse_log -."result:TestResults".-> TERM
  parse_uvm -."result:TestResults".-> TERM

  discover_root["discover-root"] -->|"path:Path"| parse_root["parse-root"]
  parse_root -->|"root_cfg:RootConfig"| select_platform["select-platform"]
  select_platform -->|"platform_cfg:PlatformConfigFile"| resolve_builder["resolve-builder"]
  check_cwd["check-cwd"] -->|"test_config_path:Path"| parse_suite["parse-suite"]
  parse_root -. "root_cfg:RootConfig" .-> sweep
  parse_root -. "root_cfg:RootConfig" .-> preproc
  resolve_builder -. "builder_cfg:RtlBuilderConfig" .-> filter
  resolve_builder -. "builder_cfg:RtlBuilderConfig" .-> cc_build
  resolve_builder -. "builder_cfg:RtlBuilderConfig" .-> seed
  resolve_builder -. "builder_cfg:RtlBuilderConfig" .-> sim_build
  seed_mode["seed-mode"] -. "seed_mode:SeedMode" .-> seed
  parse_suite -. "suite_cfg:SuiteConfig" .-> route_list

  prepend_path["prepend-path"] -->|"env_ready:bool"| ensure_logs["ensure-logs"]
  check_cwd -->|"work_dir:Path"| ensure_logs
  ensure_logs -->|"env_ready:bool"| cc_run
  ensure_logs -->|"env_ready:bool"| sim_run
  ensure_logs -->|"logs_dir:Path"| cc_build
  ensure_logs -->|"logs_dir:Path"| sim_build
  ensure_logs -->|"logs_dir:Path"| seed

  c_test_config(["test_config"]) -->|"test_config:str"| check_cwd
  c_logs_dir(["logs_dir (name)"]) -->|"logs_dir:str"| ensure_logs
  c_builder(["builder"]) -->|"builder:str"| resolve_builder
  c_test_name(["test_name"]) -->|"test_name:str"| select
  c_list(["list"]) -->|"list:bool"| route_list
  c_rnd_new(["rnd_new"]) -->|"rnd_new:bool"| seed_mode
  c_rnd_last(["rnd_last"]) -->|"rnd_last:bool"| seed_mode
  c_builder_mode(["builder_mode"]) -->|"builder_mode:str"| cc_build
  c_builder_mode -->|"builder_mode:str"| sim_build
  c_early_stop(["early_stop"]) -->|"early_stop:str"| gate_pre
  c_early_stop -->|"early_stop:str"| gate_comp
  c_early_stop -->|"early_stop:str"| gate_sim

  git_status["git-status"] -. "log git_state (→ console)" .-> GS(["console"])

  classDef fanout fill:#e6f2ff,stroke:#1f6feb;
  classDef join fill:#fff3cd,stroke:#bf8700;
  classDef term fill:#f5f5f5,stroke:#888888,stroke-dasharray:4 3;
  classDef cli fill:#eef7ee,stroke:#2da44e;
  class select,sweep,runs fanout;
  class cc_int,randseed join;
  class TERM term;
  class c_test_config,c_logs_dir,c_builder,c_test_name,c_list,c_rnd_new,c_rnd_last,c_builder_mode,c_early_stop cli;

  %% main-line continue ports (blue)
  linkStyle 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24 stroke:#1f6feb,stroke-width:2px
  %% terminal routing (grey, dashed via -.->)
  linkStyle 25,26,27,28,29,30,31,32,33,34,35,36,37 stroke:#6e7781,stroke-width:1px
  %% setup chain + persistent config (orange)
  linkStyle 38,39,40,41,42,43,44,45,46,47,48,49 stroke:#bf8700,stroke-width:1.5px
  %% env sequencing + artefact-dir provenance (purple)
  linkStyle 50,51,52,53,54,55,56 stroke:#8250df,stroke-width:1.5px
  %% CLI options (green)
  linkStyle 57,58,59,60,61,62,63,64,65,66,67,68 stroke:#1a7f37,stroke-width:1.5px
  %% git-status (grey)
  linkStyle 69 stroke:#6e7781,stroke-width:1px
```

There is **no fan-in node** — the 13 terminal ports are unwired and the summary is a logging
concern (TODO #15). Apart from the three fan-out generators and the two joins, every node is
single-input / single-output on a plain `default` contract.

## Why this maps cleanly

| rtl_buddy concept | rtl-comrade realisation |
|---|---|
| `RtlBuddy` + `TestRunner` orchestration & loops | graph topology + contracts |
| nested `for test / for run_id` loops | fan-out generator modules (`select`, `sweep`, `runs`) |
| early `return CompileFailResults` etc. | named output port routes the item off the main line |
| `--early-stop` phase truncation | `early-stop-gate` nodes emitting on `stop` |
| compile vs sim | one reusable `run-process` module + two command builders |
| matching async results to their test | `keyed_join` on the correlation key at `cc-int`/`randseed` |
| collecting all outcomes | each terminal logs its outcome (`test_result` from the silent paths; `compile_failed`/`sim_timeout`/`*_failed` from the failure terminals) → `SummaryProcessor` watch-list collects and renders the table |
| OR-accumulated exit code | per-emission `log.error` at each failure site (harness maps ERROR → exit 1) |
| git state recorded | `git-status` setup node `log.info("git_state", …)` → falls through to the console (not in the summary table) |
| `RootConfig`/`SuiteConfig` monolithic loaders | reimplemented as atomic setup nodes; config schema preserved |
