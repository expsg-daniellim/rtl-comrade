# `route-list-mode`

**Class:** `RouteListModeMod` (`modules/rtl_buddy/setup.py`)

[Back to index](index.md)

Routes the whole suite to either the list-names branch or the run branch, based on the `--list` flag.

## Inputs

| Port | Type | Default | Meaning |
|---|---|---|---|
| `suite_cfg` | `SuiteConfig` | — | parsed suite |
| `list` | `bool` | `False` | `--list`: print names instead of running |

The `list` port is the `list_` parameter in source — a trailing underscore avoids shadowing the builtin, dropped for the port name (see [module-implementation/implementation.md](../module-implementation/implementation.md)).

## Outputs

`list` — the suite (when `--list`); `run` — the suite (otherwise). Exactly one fires.

## Graph node

`route-list`, contract `unit`. The `list` branch feeds [list-test-names](list-test-names.md); the `run` branch feeds [select-tests](select-tests.md).
