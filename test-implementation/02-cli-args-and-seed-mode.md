# Spec 02: CliArgsSource + SeedModeSelect

## What this covers

Implement `CliArgsSource` and `SeedModeSelect` in `modules/rtl_buddy_compat/bootstrap.py`. Both are trivial: `CliArgsSource` copies node config into a typed artefact; `SeedModeSelect` maps three boolean flags to a three-way enum. `RootBootstrap` — the complex bootstrap module — is spec 03.

## Prerequisites

Spec 00 (artefacts) must be complete. Import from `modules/rtl_buddy_compat/artefacts.py`.

## Before you start

Read `CLAUDE.md` and `docs/module-implementation.md` for module authoring conventions.

Compatibility source: `rtl_buddy/src/rtl_buddy/rtl_buddy.py:L156-L190`.

## File: `modules/rtl_buddy_compat/bootstrap.py`

Create this file. `RootBootstrap` will be added by spec 03.

### `CliArgsSource`

```
contract: unit
outputs: default → TestCliArgs
```

No input ports. Config injected via the node's `config:` block in the graph YAML.

```python
class CliArgsSource:
    class Config:
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

    def __init__(self, config: Config):
        self.config = config

    def run(self) -> TestCliArgs:
        return TestCliArgs(...)   # copy all config fields
```

### `SeedModeSelect`

```
contract: unit
inputs:  cli: TestCliArgs
outputs: default → SeedModePlan
```

Priority: `rnd_new` wins if both flags are set.

```
rnd_new=True  → mode="new"
rnd_last=True → mode="replay"
else          → mode="default"
```

Compatibility: `rtl_buddy.py:L184-L190`.

## Register in `modules/rtl_buddy_compat/config.yaml`

Replace `files: []` with:

```yaml
files:
- file: bootstrap.py
  plugins:
  - name: cli_args_source
    class_name: CliArgsSource
  - name: seed_mode_select
    class_name: SeedModeSelect
```

`RootBootstrap` will be added to this entry by spec 03.

## Tests

Write `modules/rtl_buddy_compat/tests/__init__.py` (empty) and `modules/rtl_buddy_compat/tests/test_bootstrap.py`.

**`SeedModeSelect`**:
- `rnd_new=True, rnd_last=False` → `mode="new"`
- `rnd_new=False, rnd_last=True` → `mode="replay"`
- `rnd_new=False, rnd_last=False` → `mode="default"`
- `rnd_new=True, rnd_last=True` → `mode="new"` (rnd_new wins)

**`CliArgsSource`**:
- Default config produces `TestCliArgs` with all default values matching `TestCliArgs` field defaults.
- Custom `test_name` propagates correctly.

## Constraints

- No filesystem access in either module.
- `run_depth` default is `"post"`, not `None`.
