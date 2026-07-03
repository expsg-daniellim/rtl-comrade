# `parse-suite-config`

**Class:** `ParseSuiteConfigMod` (`modules/rtl_buddy/setup.py`)

[Back to index](index.md)

Parses the test suite YAML (`tests.yaml`) into a `SuiteConfig` — a map of test name → `TestConfig`, each cross-referenced to its testbench. Uses module-private serde types `SuiteConfigFile`/`TestConfigFile`.

## Inputs

| Port | Type | Default | Meaning |
|---|---|---|---|
| `test_config` | `str` | `"tests.yaml"` | suite file path (CLI `--test-config`) |

## Outputs

`default` — a `SuiteConfig`.

## Failure routing

Every read/parse error is caught and mapped to a distinct `log.fatal` event (`invalid_unicode`, `not_found`, `is_directory`, `permission_denied`, `os_error`, `serde_error`, `yaml_invalid`, `yaml_unreadable`, `invalid_uvm_config`); an unknown testbench reference in a test is `log.fatal` (`unknown_testbench`). The suite must parse for any test to run.

## Graph node

`parse-suite`, contract `unit`.
