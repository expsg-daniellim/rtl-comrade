# `zip`

**Class:** `ZipContract` (`contracts/contracts.py`)

[Back to index](index.md)

Pairs items from all input ports by position: first-with-first, second-with-second, and so on. All ports must deliver items at the same rate. This is the simplest correct contract when streams are guaranteed to be aligned.

## Config

None.

## Termination

Ends when any port ends. If some ports have delivered data and others have delivered `EndSentinel` for the same invocation, the mismatch is logged as an error.

## Example use cases

**Processing aligned input/output pairs.** Two upstream nodes produce a `query` stream and an `answer` stream at exactly the same rate. The `evaluate` node receives one `(query, answer)` pair per invocation.

```yaml
nodes:
  - id: evaluate
    module: evaluate_pair
    contract: zip
```

**Zipping an index stream with a value stream.** A generator emits `(index, value)` on separate ports in lock-step; the downstream node receives both together.
