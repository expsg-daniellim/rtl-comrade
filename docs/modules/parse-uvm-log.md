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

None — this is a leaf node. The verdict is communicated via log events.

## Failure routing

An unreadable log (`OSError`), a missing summary, or a summary lacking the WARNING/ERROR/FATAL counts each logs a distinct `ERROR` event (`parse_uvm_unreadable` / `parse_uvm_no_summary` / `parse_uvm_invalid_summary` / `parse_uvm_failed`). A passing summary logs `parse_uvm_passed` at `INFO`.

## Graph node

`parse-uvm-log`, contract `keyed_join` (`key_field: key`).
