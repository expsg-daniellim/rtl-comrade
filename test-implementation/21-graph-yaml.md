# Spec 21: Graph YAML and Integration Test

## What this covers

Write the complete graph YAML file `graph-rtl-buddy-test.yaml` and an integration test that runs a minimal end-to-end scenario. This spec assumes all modules (specs 02–20) and the contract (spec 01) are implemented.

## Before you start

Read:
- `graph2.yaml` — canonical example of graph YAML syntax
- `CLAUDE.md` — how to run the graph (`uv run rtl-comrade graph2.yaml`)
- `tests/integration/test_graph_run.py` — integration test patterns
- `tests/conftest.py` — `make_graph_config`, `tmp_plugin_dir` fixtures

## File: `rtl_comrade_config.yaml`

Create `rtl_comrade_config.yaml` at the repo root (or wherever the rtl-buddy-compat project root is). The harness searches upward from `cwd` to find this file:

```yaml
commands:
  test:
    path: graphs/graph-rtl-buddy-test.yaml
    help: "Run RTL simulation tests."
```

## File: `graph-rtl-buddy-test.yaml`

Copy the YAML from `rtl-comrade-test-graph-module-plan.md` §10 "Graph YAML" section. It is the complete and correct wiring.

CLI arguments enter the graph via `cli:` edge sources. There is no `CliArgsMerge` node. Each consumer node receives only the CLI values it needs, wired directly:

```yaml
# seed-mode-select: rnd_new, rnd_last
- src:
    cli: rnd_new
    option: true
    type: bool
    default: false
    help: "Use a new random seed."
  dst:
    node: seed-mode-select
    port: rnd_new
- src:
    cli: rnd_last
    option: true
    type: bool
    default: false
    help: "Replay the last random seed."
  dst:
    node: seed-mode-select
    port: rnd_last

# root-bootstrap: rtl_builder_mode, builder_override, run_depth
- src:
    cli: rtl_builder_mode
    option: true
    type: str
    default: null
    help: "Override the RTL builder mode."
  dst:
    node: root-bootstrap
    port: rtl_builder_mode
- src:
    cli: builder_override
    option: true
    type: str
    default: null
    help: "Override the builder name."
  dst:
    node: root-bootstrap
    port: builder_override
- src:
    cli: run_depth
    option: true
    type: str
    default: "post"
    help: "Execution depth gate (pre/comp/post)."
  dst:
    node: root-bootstrap
    port: run_depth

# suite-config-load: test_config
- src:
    cli: test_config
    option: true
    type: str
    default: "tests.yaml"
    help: "Path to tests YAML file."
  dst:
    node: suite-config-load
    port: test_config

# list-tests-branch: list_tests
- src:
    cli: list_tests
    option: true
    type: bool
    default: false
    help: "List available tests and exit."
  dst:
    node: list-tests-branch
    port: list_tests

# test-select: test_name
- src:
    cli: test_name
    option: true
    type: str
    default: null
    help: "Name of a single test to run."
  dst:
    node: test-select
    port: test_name
```

After copying and adding CLI edges, verify:
1. All `module:` values match names registered in `modules/rtl_buddy_compat/config.yaml`.
2. All `contract:` values match names in `contracts/config.yaml` (including `fan_in`).
3. The three `run-depth-gate-*` nodes use `module: rtl_buddy_compat.run_depth_gate` with `config.gate_depth` and `config.stop_desc`.
4. All gate node edges use `port: payload` as the destination port name (not the old type-specific names).
5. `suite-accumulate` has nine incoming edges, one per result branch.
6. There is no `exit-code-resolve` node. Exit code is determined by the harness's deferred-failure model (`log.error` calls in FAIL/NA-emitting modules).
7. There is no `cli-args-source` node and no `cli-args-merge` node. CLI arguments enter via CLI edges directly into the nodes that consume them.

## Integration test

Write `tests/integration/test_rtl_buddy_compat.py`.

Tests do not require a real RTL simulator. Use stub executables or minimal filesystem setups.

### Test 1: `--list` path

Set up a minimal `tests.yaml` with two named tests. Invoke the graph with `list_tests=True` (via the CLI edge or by constructing the graph config with the appropriate CLI argument). Run the graph. Verify:
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
- Integration tests must write a `rtl_comrade_config.yaml` into `tmp_path` (or a parent that the harness will walk to) mapping `commands.test.path` to the temporary graph YAML. The harness searches upward from `cwd` for this file; either write it into `tmp_path` and `chdir` there, or write it above `tmp_path` and rely on the upward walk.
- Do not use `graph2.yaml` in integration tests; construct temporary graph files or `GraphConfig` objects directly.
- `fan_in` must be registered in `contracts/config.yaml` before the graph loads (spec 01).
