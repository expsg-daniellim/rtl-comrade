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

## Re-convergence: the fan-in module and `any` contract

The 13 terminal ports must re-converge at `agg`. A given key reaches exactly one of the 13
ports; the others never fire for it. The built-in contracts don't fit:

- **`branch_aware_join` — no.** It fires a key only when *every* port has seen it (real or
  `BranchSkip`). Our terminal ports are mutually exclusive per key; the incomplete key
  stays unresolved forever.
- **`keyed_join` / `default` (all-ports) — no.** Both assume every port participates per
  unit of work.

The solution is two cooperating pieces:

**`fan-in-results` module** — uses `**kwargs` so the harness populates its 13 ports from
graph edges at load time (non-definite-inputs mechanism, `graph.py:95-97`). The body
discards the port name and forwards the payload:

```python
class FanInResultsMod:
    def run(self, **inputs):
        _, payload = next(iter(inputs.items()))
        return ("result", payload)
```

**`any` contract** — fires on whichever port is ready first, one delivery per call, and
propagates `EndSentinel` after all ports have ended:

```python
@dataclass
class AnyContract:
    @dataclass(frozen=True)
    class Config:
        release_lock: str | None = None

    id: str
    ports: dict[str, ContractPort]
    config: Config
    _pending: dict[str, asyncio.Task] = field(default_factory=dict, init=False, repr=False)

    async def get_inputs(self) -> dict[str, Payload] | EndSentinel:
        for name, port in self.ports.items():
            if not port.has_ended() and name not in self._pending:
                self._pending[name] = asyncio.ensure_future(port.get())

        while self._pending:
            done, _ = await asyncio.wait(self._pending.values(), return_when=asyncio.FIRST_COMPLETED)
            for name, task in list(self._pending.items()):
                if task not in done:
                    continue
                val = task.result()
                del self._pending[name]
                if isinstance(val, EndSentinel):
                    continue
                if self.config.release_lock is not None:
                    _get_lock(self.config.release_lock).release()
                return {name: val}   # port name surfaced to module; FanInResultsMod discards it

        return EndSentinel(self.id)
```

### Invariants and termination

- **State held across calls.** `_pending: dict[str, asyncio.Task]` carries one in-flight
  `port.get()` task per open port. Tasks created in call N but not returned remain in
  `_pending` and are honoured in call N+1. Pending tasks are **never cancelled** between
  calls.
- **No-loss invariant.** `asyncio.wait(..., FIRST_COMPLETED)` may report several `done`
  tasks in one wake-up. The contract returns the first non-`EndSentinel` result and leaves
  the remaining done tasks in `_pending`; on the next call they are returned immediately
  (already-completed).
- **Per-port `EndSentinel` handling.** When a port's task resolves to `EndSentinel`, the
  task is removed from `_pending` and no new task is created for it (`port.has_ended()` is
  now `True`). Other ports keep being awaited.
- **Drainage order.** A port's payloads queued before its `EndSentinel` are delivered
  first, by FIFO at the port.
- **Termination rule.** `get_inputs()` returns `EndSentinel(self.id)` exactly when every
  port has emitted its `EndSentinel` and every previously-pending task has resolved
  (`_pending` is empty and no new tasks can be created).
- **`release_lock` side-effect** (when configured — interim shim only, see
  [Serialising contracts](#serialising-contracts--interim-parallel-safety-posture)). Fires
  once per delivered payload, immediately before the `return`. `EndSentinel` paths do
  **not** release. Mismatched release (no prior acquire) raises `RuntimeError` from
  `asyncio.Lock.release()` — fail-fast, no guard.
- **Cancellation.** Mid-`get_inputs` cancellation by the harness drops in-flight items.
  This is process-end behaviour, matching every other contract.

`any` is broadly reusable for any "deliver the first ready item" fan-in. Register it in
the contracts manifest (see [06](06-graph-yaml.md)).

## Serialising contracts — interim parallel-safety posture

> **Temporary measure.** The serialising contracts described in this section exist *only*
> until the upstream `rtl_buddy` change to per-test (per-invocation) artefact directories
> lands. Once compile/sim each get their own working directory, the collisions these
> contracts protect against (next compile stomping the previous test's `obj_dir`, `simv`,
> `run.f`) disappear, and `write-filelist` returns to plain `default` while `fan-in`'s
> `any` contract drops its `release_lock` config field. See
> [07](07-ambiguities-and-assumptions.md) item 17. Do not build further design on top of
> the shim; treat it as removable.

### The hazard

A compile produces non-graph-routed artefacts in CWD (`obj_dir_<tag>/`, the `simv` binary,
and `run.f`) that the *same test's* sim later consumes. The harness launches all node tasks
concurrently (`asyncio.gather`), so absent any serialisation a second compile can start while
a previous test's sim has not yet read those artefacts, and stomp them. `sim-build` reads `simv` from `ctx["simv"]` (set by `build-compile-cmd`), but the file on
disk that the path refers to is shared. The lock makes this region atomic per test.

### Region and lock semantics

- **Region**: from `write-filelist`'s invocation through `aggregate-results`' receipt of that
  test's terminal result.
- **Atomicity unit**: one (test, sweep-variant). For the plain `test` graph `expand-runs`
  defaults to `[None]` (R=1) so each acquire matches exactly one merge release; sibling
  graphs with R>1 (`randtest`) cannot use this design as-is — see Constraints below.
- **Lock object**: a single process-wide `asyncio.Lock` per `lock_name`. The plain `test`
  graph uses one lock named `compile-sim`.

### Two contracts share one lock

The acquire side is a new contract `serial_acquire` on `write-filelist`. The release side
is the `any` contract on `fan-in`, configured with an optional `release_lock` field. Both
contracts import the same module-level lock registry from `contracts/serial.py`:

```python
# contracts/serial.py
import asyncio
from dataclasses import dataclass
from rtl_comrade.api import Payload, EndSentinel, ContractPort
from rtl_comrade.contract_default import DefaultContract

# Module-level; survives across contract instantiations because the plugin loader reuses
# the sys.modules entry (loader.py:156-159).
_LOCKS: dict[str, asyncio.Lock] = {}

def _get_lock(name: str) -> asyncio.Lock:
    if name not in _LOCKS:
        _LOCKS[name] = asyncio.Lock()
    return _LOCKS[name]

@dataclass
class SerialAcquireContract(DefaultContract):
    """Like default, but acquires a named lock per consumed item before returning."""

    @dataclass(frozen=True)
    class Config(DefaultContract.Config):
        lock_name: str = ""

    async def get_inputs(self) -> dict[str, Payload] | EndSentinel:
        inputs = await super().get_inputs()
        if isinstance(inputs, EndSentinel):
            return inputs
        await _get_lock(self.config.lock_name).acquire()
        return inputs
```

The acquire happens *after* default-contract logic has resolved the upstream item and
*before* the harness calls the module — so a `write-filelist` invocation never starts
until the lock is free, and the contract only acquires when it has real work to dispatch.
End-sentinel propagation does not acquire.

The release side is the `AnyContract`'s `Config.release_lock` field (sketch in
[Re-convergence](#re-convergence-the-fan-in-module-and-any-contract)). On every
`get_inputs()` call that delivers one payload, the contract releases the named lock once.
Returning `EndSentinel` does not release.

`asyncio.Lock` releases are not bound to the acquiring task, so the acquire-in-`write-filelist`
/ release-in-`agg` cross-node handoff is sound.

### Topology consequences

- The pre-region nodes (`select`, `filter`, `load-model`, `sweep`, `preproc`, `gate-pre`)
  still parallelise across tests; only `write-filelist` onward serialises.
- The mid-region nodes (`cc-build`, `cc-run`, `cc-int`, `gate-comp`, `runs`, `seed`,
  `sim-build`, `sim-run`, `randseed`, `link-latest`, `sim-int`, `gate-sim`, `route-post`,
  `parse-log`, `parse-uvm-log`) do not change contract — the global lock alone is enough
  to ensure only one test's data is in flight through them at a time.
- Every per-test failure path inside the region (`cc-int.fail`, `gate-comp.stop`,
  `seed.fail`, the four pre-region `*.fail` ports that also route into `fan-in`) still
  reaches `agg` via `fan-in`; the release fires uniformly on every port.

### Constraints

- **Plain `test` graph only (R=1).** Each `serial_acquire` invocation must match exactly
  one merge release. With R>1, one compile holds the lock while R sim-runs produce R
  results — only one releases. The other R−1 either orphan the lock or release-too-early.
  Sibling graphs (`randtest`, `regression`) need a different release rule (e.g. a per-key
  release counter on the merge side, or a post-`sim-run` release point that holds for all
  R runs); design deferred until those graphs are built.
- **Every acquired item must reach `agg`.** The invariant assumed by acquire/release
  pairing is that any item that crosses `write-filelist` eventually emits one terminal
  payload into the merge fan-in. If an upstream contract drops items mid-region (e.g.
  `KeyedJoinContract` returning `EndSentinel` with `incomplete_keys`), those locks leak.
  Process exit clears them, so this is not a runtime hazard, but future contract changes
  must preserve the invariant.
- **Single graph instance per process.** The lock registry is process-wide; running two
  graphs concurrently in one process would share locks. The harness runs one graph per
  process so this is moot, but worth recording.

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

## Log idioms per failure site

Each module and contract that can fail records its idiom here. Three idioms are in play, per
`docs/invariants.md:14-23` and `docs/harness/logging.md`:

- **`log.critical`** — immediate `SystemExit(1)`. Reserved for unrecoverable setup/config
  failures and harness-internal scheduling errors.
- **Port-routed `result`** — failure becomes a `result` payload on a dedicated output port,
  routed via `fan-in-results` to `aggregate-results`. Per-test failures use this idiom.
- **`log.error` at emission** — paired with port-routed `result` for every per-test FAIL
  emission site. The deferred-exit flag (`handler.failure`) is set both at emission
  (immediate operator visibility, belt-and-braces against any merge / `finalise()` misfire)
  and again at `aggregate-results.finalise()` (centralised summary record).
- **No log call** — non-failure terminals (SKIP, early-stop) emit a `result` payload for the
  summary table but do not log.

### Setup / config — `log.critical`

| Site | Failure |
|---|---|
| `discover-config-file` | `root_config.yaml` not found walking up CWD |
| `parse-root-config` | malformed YAML / schema mismatch |
| `select-platform` | no platform's `unames` matches |
| `resolve-builder` | named builder missing on platform |
| `check-suite-cwd` | `test_config` resolves outside CWD (parent ≠ CWD) — catches `-c /abs/elsewhere/tests.yaml`, `-c ../sibling/tests.yaml`, `-c subdir/tests.yaml`; also fires if the resolved path is not a file. Not wired in regression (chdir's per-suite) |
| `parse-suite-config` | `tests.yaml` missing/malformed; testbench bind failure |
| `select-tests` | named test not in suite |
| `run-process` | subprocess launch failure (binary not on PATH, permission denied) — distinct from non-zero `rc`, which is per-test |

### Per-test failure — port-routed `result` to merge, `log.error` at emission *and* at aggregate

| Site | Port → payload | Emission log |
|---|---|---|
| `interpret-compile.fail` | `fail` → `CompileFailResults` | `log.error` (compile `rc`, stderr path) |
| `interpret-sim.timeout` | `timeout` → `SimTimeoutResults` | `log.error` (`timed_out`, stderr path) |
| `parse-log.result` (FAIL) | `result` → FAIL payload | `log.error` (parsed reason) |
| `parse-uvm-log.result` (FAIL) | `result` → FAIL payload | `log.error` (severity counts) |
| `load-model.fail` | `fail` → FAIL payload | `log.error` (`models.yaml` path, reason) |
| `write-filelist.fail` | `fail` → FAIL payload | `log.error` (filelist generation reason) |
| `expand-sweep.fail` | `fail` → FAIL payload | `log.error` (sweep script trace) |
| `run-preproc.fail` | `fail` → FAIL payload | `log.error` (preproc script trace) |
| `resolve-seed.fail` (REPLAY only) | `fail` → FAIL payload | `log.error` (missing/malformed `.randseed` path) |

The bottom five rows are **new failure ports** added to modules that previously had only a
success path. Topology consequence: `fan-in-results` now has 13 edge-derived input ports
(up from the original 8). Adding a new terminal source means one new graph edge to
`fan-in` — neither `fan-in-results`' `**inputs` signature nor `aggregate-results`'
`run(self, result)` changes.

### Per-test non-failure terminals — port-routed `result` to merge, **no log call**

| Site | Port → payload |
|---|---|
| `filter-reglvl.skip` | `skip` → `SkipResults` (SKIP is pass-like via `is_pass()`) |
| `early-stop-gate.stop` (×3 instances) | `stop` → `EarlyStopResults` (normal terminal, not a failure) |

### Centralised exit-driver — `log.error` (deferred non-zero exit)

| Site | Trigger | Log call |
|---|---|---|
| `aggregate-results.finalise()` | any accumulated row not `is_pass()` | `log.error("suite_has_failures", n=...)` once |

### Deferred

| Site | Failure | Status |
|---|---|---|
| `parse-log` / `parse-uvm-log` | parse-machinery exception distinct from FAIL classification (log file missing; regex raises on malformed content) | Deferred pending TODO #13 (VlogPost quirks: replicate vs fix) |
