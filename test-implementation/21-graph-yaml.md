# Spec 21: Graph YAML and Integration Test

## What this covers

Write the complete graph YAML file `graph-rtl-buddy-test.yaml` and an integration test that runs a minimal end-to-end scenario. This spec assumes all modules (specs 02–20) and the contract (spec 01) are implemented.

## Before you start

Read:
- `graph2.yaml` — canonical example of graph YAML syntax
- `CLAUDE.md` — how to run the graph (`uv run rtl-comrade graph2.yaml`)
- `tests/integration/test_graph_run.py` — integration test patterns
- `tests/conftest.py` — `make_graph_config`, `tmp_plugin_dir` fixtures

## File: `graph-rtl-buddy-test.yaml`

Copy the YAML from `rtl-comrade-test-graph-module-plan.md` §10 "Graph YAML" section. It is the complete and correct wiring.

After copying, verify:
1. All `module:` values match names registered in `modules/rtl_buddy_compat/config.yaml`.
2. All `contract:` values match names in `contracts/config.yaml` (including `fan_in`).
3. The three `run-depth-gate-*` nodes use `module: rtl_buddy_compat.run_depth_gate` with `config.gate_depth` and `config.stop_desc`.
4. All gate node edges use `port: payload` as the destination port name (not the old type-specific names).
5. `suite-accumulate` has nine incoming edges, one per result branch.
6. There is no `exit-code-resolve` node. Exit code is determined by the harness's deferred-failure model (`log.error` calls in FAIL/NA-emitting modules).

## Integration test

Write `tests/integration/test_rtl_buddy_compat.py`.

Tests do not require a real RTL simulator. Use stub executables or minimal filesystem setups.

### Test 1: `--list` path

Set up a minimal `tests.yaml` with two named tests. Configure `CliArgsSource` with `list_tests=True`. Run the graph. Verify:
- `ListTestsRender` produces output containing both test names.
- No compile or sim stage runs.
- Exit code is `0`.

### Test 2: `run_depth=pre` early stop

Configure `run_depth="pre"`. Use a compile command that exits nonzero if called. Run the graph. Verify:
- `LegacyPreproc` runs (or is skipped — depends on test having no preproc script).
- `FilelistGenerate` does NOT run.
- `SuiteResultAccumulate` receives one `early_stop_pre_result` row with `result="NA"`.
- Exit code is `1`.

### Test 3: Compile failure

Configure `run_depth="post"` with `argv=["false"]` as the compile command. Verify:
- `SuiteResultAccumulate` receives one `compile_fail_result` row with `result="FAIL"`.
- `SimExecute` does NOT run.
- Exit code is `1`.

### Test 4: Happy path (conditional)

If `/usr/bin/true` is available as a fake simulator and a minimal `run.f` can be constructed, run a full pass with a log file containing `"PASS"`. Verify exit code is `0`.

## Constraints

- Integration tests use `tmp_path` for all filesystem artefacts.
- Do not use `graph2.yaml` in integration tests; construct temporary graph files or `GraphConfig` objects directly.
- `fan_in` must be registered in `contracts/config.yaml` before the graph loads (spec 01).
