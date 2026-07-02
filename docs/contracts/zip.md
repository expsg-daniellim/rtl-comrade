# `zip`

**Class:** `ZipContract` (`contracts/zip.py`)

[Back to index](index.md)

Pairs items from all input ports by position: first-with-first, second-with-second, and so on. All ports must deliver items at the same rate. This is the simplest correct contract when streams are guaranteed to be aligned.

## Config

None.

## Termination

Ends when any port ends. A data/end split for the same invocation is logged as a `mismatched_ends` error only within a single control-dependence partition (ports sharing the same `branch_labels`): a branch may end one arm while another stays live, so a split across partitions is a legitimate branch outcome, not a mismatch. See [branch_labels.md](../harness/branch_labels.md).

## Example use cases

**Processing aligned input/output pairs.** Two upstream nodes produce a `query` stream and an `answer` stream at exactly the same rate. The `evaluate` node receives one `(query, answer)` pair per invocation.

```yaml
nodes:
  - id: evaluate
    module: evaluate_pair
    contract: zip
```

**Zipping an index stream with a value stream.** A generator emits `(index, value)` on separate ports in lock-step; the downstream node receives both together.
