# Pipeline and contract choices

## Node table

Main-line nodes top to bottom; setup nodes feed config in as **persistent** inputs.

| # | node | module | contract | inputs (work / persistent) |
|---|---|---|---|---|
| S1 | `discover-root` | `discover-config-file` | `unit` | — (config `filename`) |
| S2 | `parse-root` | `parse-root-config` | `unit` | `path` |
| S3 | `select-platform` | `select-platform` | `unit` | `root_cfg` |
| S4 | `resolve-builder` | `resolve-builder` | `unit` | `platform_cfg`; CLI `builder` |
| S5 | `parse-suite` | `parse-suite-config` | `unit` | CLI `test_config` |
| S6 | `seed-mode` | `derive-seed-mode` | `unit` | CLI `rnd_new`,`rnd_last` |
| 0 | `route-list` | `route-list-mode` | `unit` | `suite_cfg`; CLI `list` |
| 0a | `list-names` | `list-test-names` | `unit` | `suite_cfg` (terminal) |
| 1 | `select` | `select-tests` | `unit` | `suite_cfg`; CLI `test_name` |
| 2 | `filter` | `filter-reglvl` | `default` | `ctx` / `builder_cfg`,`reg_level`,`start_level` |
| 3 | `load-model` | `load-model` | `default` | `ctx` |
| 4 | `sweep` | `expand-sweep` | `default` | `ctx` / `root_cfg` |
| 5 | `preproc` | `run-preproc` | `default` | `ctx` / `root_cfg` |
| 6 | `gate-pre` | `early-stop-gate` (phase=pre) | `default` | `ctx` / `early_stop` |
| 7 | `filelist` | `write-filelist` | `default` | `ctx` |
| 8 | `cc-build` | `build-compile-cmd` | `default` | `ctx`,`filelist` / `builder_cfg`,`builder_mode` |
| 9 | `cc-run` | `run-process` | `default` | `command` |
| 10 | `cc-int` | `interpret-compile` | `keyed_join` (`key_field: key`) | `ctx`,`proc` |
| 11 | `gate-comp` | `early-stop-gate` (phase=comp) | `default` | `ctx` / `early_stop` |
| 12 | `runs` | `expand-runs` | `default` | `ctx` / `run_ids` |
| 13 | `seed` | `resolve-seed` | `default` | `ctx` / `seed_mode`,`builder_cfg` |
| 14 | `sim-build` | `build-sim-cmd` | `default` | `ctx`,`seed` / `builder_cfg`,`builder_mode` |
| 15 | `sim-run` | `run-process` | `default` | `command`,`timeout` |
| 16 | `randseed` | `write-randseed` | `keyed_join` (`key_field: key`) | `ctx`,`proc` |
| 17 | `link-latest` | `link-latest` | `default` | `ctx` |
| 18 | `sim-int` | `interpret-sim` | `default` | `ctx` |
| 19 | `gate-sim` | `early-stop-gate` (phase=sim) | `default` | `ctx` / `early_stop` |
| 20 | `route-post` | `route-post` | `default` | `ctx` |
| 21a | `parse-log` | `parse-log` | `default` | `ctx` |
| 21b | `parse-uvm-log` | `parse-uvm-log` | `default` | `ctx` |
| 22 | `agg` | `aggregate-results` | **`merge`** + `finalise()` | 8 terminal-result ports |

Contracts in play: `unit`, `default` (often + `persistent_inputs`), `keyed_join`
(existing), and `merge` (**new** — authored for this graph; specified in
[05](05-branching-and-results.md)).

## Why each contract

### `unit` — the run-once nodes
The setup chain (`discover-root` → `parse-root` → `select-platform` → `resolve-builder`,
plus `parse-suite`, `seed-mode`) and the selection front (`route-list`, `list-names`,
`select`) each run exactly once. `unit` reads one item per port, invokes once, then returns
`EndSentinel` forever. `select`'s generator fans out all tests from that single invocation.
`discover-root` is zero-input, which also runs once.

### `default` (+ `persistent_inputs`) — the linear stages
Most stages take exactly one work payload (`ctx`, or `command`) plus cached config. The
config nodes emit once at start; listing those ports in `persistent_inputs` caches the
first value and replays it for every item — the documented "enrich each item with a
slowly-changing config" pattern. **Crucially, where a stage has two *work* inputs they come
from a single upstream in lockstep** (`cc-build` ← `filelist`+`ctx` from `write-filelist`;
`sim-build` ← `ctx`+`seed` from `resolve-seed`), so `default` pairs them correctly without
any key. This is why only two nodes need a real join.

### `keyed_join` — the two subprocess convergence points
`cc-int` and `randseed` each combine a **fast** input (`ctx`, routed directly from the
command builder) with a **slow** input (`proc`, from `run-process` after a subprocess). Under
concurrency the `proc` stream reorders relative to `ctx` across tests, so positional pairing
is wrong. `keyed_join` on `key` buffers and matches them. These are the *only* places two
independently-paced streams meet. (`randseed` is the sim-side join because it is the first
node that needs both `proc` and `ctx`; `link-latest` and `interpret-sim` follow it as
single-source `default`. The `.log`/`.err` files are written by `run-process` itself, so
there is no separate "write logs" node — the runner is the writer.) Both join nodes take
**exactly two keyed ports** — config the downstream nodes would otherwise need (the `simv`
path, the `seed`/`log` paths) is folded into `ctx` by the command builders upstream, because
`keyed_join` joins *every* port by key and so cannot also carry a persistent config port.

### `merge` — the single fan-in
`agg` collects mutually-exclusive terminal results from 8 source ports (`route-post` splits
the post path into `parse-log` and `parse-uvm-log`, each a terminal source). `branch_aware_join`
cannot express this (a given key reaches only one port; the others never produce it). The
custom `merge` contract forwards items from whichever port has one and ends when all end.
Details and a sketch in [05](05-branching-and-results.md).

## Fan-out points

`select` (suite → N tests), `sweep` (1 test → M variants), `runs` (1 compiled test → R
runs) are generator modules. Total terminal results reaching `agg` = `N×M×R`, matching the
row count `rtl_buddy` would print. A test that fails compile is sealed at `cc-int.fail`
*before* `runs`, so it yields exactly one result, not R — no special-casing needed, because
the failed item simply never enters the run fan-out.

## Persistent / fan-out wiring summary

One output may feed many destinations (output fan-out is allowed; the single-source rule
constrains *input* ports only). Config broadcasts:

- setup chain: `discover-root` → `parse-root` → `select-platform` → `resolve-builder`
- `parse-root.root_cfg` → `sweep`, `preproc` (persistent)
- `resolve-builder.builder_cfg` → `filter`, `cc-build`, `seed`, `sim-build` (persistent)
- `parse-suite.suite_cfg` → `route-list`; `route-list.run` → `select`, `route-list.list` → `list-names`
- `seed-mode.default` → `seed.seed_mode`
- CLI `early_stop` → `gate-pre`, `gate-comp`, `gate-sim`
- CLI `builder_mode` → `cc-build`, `sim-build`

## Liveness / termination

Every node propagates `EndSentinel` (handled by the chosen contracts: `unit` after its run;
`default`/`keyed_join` when a required port ends; `merge` when all ports end). The graph is
a DAG with a single sink (`agg`), so when `select` ends the sentinel cascades through every
branch — including the terminal ports into `agg` — and `agg.finalise()` fires once. No
cycles, so `validation.py`'s acyclicity/deadlock checks pass.
