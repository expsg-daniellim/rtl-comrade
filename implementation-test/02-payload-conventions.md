# Payload conventions

Modules receive raw values (the harness unwraps `Payload` before calling `run`). There is
**no single payload type** threaded through the graph. Instead there are three small,
purpose-specific payload shapes, plus one correlation key.

## The correlation key

A stable string identifying one test invocation, stamped at each fan-out:

- `select` → `key = "<test_name>"`
- `sweep`  → `key = "<test_name>#<sweep_idx>"`
- `runs`   → `key = "<test_name>#<sweep_idx>#<run_id>"`

The key exists so the two join nodes can match a subprocess result back to the test it
came from. It appears as a field only on payloads that actually enter a `keyed_join`
(the `ctx` and `proc` payloads). Modules copy it forward; they never parse or branch on it.

## Shape 1 — `ctx`: the main-line context record

A minimal dict that rides the main line and is forwarded stage-to-stage:

```python
ctx = {
    "key":  "alu_smoke#0#0",   # correlation key
    "test": <TestConfig>,      # the rtl_buddy TestConfig (mutated in place by preproc/sweep)
    "simv": <Path>,            # ADDED by interpret-compile; absent before compile
}
```

Rules that keep this from becoming the rejected envelope:

- **Only genuinely-pervasive values live here.** `test` is needed by almost every stage;
  `simv` is needed by every run of a compiled test. A value earns a place in `ctx` *only
  if every downstream stage needs it*. Everything else is a Shape-2/3 payload consumed
  locally.
- **No derived or transient values** — `argv`, `rc`, `stdout`, `stderr`, `log`, `duration`
  never enter `ctx`.
- **No `result` field, ever.** A terminal outcome does not ride inside `ctx`; it leaves the
  main line as a Shape-3 payload (below). This is what removes the need for any
  "am I already done?" guard inside modules.
- Modules read only `ctx["test"]` (and `ctx["simv"]` post-compile). They forward `ctx`
  unchanged on their continue-port.

> Why a dict and not separate `key`/`test` ports? `keyed_join` correlates by reading
> `payload[key_field]`, so any payload entering a join must be a dict carrying the key.
> Keeping `ctx` a dict everywhere makes the join trivial and the forwarding uniform.

## Shape 2 — work payloads (local, single-hop)

Values produced by one stage for the next, carrying the key so a downstream join can match:

```python
filelist = { "key": k, "filelist": <Path> }                 # write-filelist  → build-compile-cmd
command  = { "key": k, "argv": [ ... ] }                     # build-*-cmd     → run-process
proc     = { "key": k, "rc": int, "stdout": bytes,           # run-process     → interpret-*
             "stderr": bytes, "timed_out": bool }
seed     = { "key": k, "seed": int }                         # resolve-seed    → build-sim-cmd
```

These never accumulate. Each is consumed by exactly the next stage(s).

## Shape 3 — result payloads (terminal, route to the collector)

The single shape every terminal output port emits, regardless of which stage produced it:

```python
result = { "key": k, "result": <TestResults> }
```

Emitted on a stage's terminal port (`skip`, `stop`, `fail`, `timeout`, `result`) and routed
to one port of `aggregate-results`. See [05](05-branching-and-results.md).

## `TestResults` values used at the terminal ports

Reuse `rtl_buddy.runner.test_results`:

| terminal port (node) | result | is_pass? | exit contribution |
|---|---|---|---|
| `skip` (`filter`) | `SkipResults(desc)` | yes (SKIP) | none |
| `stop` (`gate-*`) | `EarlyStopResults(desc)` | no (NA) | exit 1 |
| `fail` (`interpret-compile`) | `CompileFailResults` | no (FAIL) | exit 1 |
| `timeout` (`interpret-sim`) | `SimTimeoutResults` | no (FAIL) | exit 1 |
| `result` (`parse-log` / `parse-uvm-log`) | `TestPassResults` / FAIL / NA | PASS→yes | non-pass→exit 1 |

`TestResults.is_pass()` is the single source of truth for the exit code (SKIP counts as
pass; NA/FAIL do not), exactly as in `rtl_buddy`.

## Sentinels

`EndSentinel` (handled entirely by contracts) is the only sentinel. No `GroupEnd` or
`BranchSkip` is used: branches are mutually exclusive and re-converge through the `merge`
contract, not through `branch_aware_join`.
