# `summarise-results`

**Class:** `SummariseResultsMod` (`modules/rtl_buddy/summarise_results.py`)

[Back to index](index.md)

Collects one `TestResult` per invocation across the whole run, then on `finalise()` renders the aligned summary table and emits it. If any result is a `FAIL`, it logs a consolidated `ERROR` — the signal that drives the non-zero exit.

## Inputs

| Port | Type | Meaning |
|---|---|---|
| `result` | `TestResult` | one result; the [`any`](../contracts/any.md) contract funnels all 13 terminal ports onto this single input |

## Outputs

`finalise` only: `table` — the rendered plain-text table; emits nothing if no results were collected (list-mode or an aborted run).

## Behaviour

Each row is `test_name / result / desc`, `None` fields rendered as `NA`. The `FAIL` count, if non-zero, is logged as `test_failures` at `ERROR`, deferring a failing exit until the run completes.

## Graph node

`results-summary`, contract `any` (`mapping: result`) — its `contract_port_mappings` funnel all 13 terminal result ports (`compile_fail`, `sim_timeout`, `load_model`, `filelist`, `sweep`, `preproc`, `seed`, `parse_plain`, `parse_uvm`, `skip`, `stop_pre`, `stop_comp`, `stop_sim`) onto `result`. The `table` output fans to [print-summary](print-summary.md) and [write-summary-log](write-summary-log.md).
