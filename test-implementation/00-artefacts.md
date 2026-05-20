# Spec 00: Package Setup + Shared Artefacts

## What this covers

Create the `modules/rtl_buddy_compat/` package and define all shared dataclasses used across the rtl-buddy compatibility graph. Every subsequent spec imports from `artefacts.py`; get this right first.

## Before you start

Read:
- `CLAUDE.md` — project conventions
- `docs/module-implementation.md` — module interface rules
- `modules/config.yaml` — how the existing modules plugin manifest works

## Files to create

```
modules/rtl_buddy_compat/
    __init__.py          (empty)
    artefacts.py         (all dataclasses — this spec)
    config.yaml          (plugin manifest — this spec)
```

The per-module Python files (`bootstrap.py`, `suite.py`, etc.) are created by later specs; do not create them here.

## artefacts.py

All types are plain Python dataclasses. Use `from dataclasses import dataclass, field`. No serde decorators needed yet — add them later if the harness requires it.

### `TestCliArgs`

```python
@dataclass
class TestCliArgs:
    test_config: str = "tests.yaml"
    test_name: str | None = None
    list_tests: bool = False
    rnd_new: bool = False
    rnd_last: bool = False
    rtl_builder_mode: str | None = None
    builder_override: str | None = None
    run_depth: str = "post"
    debug: bool = False
    color: bool = True
```

### `RootContext`

Carries everything downstream nodes need from the root config. All fields are plain Python primitives (no live config objects).

```python
@dataclass
class RootContext:
    builder_name: str
    rtl_builder_mode: str
    run_depth: str
    project_root: str
    root_config_path: str
    # Raw dicts from root_config.yaml for downstream reconstruction
    rtl_builder_cfg: dict        # serialised RtlBuilderConfig
    platform_name: str
```

`rtl_builder_cfg` stores the raw YAML dict for the selected builder so `CompileCommandBuild` and `SimCommandBuild` can reconstruct the config object without carrying a live object across the graph boundary.

Compatibility source: `root.py:L46-L113`, `rtl_buddy.py:L171-L172`.

### `SuiteContext`

```python
@dataclass
class SuiteContext:
    path: str
    test_names: list[str]
    tests: list["TestConfigEnvelope"]
```

### `TestConfigEnvelope`

```python
@dataclass
class TestConfigEnvelope:
    name: str
    desc: str
    model_path: str
    testbench_name: str
    testbench_filelist: str | None
    reglvl: int | dict | None
    plusargs: list[str]
    plusdefines: dict[str, str | None]
    uvm: dict | None
    preproc_path: str | None
    postproc_path: str | None
    sweep_path: str | None
    timeout: int | None
    suite_path: str
    declaration_index: int
```

`reglvl` may be an `int`, a builder-keyed `dict`, or `None`. `plusdefines` maps key to value-or-None (no-value defines use `None`). `declaration_index` is the 0-based position in the suite file.

Compatibility source: `test.py:L30-L264`.

### `TestInstanceKey`

```python
@dataclass(frozen=True)
class TestInstanceKey:
    suite_path: str
    original_test_name: str
    expanded_test_name: str
    expanded_index: int
    run_id: int | None
```

Frozen so it can be used as a dict key. `run_id=None` for plain `test`.

### `SeedModePlan`

```python
from typing import Literal

@dataclass
class SeedModePlan:
    mode: Literal["default", "new", "replay"]
    replay_run_id: int | None = None
```

### `RunPlan`

One item per run id per expanded test.

```python
@dataclass
class RunPlan:
    key: TestInstanceKey
    test: TestConfigEnvelope
    seed_mode: SeedModePlan
```

### `PreprocessedRunPlan`

After the preproc hook has run (which may mutate `test`).

```python
@dataclass
class PreprocessedRunPlan:
    key: TestInstanceKey
    test: TestConfigEnvelope     # may differ from RunPlan.test if preproc mutated it
    seed_mode: SeedModePlan

    @property
    def instance_key(self) -> TestInstanceKey:
        return self.key
```

The `instance_key` property is required by `RunDepthGate`.

### `FilelistArtefact`

```python
@dataclass
class FilelistArtefact:
    output_path: str
    lines: list[str]
    run_plan: PreprocessedRunPlan    # embedded so CompileCommandBuild needs only 2 inputs
```

### `CompileCommand`

```python
@dataclass
class CompileCommand:
    argv: list[str]
    cwd: str
    test_name: str
    build_dir: str
    filelist_path: str
    run_plan: PreprocessedRunPlan   # forwarded for RunDepthGateComp and RunFanout
```

### `CompileResult`

```python
@dataclass
class CompileResult:
    command: CompileCommand
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float

    @property
    def instance_key(self) -> TestInstanceKey:
        return self.command.run_plan.key
```

The `instance_key` property is required by `RunDepthGate`.

### `PerRunExecutionPlan`

```python
@dataclass
class PerRunExecutionPlan:
    key: TestInstanceKey
    test: TestConfigEnvelope
    seed_mode: SeedModePlan
    compile_result: CompileResult
```

### `ResolvedRunPlan`

```python
@dataclass
class ResolvedRunPlan:
    key: TestInstanceKey
    test: TestConfigEnvelope
    seed: int
    seed_mode: SeedModePlan
    compile_result: CompileResult
```

### `SimCommand`

```python
@dataclass
class SimCommand:
    argv: list[str]
    cwd: str
    key: TestInstanceKey
    log_path_prefix: str
    timeout_seconds: int
    seed: int
    test: TestConfigEnvelope
```

### `SimResult`

```python
@dataclass
class SimResult:
    command: SimCommand
    returncode: int
    duration_seconds: float
```

### `LinkedSimArtifacts`

```python
@dataclass
class LinkedSimArtifacts:
    sim_result: SimResult
    log_path: str
    err_path: str
    randseed_path: str

    @property
    def instance_key(self) -> TestInstanceKey:
        return self.sim_result.command.key
```

The `instance_key` property is required by `RunDepthGate`.

### `TestResultRow`

```python
@dataclass
class TestResultRow:
    key: TestInstanceKey
    result: Literal["PASS", "FAIL", "NA", "SKIP"]
    desc: str
    evidence: dict[str, str] = field(default_factory=dict)
```

### `SuiteResultSummary`

```python
@dataclass
class SuiteResultSummary:
    rows: list[TestResultRow]
```

### `RenderedOutput`

```python
@dataclass
class RenderedOutput:
    text: str
```

### `GitStatusArtefact`

```python
@dataclass
class GitStatusArtefact:
    branch: str
    commit: str
    text: str
```

## config.yaml

Create `modules/rtl_buddy_compat/config.yaml`. The module files (bootstrap, suite, etc.) will be registered here by later specs as they are created. For now just establish the manifest skeleton:

```yaml
files: []
```

Later specs will append entries like:
```yaml
- file: bootstrap.py
  plugins:
  - name: cli_args_source
    class_name: CliArgsSource
  - name: root_bootstrap
    class_name: RootBootstrap
  - name: seed_mode_select
    class_name: SeedModeSelect
```

## Tests

Write `modules/rtl_buddy_compat/tests/__init__.py` (empty) and `modules/rtl_buddy_compat/tests/test_artefacts.py`.

Cover:
- `TestInstanceKey` is hashable and usable as a dict key (it's frozen)
- `PreprocessedRunPlan.instance_key` returns the `key` field
- `CompileResult.instance_key` returns `command.run_plan.key`
- `LinkedSimArtifacts.instance_key` returns `sim_result.command.key`

These are the three `.instance_key` accessors that `RunDepthGate` depends on.

## Constraints

- Do not implement any module logic here. This spec is purely dataclass definitions.
- Do not import from rtl_buddy source. All fields are plain Python types.
- All three payloads passed to `RunDepthGate` (`PreprocessedRunPlan`, `CompileResult`, `LinkedSimArtifacts`) must expose `.instance_key: TestInstanceKey`.
