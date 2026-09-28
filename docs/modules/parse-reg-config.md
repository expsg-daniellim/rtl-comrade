# `parse-reg-config`

**Class:** `ParseRegConfigMod` (`modules/rtl_buddy/setup.py`)

[Back to index](index.md)

Parses the regression config (`regressions.yaml`) and yields one resolved suite config `Path` per `test-configs` entry — the fan-out point from one regression config to N suites. Each entry is resolved against the regression config's directory, not CWD. Uses the module-private serde type `RegConfigFile`.

## Inputs

| Port | Type | Default | Meaning |
|---|---|---|---|
| `reg_config_path` | `Path` | — | path to the regression config |

## Outputs

`default` — one resolved `Path` per `test-configs` entry, in file order. An empty `test-configs` list yields nothing.

## Failure routing

Every read/parse error is caught and mapped to a distinct `log.fatal` event (`reg_config_invalid_unicode`, `reg_config_not_found`, `reg_config_is_directory`, `reg_config_permission_denied`, `reg_config_os_error`, `reg_config_yaml_invalid`, `reg_config_yaml_unreadable`, `reg_config_serde_error`). An entry that fails to resolve is `log.fatal`: `reg_config_entry_invalid` (e.g. an embedded null character), `reg_config_entry_symlink_loop` (`RuntimeError`, Python ≤ 3.12) or `reg_config_entry_os_error` (`OSError`, Python ≥ 3.13).

## Graph node

`parse-reg`, contract `unit`, in the `regression` graph. `reg_config_path` arrives from `resolve-reg-path`; each yielded path feeds `parse-suite`'s `test_config` port.
