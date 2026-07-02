# `write-summary-log`

**Class:** `WriteSummaryLogMod` (`modules/rtl_buddy/summarise_results.py`)

[Back to index](index.md)

Writes the (uncoloured) summary table to a log file.

## Inputs

| Port | Type | Meaning |
|---|---|---|
| `table` | `str` | the rendered table from [summarise-results](summarise-results.md) |

## Config

```yaml
config:
  log_path: rtl_buddy.log
```

| Field | Type | Default | Purpose |
|---|---|---|---|
| `log_path` | `Path` | `rtl_buddy.log` | summary log destination |

## Outputs

None — writes the file.

## Failure routing

A write failure (`OSError`) is `log.error` (`summary_log_write_failed`) — the run still finishes.

## Graph node

`write-summary-log`, contract `default`.
