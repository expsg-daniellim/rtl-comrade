# `parse-uvm-log`

**Class:** `ParseUvmLogMod` (`modules/rtl_buddy/sim.py`)

[Back to index](index.md)

Extracts the UVM Report Summary severity counts from the sim stdout and applies the test's UVM thresholds: `PASS` when warnings ≤ `max_warns`, errors ≤ `max_errors`, and no fatals; `FAIL` otherwise. A missing or malformed summary is a `FAIL`.

## Inputs

| Port | Type | Meaning |
|---|---|---|
| `test` | `TestConfig` | the run (supplies `uvm` thresholds) |
| `proc` | `Proc` | finished sim (supplies `stdout_path`) |

## Outputs

`default` — a `TestResult.parse` with verdict `PASS` / `FAIL`.

## Failure routing

An unreadable log (`OSError`), a missing summary, or a summary lacking the WARNING/ERROR/FATAL counts each produces a `FAIL` result with a distinct `ERROR` event (`parse_uvm_unreadable` / `parse_uvm_no_summary` / `parse_uvm_invalid_summary` / `parse_uvm_failed`); a passing summary logs nothing.

## Graph node

`parse-uvm-log`, contract `keyed_join` (`key_field: key`). The `default` port fans into [summarise-results](summarise-results.md) as `parse_uvm`.
