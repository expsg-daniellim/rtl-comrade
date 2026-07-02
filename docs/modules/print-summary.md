# `print-summary`

**Class:** `PrintSummaryMod` (`modules/rtl_buddy/summarise_results.py`)

[Back to index](index.md)

Prints the summary table to stdout, ANSI-colourising the `PASS`/`FAIL`/`NA` verdict tokens when stdout is a TTY (`SKIP` left plain, matching upstream).

## Inputs

| Port | Type | Meaning |
|---|---|---|
| `table` | `str` | the rendered table from [summarise-results](summarise-results.md) |

## Outputs

None — prints.

## Graph node

`print-summary`, contract `default`.
