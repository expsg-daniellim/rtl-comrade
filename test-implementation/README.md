# rtl-buddy compat graph — implementation specs

## Original flow

```
do_cmd_test()
  └─ _do_test_suite()
       └─ for each TestConfig in SuiteConfig.get_tests():
            └─ _run_test_cfg_for_run_ids()
                 └─ TestRunner.run()
                      ├─ VlogSim.pre()        — exec preproc script (mutates TestConfig)
                      ├─ VlogSim.compile()    — write run.f, invoke builder executable
                      ├─ VlogSim.execute()    — run simv, seed management, log to file
                      └─ VlogSim.post()       — parse log → TestResults (PASS/FAIL/NA)
```

Key data flowing through the pipeline:

| Object | Created by | Consumed by |
|---|---|---|
| `RootConfig` | `RootConfig()` | compile, execute, post |
| `TestConfig` | `SuiteConfig.get_tests()` | all stages (mutated by preproc) |
| `compile_returncode: int` | `VlogSim.compile()` | `VlogSim.execute()` gate |
| `execute_returncode: int` | `VlogSim.execute()` | `VlogSim.post()` gate |
| `run_id`, `seed_mode` | `do_cmd_test()` | `VlogSim.execute()` |
| `TestResults` dict | `VlogSim.post()` | result table print |



Implement in order. Each spec assumes all earlier ones are complete.

`rtl-comrade-test-graph-module-plan.md` is the master spec from which these individual specs are derived.

| # | File | Covers | Shared file |
|---|------|--------|-------------|
| 00 | `00-artefacts.md` | Package setup + all shared dataclasses | `artefacts.py` (new) |
| 01 | `01-collect-until-end-contract.md` | New harness contract | `contracts/collect_until_end.py` (new) |
| 02 | `02-cli-args-and-seed-mode.md` | CliArgsSource, SeedModeSelect | `bootstrap.py` (new) |
| 03 | `03-root-bootstrap.md` | RootBootstrap | `bootstrap.py` (extend) |
| 04 | `04-suite-config-load.md` | SuiteConfigLoad | `suite.py` (new) |
| 05 | `05-suite-routing-and-select.md` | ListTestsBranch, ListTestsRender, TestSelect | `suite.py` (extend) |
| 06 | `06-regression-level-skip-filter.md` | RegressionLevelSkipFilter | `planning.py` (new) |
| 07 | `07-legacy-sweep-expand.md` | LegacySweepExpand | `planning.py` (extend) |
| 08 | `08-run-id-plan.md` | RunIdPlan | `planning.py` (extend) |
| 09 | `09-legacy-preproc.md` | LegacyPreproc | `preproc.py` (new) |
| 10 | `10-run-depth-gate.md` | RunDepthGate (generic; 3 graph instances) | `preproc.py` (extend) |
| 11 | `11-filelist-and-compile-command.md` | FilelistGenerate, CompileCommandBuild | `compile.py` (new) |
| 12 | `12-compile-execute.md` | CompileExecute | `compile.py` (extend) |
| 13 | `13-run-fanout.md` | RunFanout | `sim.py` (new) |
| 14 | `14-seed-resolve.md` | SeedResolve | `sim.py` (extend) |
| 15 | `15-sim-command-build.md` | SimCommandBuild | `sim.py` (extend) |
| 16 | `16-sim-execute.md` | SimExecute, SimArtifactLink | `sim.py` (extend) |
| 17 | `17-default-log-parser.md` | PostParserSelect, DefaultLogParser | `post.py` (new) |
| 18 | `18-uvm-log-parser.md` | UvmLogParser | `post.py` (extend) |
| 19 | `19-suite-result-accumulate.md` | SuiteResultAccumulate | `results.py` (new) |
| 20 | `20-summary-and-exit-code.md` | SummaryRender | `results.py` (extend) |
| 21 | `21-graph-yaml.md` | Graph YAML + integration tests | `graph-rtl-buddy-test.yaml` (new) |
| 22 | `22-git-status.md` | GitStatusReport (optional) | `git_status.py` (new) |

## Notes

- Specs that share a Python file are always sequential: the first spec creates the file, later specs extend it. The spec will say "extend the file from spec N".
- Specs 02–20 are independent of each other once spec 00 is done. The only shared dependency is `artefacts.py`.
- Spec 16 (`SimArtifactLink`) is grouped with `SimExecute` because it is five lines with no independent test scenarios.
- Spec 17 (`PostParserSelect`) is grouped with `DefaultLogParser` because it is a two-line router whose only purpose is to gate entry into the two parsers.
- Spec 22 can be skipped if git status output is not a priority.

## Artefacts vs observability

Graph payloads fall into two categories:

- **Artefacts** — values with a concrete downstream purpose within the graph. A downstream node consumes them as inputs. Examples: `CompileResult`, `ResolvedRunPlan`, `SimResult`.
- **Observability** — values produced solely for the benefit of the user or operator. No downstream node consumes them for computation. Examples: `TestResultRow`, rendered summaries, git status output.

Observability data should flow through the logging system (via a custom logging provider and a structured log type), not through graph edges. Routing observability through the graph conflates scheduling concerns with reporting concerns and forces artificial fan-in nodes whose only job is to collect and render data that already exists at the log level.

## TODO: rework result-emitting nodes once custom logging providers are implemented

Currently specs 12, 14, 16, 17, 18, 19, and 20 route `TestResultRow` through graph edges as payloads, accumulated by `SuiteResultAccumulate` and rendered by `SummaryRender`. This is a pragmatic workaround for the absence of custom logging providers.

Once custom logging providers land, the following should be reworked:

- `DefaultLogParser`, `UvmLogParser` — emit `TestResultRow` as a structured log event instead of a graph payload; remove their output ports.
- `CompileExecute.failure`, `SeedResolve.failure`, `SimExecute.timeout` — replace the `TestResultRow` output port with a `log.result(...)` call; branch terminates via harness `EndSentinel` propagation after logging.
- `SuiteResultAccumulate`, `SummaryRender`, and all of `results.py` — replace with a structured log drain and renderer; remove from the graph entirely.
- The `fan_in` contract (spec 01) — likely no longer needed once result rows leave the graph.
