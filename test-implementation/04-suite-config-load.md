# Spec 04: SuiteConfigLoad

## What this covers

Implement `SuiteConfigLoad` in `modules/rtl_buddy_compat/suite.py`. This is the most complex module in the graph: it parses `tests.yaml`, resolves model and testbench paths, and normalizes all per-test config fields into `TestConfigEnvelope` instances. The downstream routing and selection modules (spec 05) live in the same file but are implemented separately.

## Prerequisites

Spec 00 (artefacts) must be complete.

## Before you start

Read:
- `rtl_buddy/src/rtl_buddy/config/suite.py` — full file; `SuiteConfigFile`, `SuiteConfig`, `get_tests()`, `get_test_names()`
- `rtl_buddy/src/rtl_buddy/config/test.py:L1-L264` — `TestConfig`, `TestConfigFile`, `initialise()`, all field types
- `rtl_buddy/src/rtl_buddy/rtl_buddy.py:L292-L342` — how `_do_test_suite()` uses the suite

## File: `modules/rtl_buddy_compat/suite.py`

Create this file. Spec 05 will add `ListTestsBranch`, `ListTestsRender`, and `TestSelect` to it.

### `SuiteConfigLoad`

```
contract: zip
inputs:  cli: TestCliArgs, root: RootContext
outputs: default → SuiteContext
```

Implementation steps:

1. Open `cli.test_config`. Fatal if file not found (`suite.py:L18-L22`).

2. Parse YAML. Top-level keys: `testbenches` (dict), `tests` (list). Fatal if malformed.

3. Build `testbench_name → testbench_dict` lookup from the `testbenches` section.

4. For each test entry in `tests`, in declaration order:
   a. Resolve `model_path` relative to the directory containing `cli.test_config` (`test.py:L247-L264`).
   b. Look up `testbench` by name in the testbench lookup. Fatal if not found.
   c. Normalize `plusargs` to `list[str]` — entries may be plain strings or single-key dicts; flatten to `"key=value"` or `"key"` strings.
   d. Normalize `plusdefines` to `dict[str, str | None]` — entries may be strings (`"KEY"` → `{KEY: None}`) or dicts (`{"KEY": "val"}` → `{KEY: "val"}`).
   e. Set `declaration_index` to 0-based position in the list.
   f. Populate `TestConfigEnvelope` with all fields.

5. Emit `SuiteContext(path=cli.test_config, test_names=[t.name for t in tests], tests=tests)`.

Key field mappings from `TestConfig` (`test.py:L30-L63`):
- `uvm`: optional dict; keep as-is if present, `None` if absent
- `reglvl`: may be `int`, `dict`, or absent → `None`
- `timeout`: int seconds or absent → `None`
- `preproc_path`, `postproc_path`, `sweep_path`: string paths or absent → `None`; resolve relative to the suite config directory

## Create `modules/rtl_buddy_compat/config.yaml`

```yaml
files:
- file: suite.py
  plugins:
  - name: suite_config_load
    class_name: SuiteConfigLoad
```

Spec 05 will append `ListTestsBranch`, `ListTestsRender`, and `TestSelect` to this entry.

## Tests

Write `modules/rtl_buddy_compat/tests/test_suite_load.py`.

Use `tmp_path` to write minimal `tests.yaml` files.

- Valid suite with two tests → `SuiteContext` has both names in declaration order
- `plusdefines: ["DEBUG"]` → `{"DEBUG": None}`
- `plusdefines: [{WIDTH: "8"}]` → `{"WIDTH": "8"}`
- `plusargs: ["verbose"]` → `["verbose"]`
- `plusargs: [{timeout: "100"}]` → `["timeout=100"]`
- Missing testbench reference → fatal
- Missing `tests.yaml` → fatal
- `declaration_index` is 0 for first test, 1 for second
- `model_path` is resolved relative to suite config directory (not cwd)
- Missing `reglvl` → `None` in envelope
- `reglvl: 3` → `3`
- `reglvl: {vcs: 5}` → `{"vcs": 5}`

## Constraints

- Preserve declaration order. Do not sort tests.
- `model_path`, `preproc_path`, `postproc_path`, `sweep_path` must be absolute or project-relative strings, not raw relative paths.
- Do not carry live `SuiteConfig` objects; everything into `TestConfigEnvelope`.
