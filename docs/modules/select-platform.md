# `select-platform`

**Class:** `SelectPlatformMod` (`modules/rtl_buddy/setup.py`)

[Back to index](index.md)

Runs `uname` and picks the `PlatformConfig` whose `unames` list contains the result.

## Inputs

| Port | Type | Meaning |
|---|---|---|
| `root_cfg` | `RootConfig` | parsed root config |

## Outputs

`default` — the matching `PlatformConfig`.

## Failure routing

`log.fatal` (`uname_unavailable`) if `uname` can't be launched; `log.fatal` if no configured platform matches the host `uname`.

## Graph node

`select-platform`, contract `unit`.
