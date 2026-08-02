# `list-test-names`

**Class:** `ListTestNamesMod` (`modules/rtl_buddy/setup.py`)

[Back to index](index.md)

Prints the suite's test names space-separated. Terminal node for `--list` mode; emits nothing.

## Inputs

| Port | Type | Meaning |
|---|---|---|
| `suite_cfg` | `SuiteConfig` | suite from `route-list`'s `on` branch (`flag-gate` instance) |

## Outputs

None — prints to stdout, returns `None`.

## Graph node

`list-names`, contract `default`.
