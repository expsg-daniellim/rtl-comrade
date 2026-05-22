# `group_until_end`

**Class:** `GroupUntilEndContract` (`contracts/group_until_end.py`)

[Back to index](index.md)

Accumulates items from each port into a list until every port emits a `GroupEnd` sentinel payload. Each call to `get_inputs` collects exactly one group. The module receives each port's entire batch as a list. Multiple groups per stream are supported by calling `get_inputs` repeatedly; the `GroupEnd` sentinel resets the accumulator.

## Config

None.

## Sentinel

`GroupEnd` is imported from `contracts.sentinels`. Emit it as a payload value — not as an `EndSentinel` — to signal the end of one group while keeping the port open for the next.

```python
from contracts.sentinels import GroupEnd

async def run(self, items):
    ...
    yield ("out", GroupEnd())   # closes current group
```

The stream itself ends with an ordinary `EndSentinel` from the upstream node.

## Termination

Ends when any port delivers an `EndSentinel` mid-group. The accumulated items for the current incomplete group are discarded.

## Example use cases

**Aggregating all log lines for a job before writing a report.** A log-streaming node emits one line per item and a `GroupEnd` when the job finishes. The reporting node accumulates the full log batch and writes one report per job.

```yaml
nodes:
  - id: write_report
    module: write_job_report
    contract: group_until_end
```

The `run` method receives `{"lines": ["line 1", "line 2", ...]}` rather than individual lines.

**Collecting all items from a paginated source before processing.** A paginated API fetcher emits items one at a time and a `GroupEnd` at each page boundary. A downstream node processes each complete page as a batch.

**Running a batch computation once all inputs are ready.** Multiple upstream nodes each produce a sequence of partial results, signalling completion with `GroupEnd`. The downstream node accumulates all partial results and produces one final output.
