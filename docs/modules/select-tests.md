# `select-tests`

**Class:** `SelectTestsMod` (`modules/rtl_buddy/setup.py`)

[Back to index](index.md)

Fans the suite out into one `TestConfig` per selected test. With no `test_name`, emits every test; otherwise emits the matching subset. This is where the per-test stream begins.

## Inputs

| Port | Type | Default | Meaning |
|---|---|---|---|
| `suite_cfg` | `SuiteConfig` | — | suite from `route-list`'s `off` branch (`flag-gate` instance) |
| `test_name` | `str` | `""` | positional CLI arg; empty means all tests |

## Outputs

`test` — one `TestConfig` per selected test (generator).

## Graph node

`select`, contract `default`.
