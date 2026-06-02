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
contract. Semantics: *forward the next item from any contract-side input port to its
mapped module-side output port; end when all input ports have ended.* The mapping is set
by `Config.fan_in`, supporting M-N fan-in:

- **String form** (`fan_in: "out"`) — N→1 shorthand: every contract-declared input port
  fans in to the single output port `out` (which is a module parameter).
- **Dict form** (`fan_in: {out1: [in1, in2], out2: [in3, in4]}`) — explicit M-N. Each
  entry names one output port (a module parameter) and the list of contract-declared
  input ports that deliver under it.

The contract returns `{output_port: payload}` (one entry per call). For
`aggregate-results`, the output port is `result` — the only parameter on `run()`. The 13
upstream terminals wire to **contract-side** input ports (`skip`, `es_pre`, …,
`seed_fail`), not module parameters; the module sees only the collapsed `result` stream.

> **Harness prerequisite.** This design requires the harness to support
> *contract-declared input ports* — ports the contract introduces independently of the
> module's `run()` signature. Today's implementation (`src/rtl_comrade/node.py:122`)
> builds the node's port set strictly from module parameters, so the contract cannot
> introduce additional ports. The user is owning that change; the spec below is written
> against the post-change harness.

```python
@dataclass
class MergeContract:
    """Non-correlating M-N fan-in: contract-side inputs deliver to module-side outputs; end when all inputs end."""

    @dataclass(frozen=True)
    class Config:
        # Either a single module output-port name (all contract-declared inputs fan into it),
        # or {output_port: [input_ports...]} mapping module outputs to contract-side inputs.
        fan_in: dict[str, list[str]] | str
        release_lock: str | None = None

    id: str
    ports: dict[str, ContractPort]    # union of module input ports and contract-declared input ports
    config: Config
    _port_map: dict[str, str] = field(default_factory=dict, init=False, repr=False)
    _pending: dict[str, asyncio.Task] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self):
        # `_port_map` maps contract-side input port → module-side output port.
        # Validation of fan_in against self.ports surfaces misconfiguration as log.fatal.
        # (See the spec for the enumerated rules — the implementation owns the harness
        # interaction for distinguishing input ports from module-side output ports.)
        ...

    async def get_inputs(self) -> dict[str, Payload] | EndSentinel:
        for name in self._port_map:                                   # listen only on input ports
            port = self.ports[name]
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
                    continue                                          # that input closed; others may still run
                if self.config.release_lock is not None:
                    _get_lock(self.config.release_lock).release()
                return { self._port_map[name]: val }                  # delivered under the mapped module-output name

        return EndSentinel(self.id)
```

### Invariants and termination

The properties downstream specs (`aggregate-results`, the serialising shim) depend on:

- **Two port surfaces.** The node has a *module-side* surface (parameters on `run()`) and
  a *contract-side* surface (input ports declared by the contract's `Config`). Graph
  edges wire into contract-side input ports; the module sees only deliveries under its
  declared parameter names. `MergeContract` consumes from contract-side inputs and emits
  on module-side outputs, mediated by `Config.fan_in`. The exact harness mechanism for
  declaring contract-side ports is owned by the harness change called out as a
  prerequisite above; this spec assumes it is in place.
- **State held across calls.** `_port_map: dict[str, str]` (frozen after `__post_init__`)
  maps each contract-side input port to its module-side output port. `_pending: dict[str,
  asyncio.Task]` carries one in-flight `port.get()` task per *input* port that has not
  yet emitted `EndSentinel`. Tasks created in call N but not consumed by call N's return
  remain in `_pending` and are honoured in call N+1. Output ports are delivery-only —
  the contract never reads them.
- **Construction-time validation.** `__post_init__` validates `fan_in` against
  `self.ports`: every output port named must correspond to a module parameter, every
  input port named must be a contract-declared port, no input port appears in more than
  one output's list, no port is both an input and an output (in the dict form), and no
  declared contract-side input is left unmapped. Failures call `log.fatal`
  (misconfiguration is unrecoverable; immediate `SystemExit(1)`).
- **No-loss invariant.** `asyncio.wait(..., FIRST_COMPLETED)` may report several `done`
  tasks in one wake-up. The contract returns the first non-`EndSentinel` payload found
  and leaves the remaining `done` tasks in `_pending`; on the next call, `asyncio.wait`
  returns them immediately (already-completed). Pending tasks are **never cancelled**
  between calls.
- **Per-port `EndSentinel` handling.** When an input port's task resolves to
  `EndSentinel`, the task is removed from `_pending` and **no new task is created** for
  that port (`port.has_ended()` is now `True`). Other input ports keep being awaited.
- **Drainage order.** An input port's payloads queued before its `EndSentinel` are
  delivered first, by FIFO at the port plus the upstream invariant that `EndSentinel` is
  propagated only after every payload has been enqueued.
- **Non-correlating; no input-port identity surfaced.** Merge does **not** inspect or
  correlate payload contents, **and does not surface contract-side input-port identity to
  the module** — each delivered payload arrives under the module output port its source
  input is mapped to in `Config.fan_in`. The "each test reaches exactly one terminal
  input" property is enforced by the graph topology (gates, routers, single-port emits),
  **not** by this contract. If two inputs sharing an output port both emit a payload for
  the same upstream key (invariant violation), merge delivers both; the consumer would
  record duplicate rows. Detection belongs upstream.
- **Termination rule.** `get_inputs()` returns `EndSentinel(self.id)` exactly when every
  contract-side input port has emitted its `EndSentinel` **and** every previously-pending
  task has resolved — i.e. `_pending` is empty and no new tasks can be created. The outer
  `while self._pending` guarantees this. Output ports are not consulted for termination.
- **`release_lock` side-effect (when configured, per
  [Serialising contracts](#serialising-contracts--interim-parallel-safety-posture)).**
  Fires once immediately before the `return { ...: val }` line — one release per delivered
  payload. The `EndSentinel` paths (the `continue` after an end, and the final terminal
  return) do **not** release. If `release_lock` names a lock that no upstream
  `serial_acquire` ever held, `asyncio.Lock.release()` raises `RuntimeError` on the first
  payload — fail-fast misconfiguration, no protective guard.
- **Cancellation.** If the harness cancels the node task mid-`get_inputs`, pending tasks are
  cancelled by the event loop. Items in flight in those tasks are lost. This is process-end
  behaviour and matches every other contract.

Notes:

- `merge` is broadly reusable: any "collect results from alternative branches" fan-in.
  Register it in the contracts manifest (see [06](06-graph-yaml.md)).
- This is the one piece of genuine scheduling the design adds (excluding the interim
  serialising shim above), and it lives where the framework wants scheduling — in a
  contract, not in a module.

## Serialising contracts — interim parallel-safety posture

> **Temporary measure.** The serialising contracts described in this section exist *only*
> until the upstream `rtl_buddy` change to per-test (per-invocation) artefact directories
> lands. Once compile/sim each get their own working directory, the collisions these
> contracts protect against (next compile stomping the previous test's `obj_dir`, `simv`,
> `run.f`) disappear, and `write-filelist` returns to plain `default` while `aggregate-results`
> returns to plain `merge`. See [07](07-ambiguities-and-assumptions.md) item 17. Do not build
> further design on top of these contracts; treat them as a removable shim.

### The hazard

A compile produces non-graph-routed artefacts in CWD (`obj_dir_<tag>/`, the `simv` binary,
and `run.f`) that the *same test's* sim later consumes. The harness launches all node tasks
concurrently (`asyncio.gather`), so absent any serialisation a second compile can start while
a previous test's sim has not yet read those artefacts, and stomp them. `cc-int` carries the
`simv` path forward in `ctx` to `sim-build`/`sim-run`, but the file on disk that the path
refers to is shared. The lock makes this region atomic per test.

### Region and lock semantics

- **Region**: from `write-filelist`'s invocation through `aggregate-results`' receipt of that
  test's terminal result.
- **Atomicity unit**: one (test, sweep-variant). For the plain `test` graph `expand-runs`
  defaults to `[None]` (R=1) so each acquire matches exactly one merge release; sibling
  graphs with R>1 (`randtest`) cannot use this design as-is — see Constraints below.
- **Lock object**: a single process-wide `asyncio.Lock` per `lock_name`. The plain `test`
  graph uses one lock named `compile-sim`.

### Two contracts share one lock

The acquire side is a new contract `serial_acquire` annotated on `write-filelist`. The
release side is the existing `merge` contract on `aggregate-results`, extended with an
optional `release_lock` config field. Both contracts live in the same plugin file so they
share a module-level lock registry:

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

The release side is the `MergeContract`'s built-in `Config.release_lock` field (sketch in
[Re-convergence](#re-convergence-the-custom-merge-contract)). On every `get_inputs()` call
that returns one `{output_port: payload}`, the contract releases the named lock once.
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
  `seed.fail`, the four pre-region `*.fail` ports that also route into `agg`) still reaches
  `agg` via the `merge` contract; the release fires uniformly on every port.

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
  fanned into `aggregate-results` via `MergeContract`. Per-test failures use this idiom.
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
| `MergeContract` | internal scheduling error |

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
success path. Topology consequence: the `MergeContract` fan-in into `aggregate-results`
grows from 8 contract-side input ports to 13. [04](04-pipeline-and-contracts.md) row 22
and the merge edge list in [06](06-graph-yaml.md) need to be updated to reflect this. The
module's `run()` signature is unchanged — still just `run(self, result)` — because the
new input ports live on the contract side; only `Config.fan_in`'s input list grows.

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
