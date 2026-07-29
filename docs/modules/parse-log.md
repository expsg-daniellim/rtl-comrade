# `parse-log`

**Class:** `ParseLogMod` (`modules/rtl_buddy/sim.py`)

[Back to index](index.md)

Scans the plain sim stdout for the first `PASS`/`FAIL` line (and any `ERR:`/`FAT:` detail) and logs the verdict. A `FAIL` line wins over a `PASS` line; neither present yields an `NA` "result unknown".

## Inputs

| Port | Type | Meaning |
|---|---|---|
| `test` | `TestConfig` | the run |
| `proc` | `Proc` | finished sim (supplies `stdout_path`) |

## Outputs

None — this is a leaf node. The verdict is communicated via log events.

## Failure routing

An unreadable log (`OSError`) logs `parse_log_unreadable` at `ERROR`. A `FAIL` verdict logs `parse_log_failed` at `ERROR`; an `NA` verdict logs `parse_log_unknown` at `ERROR`. A clean `PASS` logs `parse_log_passed` at `INFO`.

## Graph node

`parse-log`, contract `keyed_join` (`key_field: key`).
