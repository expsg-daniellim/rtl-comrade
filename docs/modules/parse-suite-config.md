# `parse-suite-config`

**Class:** `ParseSuiteConfigMod` (`modules/rtl_buddy/setup.py`)

[Back to index](index.md)

Parses the test suite YAML (`tests.yaml`) into a `SuiteConfig` — a map of test name → `TestConfig`, each cross-referenced to its testbench. Uses module-private serde types `SuiteConfigFile`/`TestConfigFile`.

## Inputs

| Port | Type | Default | Meaning |
|---|---|---|---|
| `test_config` | `str` | `"tests.yaml"` | suite file path (CLI `--test-config`) |

## Config

```yaml
config:
  prefix_suite: true
```

| Field | Type | Default | Purpose |
|---|---|---|---|
| `prefix_suite` | `bool` | `false` | when true, each test's `key` is `<suite_dir.name>/<test_name>` (e.g. `sandbox/basic`) instead of the bare test name; the regression graph sets it to tell same-named tests in different suites apart |

## Outputs

`default` — a `SuiteConfig`.

## Failure routing

A `test_config` that fails to resolve is `log.fatal` (`path_invalid` for an embedded null character, `path_symlink_loop` / `path_os_error` for a symlink loop or other OS error). Every read/parse error is caught and mapped to a distinct `log.fatal` event (`invalid_unicode`, `not_found`, `is_directory`, `permission_denied`, `os_error`, `serde_error`, `yaml_invalid`, `yaml_unreadable`, `invalid_uvm_config`); an unknown testbench reference in a test is `log.fatal` (`unknown_testbench`). The suite must parse for any test to run.

## Graph node

`parse-suite`, contract `unit`.
