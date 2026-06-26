# Pipeline and contract choices

## Node table

Main-line nodes top to bottom; setup nodes feed config in as **persistent** inputs.

| # | node | module | contract | inputs (work / persistent) |
|---|---|---|---|---|
| S0 | `prepend-path` | `prepend-cwd-path` | `default` | — (zero-input) |
| S1 | `discover-root` | `discover-config-file` | `default` | — (config `filename`) |
| S2 | `parse-root` | `parse-root-config` | `unit` | `path` |
| S3 | `select-platform` | `select-platform` | `unit` | `root_cfg` |
| S4 | `resolve-builder` | `resolve-builder` | `unit` | `root_cfg`, `platform_cfg`; CLI `builder` |
| S4.5 | `work-dir` | `work-dir` | `default` | (zero-input) — emits `work_dir = Path.cwd().resolve()`, the artefact base |
| S4.6 | `ensure-logs` | `ensure-logs-dir` | `unit` | CLI `logs_dir` (name); `work_dir` (from `work-dir`) — emits resolved `logs_dir` Path |
| S5 | `parse-suite` | `parse-suite-config` | `unit` | CLI `test_config` (resolves it against CWD internally) |
| S6 | `seed-mode` | `derive-seed-mode` | `unit` | CLI `rnd_new`,`rnd_last` |
| S7 | `git-status` | `git-status` | `default` | — (zero-input; logs `git_state`) |
| 0 | `route-list` | `route-list-mode` | `unit` | `suite_cfg`; CLI `list` |
| 0a | `list-names` | `list-test-names` | `default` | `suite_cfg` (terminal) |
| 1 | `select` | `select-tests` | `default` | `suite_cfg`; CLI `test_name` |
| 2 | `filter` | `filter-reglvl` | `default` | `test` / `builder_cfg`,`reg_level`,`start_level` |
| 3 | `load-model` | `load-model` | `default` | `test` |
| 4 | `sweep` | `expand-sweep` | `keyed_join` (`key_field: key`) | `test`,`model` / `root_cfg` |
| 5 | `preproc` | `run-preproc` | `keyed_join` (`key_field: key`) | `test`,`model` / `root_cfg` |
| 6 | `gate-pre` | `early-stop-gate` (phase=pre) | `keyed_join` (`key_field: key`) | `test`,`model` / `early_stop` |
| 7 | `filelist` | `write-filelist` | `keyed_join` (`key_field: key`) | `test`,`model` / `work_dir` (writes `run.<tag>.f`) |
| 8 | `cc-build` | `build-compile-cmd` | `keyed_join` (`key_field: key`) | `test`,`filelist` / `builder_cfg`,`builder_mode`,`logs_dir` (Path from `ensure-logs`),`work_dir` |
| 9 | `cc-run` | `run-process` | `default` | `command` / `env_ready` (from `prepend-path`; edge `required: true`, persistent),`work_dir` |
| 10 | `cc-int` | `interpret-compile` | `keyed_join` (`key_field: key`) | `test`,`simv`,`proc` |
| 11 | `gate-comp` | `early-stop-gate` (phase=comp) | `keyed_join` (`key_field: key`) | `test`,`simv` / `early_stop` |
| 12 | `runs` | `expand-runs` | `keyed_join` (`key_field: key`) | `test`,`simv` / `run_ids` |
| 13 | `seed` | `resolve-seed` | `keyed_join` (`key_field: key`) | `test`,`run_id`,`simv` / `seed_mode`,`builder_cfg`,`logs_dir` (Path from `ensure-logs`) |
| 14 | `sim-build` | `build-sim-cmd` | `keyed_join` (`key_field: key`) | `test`,`run_id`,`simv`,`seed` / `builder_cfg`,`builder_mode`,`logs_dir` (Path from `ensure-logs`) |
| 15 | `sim-run` | `run-process` | `keyed_join` (`key_field: key`) | `command`,`timeout` / `env_ready` (from `prepend-path`; edge `required: true`, persistent),`work_dir` |
| 16 | `randseed` | `write-randseed` | `keyed_join` (`key_field: key`) | `randseed`,`proc` (gate) / `work_dir` |
| 17 | `link-latest` | `link-latest` | `keyed_join` (`key_field: key`) | `randseed`,`proc`,`randseed_done` (gate) / `work_dir` |
| 18 | `sim-int` | `interpret-sim` | `keyed_join` (`key_field: key`) | `test`,`proc` |
| 19 | `gate-sim` | `early-stop-gate` (phase=sim) | `keyed_join` (`key_field: key`) | `test`,`proc` / `early_stop` |
| 20 | `route-post` | `route-post` | `keyed_join` (`key_field: key`) | `test`,`proc` |
| 21a | `parse-log` | `parse-log` | `keyed_join` (`key_field: key`) | `test`,`proc` |
| 21b | `parse-uvm-log` | `parse-uvm-log` | `keyed_join` (`key_field: key`) | `test`,`proc` |

> **One `results-summary` row, no relay/agg pair (TODO #15, revised by spec [10d](specs/10d-summarise-results.md)).**
> The former rows 22a (`fan-in`) and 22 (`agg`) are gone. The 13 result ports are **wired** to a
> single `results-summary` node (`contract: any`, `contract_port_mappings`), which renders the summary
> **results** table from the fanned-in `TestResult`s in its `finalise()` hook — the `any` contract is
> the fan-in, so no `fan-in-results` relay is reintroduced. Each terminal also logs a **per-case**
> event (the failure terminals' `compile_failed`/`sim_timeout`/`model_*`/`sweep_*`/`preproc_*`/`filelist_*`/`replay_seed_*`/`parse_*`; the pass-like
> ones at INFO — no generic `test_result`); git state falls through to the console separately. See
> [05 — Re-convergence](05-branching-and-results.md#re-convergence-the-summary-returns-as-a-graph-node).

The same nodes are drawn in the overview's
[combined dataflow diagram](00-overview.md#end-to-end-dataflow-at-a-glance), where edges are
colour- and style-coded by type (main-line / terminal / config / env / CLI) so each can be
traced without conflict. The authoritative edge list is [`06-graph-yaml.md`](06-graph-yaml.md).

Contracts in play: `unit`, `default` (often + `persistent_inputs`), and `keyed_join`
(existing). No bespoke contracts: the former `serial_acquire`/`any.release_lock` parallel-safety
shim was **removed** (TODO #30) in favour of per-tag artefact naming — see
[05 — Interim CWD-collision posture](05-branching-and-results.md#interim-cwd-collision-posture--per-tag-artefact-naming).
The general-purpose `any` contract ([specs/02](specs/02-any-contract-and-fan-in.md)) remains
specified but is **no longer wired** in the `test` graph.

## Why each contract

### `unit` — the run-once nodes
The setup chain (`parse-root` → `select-platform` → `resolve-builder`,
plus `parse-suite` and `ensure-logs`, and `seed-mode`) plus the
list-mode classifier `route-list` each run exactly once via `unit`. `unit` reads one item per port, invokes
once, then returns `EndSentinel` forever. Each of these nodes always receives exactly one value on
every required port, so `unit`'s "`EndSentinel` before data is a `missing_required_inputs` error"
rule never fires for them.

`prepend-path`, `discover-root`, `git-status`, and `work-dir` are zero-input, so they also run exactly once — but that bound comes from having no input ports (the harness stops a node after one invocation when there is nothing to wait for), **not** from the contract. With zero ports `unit` and `default` are identical, so these four use `default`; declaring `unit` there would assert a one-shot guarantee it does not actually supply.

The two env-setup orderings are independent data edges, **not** a chain through `ensure-logs`:

- **PATH prepend** — `prepend-path` emits an `env_ready` token wired directly to
  `cc-run.env_ready` and `sim-run.env_ready`. Each edge is marked **`required: true`** and
  `env_ready` is in each `run-process`'s `persistent_inputs`: `required` suppresses the module's
  Python default so the **first** invocation blocks until the `$PATH` mutation is done (a hard
  dependency), and `persistent` caches the once-emitted token to replay it on the streaming later
  invocations. See [07 settled 25](07-ambiguities-and-assumptions.md).
- **`logs/` `mkdir`** — `ensure-logs` takes `work_dir` from the zero-input `work-dir` provider
  (the artefact base = CWD), `mkdir`s the
  artefact directory, then emits the resolved `logs_dir` `Path`. The composers consume `logs_dir`
  as a first-run-required input (no Python default), so they block on it before building a command;
  because the `mkdir` precedes the emit, the directory provably exists before any subprocess
  redirects into it. No `env_ready` token is needed for the `mkdir`, and `ensure-logs` depends only
  on what it reads (`work_dir`) — a missing edge fails edge-validation rather than silently
  mistargeting.

### `default` — the post-branch run-once nodes (`select`, `list-names`)
`route-list` emits on exactly **one** of its `run`/`list` ports per run, so the *other*
branch's downstream node receives only the `EndSentinel` that the harness broadcasts to every
destination at node end (`node.py` end-of-run propagation). `select` (on `run`) and
`list-names` (on `list`) are therefore each fed an empty stream whenever the other branch is
taken. They use `default`, **not** `unit`, precisely because `default` returns `EndSentinel`
silently when its single required port ends with no data (it only logs `mismatched_end` on a
*partial* end — some required ports with data, others ended), whereas `unit` would log
`missing_required_inputs` (an `ERROR`, which flips the harness failure flag → exit 1) for the
unfired branch. With `default`, a normal run drains `list-names` cleanly and a `--list` run
drains `select` cleanly — neither raises a spurious error, so list-mode exits 0 and a passing
run is not forced to exit 1. Each still runs at most once: `route-list` delivers a single
`suite_cfg`, so the node invokes once and `select`'s generator fans out all tests from that one
invocation. `select`'s `test_name` is a CLI edge (`has_default`, so non-blocking); it is
delivered at startup, ahead of the `suite_cfg` that traverses the whole setup + `route-list`
chain, so the contract's non-blocking read always sees it.

### `default` (+ `persistent_inputs`) — the single-work-edge stages
Under the split-edge model a stage uses `default` only when it consumes **exactly one** keyed
work edge plus cached config: `filter` and `load-model` (one `test` edge) and `cc-run` (one
`command` edge). The config nodes emit once at start; listing their ports in `persistent_inputs`
caches the first value and replays it for every item — the documented "enrich each item with a
slowly-changing config" pattern. A stage that consumes **two or more** keyed work edges does
**not** use `default`: with the `ctx`/`test_run`/`sim_cmd` bags dissolved into independent
per-field edges (`test`/`model`/`simv`/`filelist`/`seed`/`run_id`/`timeout`/`proc`), those edges
are paced independently, so positional pairing is unsafe and every such node uses `keyed_join` on
`key` (below). This is why all the multi-input main-line nodes are joins, not just the
run-process (`proc`) convergence points.

### `keyed_join` — pairing independent keyed edges
With the bags split, `keyed_join` on `key` is the norm rather than the exception: every node
consuming ≥2 keyed work edges uses it. Two distinct reasons drive it:

1. **Edge re-pairing.** Edges that once rode a single `ctx`/`test_run` bag are now independent —
   `sweep`/`preproc`/`gate-pre` join `test`+`model`, `filelist` joins `test`+`model`, `cc-build`
   joins `test`+`filelist`, `gate-comp` joins `test`+`simv`, `runs` joins `test`+`simv`, `seed`
   joins `test`+`run_id`+`simv`, `sim-build` joins `test`+`run_id`+`simv`+`seed`, and `sim-run`
   joins `command`+`timeout`. They may originate together, but as separate edges paced
   independently the harness can't pair them positionally, so they are matched by `key`.
2. **Fast/slow subprocess convergence.** `cc-int` and the post-sim nodes (`randseed`, `sim-int`,
   `route-post`, `parse-log`/`parse-uvm-log`) combine a fast path with the **independently-paced
   `proc`** stream that `run-process` (`cc-run`/`sim-run`) emits. Under concurrency `proc` reorders
   relative to the fast path across tests, so positional pairing is outright wrong; `keyed_join`
   buffers and matches by `key`.

`cc-int` takes three keyed ports: `test`, `simv` (set by `build-compile-cmd`), and `proc`
(from `cc-run`). On `ok` it forwards `test`+`simv` unchanged — `simv` is already present and
requires no re-derivation downstream.

`randseed` (write-randseed) takes two keyed ports: `randseed` (the cohesive seed message from
`sim-build`) and `proc` (from `sim-run`, joined only as a completion gate). It is a
**side-effect leaf** — it writes the `.randseed` record and emits a `randseed_done` ordering
signal; there is **no `test_run` assembly** (the post-sim bag is dissolved). Post-sim is two
parallel branches off `proc`: the side-effect branch (`write-randseed` → `link-latest`,
sequenced by `randseed_done`) and the classification branch (`interpret-sim` → `gate-sim` →
`route-post` → `parse-log`/`parse-uvm-log`), where each classification node `keyed_join`s
`test` + `proc` by key.

The `.log`/`.err` files are written by `run-process` itself (redirect, paths supplied in
`command`) — there is no separate "write logs" node.

### Interim CWD-collision posture — per-tag naming (no contract)
There is no parallel-safety contract. Instead `write-filelist` names its filelist
`run.<tag>.f` (and `build-compile-cmd` already derives per-tag `obj_dir`/verilator-`simv`/log
paths), so concurrent tests don't collide on shared CWD filenames and the compile/sim region
stays genuinely concurrent. The former `serial_acquire`/`any.release_lock` lock shim was
removed (TODO #30). This per-tag naming is an **interim graph-local subset** of the upstream
per-invocation-subdir change ([07](07-ambiguities-and-assumptions.md) item 17), which remains
the reference fix for the residual it cannot name (non-verilator `simv`, `test.*` symlinks,
tool-internal CWD files). Detail in
[05 — Interim CWD-collision posture](05-branching-and-results.md#interim-cwd-collision-posture--per-tag-artefact-naming).

### Re-convergence — the `results-summary` node
The 13 mutually-exclusive terminal-result branches re-converge at one `results-summary` node
(spec [10d](specs/10d-summarise-results.md)), fanned in by the `any` contract: each emits its
`TestResult` (the summary row) and logs a per-case event at origin (failure terminals at
`log.error`; the pass-like outcomes are recorded by their `TestResult` alone). `results-summary.finalise()`
renders the table and emits the consolidated `test_failures` error on any FAIL row. The `any`
contract is the fan-in itself — the old `fan-in-results` relay + `aggregate-results` sink is **not**
reintroduced. Details in
[05 — Re-convergence](05-branching-and-results.md#re-convergence-the-summary-returns-as-a-graph-node)
and [specs/10](idx-10-control-aggregate.md).

## Fan-out points

`select` (suite → N tests), `sweep` (1 test → M variants), `runs` (1 compiled test → R
runs) are generator modules. Total terminal results = `N×M×R` `TestResult` rows fanned into
`results-summary`, matching the row count `rtl_buddy` would print. A test that fails compile
is sealed at `cc-int.fail` *before* `runs`, so it yields exactly one result, not R — no
special-casing needed, because the failed item simply never enters the run fan-out.

## Persistent / fan-out wiring summary

One output may feed many destinations (output fan-out is allowed; the single-source rule
constrains *input* ports only). Config broadcasts:

- setup chain: `discover-root` → `parse-root` → `select-platform` → `resolve-builder`
- env setup: `prepend-path` → `cc-run.env_ready`, `sim-run.env_ready` (direct token, each edge
  `required: true` with `env_ready` persistent on the consumer); the zero-input `work-dir` node
  (`work_dir = Path.cwd().resolve()`) fans out to `ensure-logs`, `filelist`, `cc-build`, `cc-run`,
  `sim-run`, `randseed`, `link-latest` (persistent base-dir fan-out: `filelist` roots `run.<tag>.f`,
  `cc-build` roots `obj_dir_<tag>/`, `cc-run`/`sim-run` use it as the subprocess `cwd`, `randseed`
  reads `HierInstanceSeed.txt` from it, `link-latest` places the `test.*` symlinks under it).
  `ensure-logs` carries no `env_ready` — its `mkdir` is ordered by the `logs_dir` data edge below.
- `parse-root.root_cfg` → `select-platform`, `resolve-builder` (`unit`); `sweep`, `preproc` (persistent)
- `resolve-builder.builder_cfg` → `filter`, `cc-build`, `seed`, `sim-build` (persistent)
- `parse-suite.suite_cfg` → `route-list`; `route-list.run` → `select`, `route-list.list` → `list-names`
- `seed-mode.default` → `seed.seed_mode`
- CLI `early_stop` → `gate-pre`, `gate-comp`, `gate-sim`
- CLI `builder_mode` → `cc-build`, `sim-build`
- CLI `logs_dir` (subdir name) → `ensure-logs` only; the **resolved** `logs_dir` Path
  `ensure-logs.logs_dir` → `cc-build`, `sim-build`, `seed` (persistent on the three main-line
  composers). Artefact location is decided once (`work-dir.work_dir` = CWD) and flows as data.

## Liveness / termination

Every node propagates `EndSentinel` (handled by the chosen contracts: `unit` after its run;
`default`/`keyed_join` when a required port ends; `any` when all 13 fanned-in ports end). The
13 terminal result ports converge on the `results-summary` sink, so the graph is a DAG that
fans **in** to one sink (plus `git-status`, whose log-only `default` port stays unwired).
`graph.py` gathers every node coroutine via `asyncio.gather`, so when `select` ends the
sentinel cascades through every branch; the `any` contract returns `EndSentinel` once all 13
result ports end, and `results-summary.finalise()` then renders the table and emits the
consolidated `test_failures` error — the per-run teardown the harness invokes after the gather
(before the failure check). No cycles, so `validation.py`'s acyclicity/deadlock checks pass.
