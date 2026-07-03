# `parse-log`

**Class:** `ParseLogMod` (`modules/rtl_buddy/sim.py`)

[Back to index](index.md)

Scans the plain sim stdout for the first `PASS`/`FAIL` line (and any `ERR:`/`FAT:` detail) and produces a parse `TestResult`. A `FAIL` line wins over a `PASS` line; neither present yields an `NA` "result unknown".

## Inputs

| Port | Type | Meaning |
|---|---|---|
| `test` | `TestConfig` | the run |
| `proc` | `Proc` | finished sim (supplies `stdout_path`) |

## Outputs

`default` — a `TestResult.parse` with verdict `PASS` / `FAIL` / `NA`.

## Failure routing

An unreadable log (`OSError`) becomes a `FAIL` result with the error text. `FAIL` and `NA` verdicts also emit an `ERROR` log (`parse_log_failed` / `parse_log_unknown`); a clean `PASS` logs nothing.

## Graph node

`parse-log`, contract `keyed_join` (`key_field: key`). The `default` port fans into [summarise-results](summarise-results.md) as `parse_plain`.
