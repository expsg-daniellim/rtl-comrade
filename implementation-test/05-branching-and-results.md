# Branching, early-exit, and results

`rtl_buddy` is an imperative pipeline with many early `return`s; a graph is fixed dataflow.
This file shows how each early-exit becomes a named output port that routes the item off
the main line, and how the mutually-exclusive results re-converge through a custom contract.

## Each terminal outcome is a named output port

For each test invocation `rtl_buddy` produces **exactly one** terminal result. Each
producing stage emits it on a dedicated output port that goes to the collector; the
continue-path goes to the next stage:

| stage | continue port → next stage | terminal port → `agg` |
|---|---|---|
| `filter` | `keep` | `skip` (`SkipResults`) |
| `gate-pre` | `go` | `stop` (`EarlyStopResults`) |
| `cc-int` | `ok` | `fail` (`CompileFailResults`) |
| `gate-comp` | `go` | `stop` (`EarlyStopResults`) |
| `sim-int` | `ok` | `timeout` (`SimTimeoutResults`) |
| `gate-sim` | `go` | `stop` (`EarlyStopResults`) |
| `route-post` | `uvm` → `parse-uvm-log`, `plain` → `parse-log` | — (classifier only) |
| `parse-log` | — | `result` (PASS/FAIL/NA) |
| `parse-uvm-log` | — | `result` (PASS/FAIL/NA) |

Because a terminal item leaves the main line, **no downstream stage ever sees it** — which
is why no module needs an "am I already done?" guard. Choosing the port is ordinary
business logic (`rc == 0`, `level out of range`, `timed_out`), expressed as a named-port
return — the framework's sanctioned mechanism, and statically analysable (all port names
are string literals, so `definite_emits` holds).

## `--early-stop` as gates

Three `early-stop-gate` nodes sit at the pre/comp/sim boundaries. Each compares the global
`early_stop` value (a persistent input) against its configured `phase`; if the run should
stop here it emits `stop`, else `go`. Since `early_stop` is one global value, a gate makes
the same choice for every item — so the gate at the configured boundary diverts the whole
stream, reproducing `rtl_buddy`. `--early-stop post` (default) means no gate fires.

## `--list` as an empty stream

`select-tests` with `list=True` prints names and emits nothing. The empty stream
propagates `EndSentinel` to `agg`, which finalises with zero rows → exit 0. No special
casing anywhere else.

## Re-convergence: the custom `merge` contract

The 8 terminal ports feed `agg`. Input ports are single-source, so `agg` has 8 input ports
(one per source). A contract must drain *whichever* port has an item, because for any given
key only one ever fires. The built-ins don't fit:

- **`branch_aware_join` — no.** It fires a key only when *every* port has seen it (real or
  `BranchSkip`). Here each key reaches exactly one port; the other ports' upstreams never
  process that key and can't emit `BranchSkip` for it. The key stays incomplete forever.
- **`group_until_end` / `zip` / `keyed_join` — no.** All assume every port participates per
  unit of work. Our terminal ports are mutually exclusive per key.

So we **author a `merge` contract** — exactly the kind of scheduling that belongs in a
contract. Semantics: *forward the next item from any port as it arrives; end when all ports
have ended.* It returns `{firing_port_name: payload}`, and `aggregate-results` takes
`**fired` (one entry per call).

```python
@dataclass
class MergeContract:
    """Non-correlating fan-in: forward each item from any port; end when all ports end."""

    id:str
    ports:dict[str, ContractPort]
    _pending:dict[str, asyncio.Task] = field(default_factory=dict, init=False, repr=False)

    async def get_inputs(self) -> dict[str, Payload] | EndSentinel:
        # keep one in-flight get() per still-open port so no item is dropped between calls
        for name, port in self.ports.items():
            if not port.has_ended() and name not in self._pending:
                self._pending[name] = asyncio.ensure_future(port.get())

        while self._pending:
            done, _ = await asyncio.wait(self._pending.values(),
                                         return_when=asyncio.FIRST_COMPLETED)
            for name, task in list(self._pending.items()):
                if task not in done:
                    continue
                val = task.result()
                del self._pending[name]
                if isinstance(val, EndSentinel):
                    continue                      # that port closed; others may still run
                return { name: val }              # one item, under its source port's name

        return EndSentinel(self.id)
```

Notes:

- Pending `get()` tasks persist on `self` across calls, so an item that arrives on a
  not-yet-returned port is never lost.
- `merge` is broadly reusable: any "collect results from alternative branches" fan-in.
  Register it in the contracts manifest (see [06](06-graph-yaml.md)).
- This is the one piece of genuine scheduling the design adds, and it lives where the
  framework wants scheduling — in a contract, not in a module.

## Result aggregation and exit code

`aggregate-results` accumulates each delivered `result` in `run()` and, in `finalise()`:

1. prints the summary table (`key`/`test_name`, `result`, `desc`), reproducing
   `do_cmd_test`'s "Test Results Summary";
2. logs `ERROR` if **any** row is not `is_pass()`. The harness turns a single ERROR into a
   non-zero exit, reproducing `rtl_buddy`'s `exit_code |= 0 if is_pass() else 1` exactly
   (SKIP/PASS contribute nothing; FAIL/NA — compile fail, timeout, early-stop, unknown —
   force exit 1).

`CRITICAL` stays reserved for harness-fatal conditions (missing/malformed `root_config.yaml`,
missing builder/testbench), matching `rtl_buddy`'s `logger.critical` → `typer.Abort`.
