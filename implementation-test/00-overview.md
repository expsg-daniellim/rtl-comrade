# Overview

## Goal

Reproduce the behaviour of `rtl_buddy test` as an `rtl-comrade` graph.

`rtl_buddy test` (traced from `rtl_buddy/src/rtl_buddy/`) does, in one sequential
in-process pass:

1. load `root_config.yaml` (walk up the tree, pick a platform by `uname`, resolve a builder)
2. load the suite `tests.yaml` (and each test's `models.yaml` + testbenches)
3. select one test or all tests
4. (regression only) filter tests by regression level
5. expand each test through an optional `sweep` script into N variants
6. for each test: run an optional `preproc` script, write a filelist (`run.f`), compile
7. for each run-id: resolve a seed, simulate (with timeout), parse the log into a result
8. aggregate all results, print a summary, exit `0` iff every result is PASS/SKIP

The whole thing is sequential, mutation-heavy, and short-circuits on the first failure
of each test (compile fail → no sim; timeout → no post; `--early-stop` → stop at a phase).

## Design philosophy

1. **Phases are tags, not structure.** `pre`/`compile`/`sim`/`post` are labels on the
   modules that happen to do that kind of work, not structural boundaries. The real unit
   is the smallest piece of node-local work.

2. **Atomic modules; coordination in contracts.** Every module declares exactly the inputs
   it consumes as **granular named ports** the harness can see and validate, does its work,
   and emits named outputs. Modules contain **no scheduling** — no "should I run", no
   passthrough guards, no awareness of the graph. *All* coordination (when a node runs,
   which inputs are matched, how branches re-converge) lives in contracts, and **we author
   the contracts the design needs** — contracts are plugins, not framework internals.

3. **Branching is data routing via output ports; re-convergence is a contract.** A stage
   that produces a terminal outcome (skip, early-stop, compile-fail, timeout, parsed result)
   emits it on a dedicated output port that routes the item *off the main line* to the
   result collector. Items that continue stay on the main line. Because terminal items
   leave, downstream stages never see them — which is why no module needs a guard. The
   collector fans the mutually-exclusive terminal ports back in with a small **custom
   `merge` contract** (the built-in joins can't express mutually-exclusive exits; see
   [05](05-branching-and-results.md)).

4. **`compile` and `sim` are one reusable module.** `run-process` — `run(self, command,
   timeout=None) -> {rc, timed_out, stdout_path, stderr_path}` — is the single subprocess
   primitive, wired twice. It **redirects** stdout/stderr to caller-supplied files (paths in
   `command`), so partial output survives a timeout and memory stays bounded.

5. **Reimplement rtl_buddy, preserve only the config surface.** Modules reimplement
   `rtl_buddy`'s behaviour natively rather than wrapping its classes; only the config-file
   schema (`root_config.yaml`, `tests.yaml`, `models.yaml` field names/structure) is kept
   identical, so existing config files run drop-in. This is what frees the monolithic
   `RootConfig`/`SuiteConfig` loaders to be split into atomic nodes (`discover-config-file`,
   `parse-root-config`, `select-platform`, `resolve-builder`, `parse-suite-config`,
   `load-model`). See [07](07-ambiguities-and-assumptions.md) item 1.

## Correlation: a minimal context record + joins only where streams diverge

With no god-object carrying everything, a stage needs its inputs *matched up* under
concurrency. The chosen strategy (see [02](02-payload-conventions.md)):

- A minimal **`ctx` record** `{key, test}` rides the main line and is forwarded
  stage-to-stage, because nearly every stage needs the test config. `simv` is folded into
  `ctx` after compile (every run of that test needs it). `ctx` never carries derived or
  transient values (`argv`, `rc`, `stdout`, `log`, and crucially no `result`).
- A stable **correlation key** is stamped at each fan-out (`select`→`name`,
  `sweep`→`name#i`, `runs`→`name#i#run`).
- **Joins happen only where a fast path meets a slow path**: the direct `ctx` edge meets
  the subprocess `proc` result at `interpret-compile` and `write-randseed` (the first sim-side
  node needing both). Those two nodes use `keyed_join` on the key. Everywhere else, a stage's
  inputs come from a single upstream in lockstep, so a plain `default` contract suffices.

This is the explicit difference from the rejected single-envelope design: `ctx` is a
*minimal, bounded* record of genuinely-pervasive values (not an accumulator), modules read
only the ports they declare, and no module contains scheduling.

## End-to-end dataflow at a glance

```
 CLI edges ──────────────────────────────────────────────────────────────────────────────┐
 (test_config, test_name, list, rnd_new/rnd_last, builder, builder_mode, early_stop)        │
                                                                                            │
 discover-root→parse-root→select-platform→resolve-builder ─► builder_cfg ─ persistent ────┐ │
 parse-root ─► root_cfg (persistent) ;  seed-mode ─► seed_mode                            │ │
 parse-suite ─► suite_cfg ─► route-list ──list──► list-names (prints names; exit 0)       │ │
        │                                                                                 │ │
        ▼  MAIN LINE carries ctx = {key, test (+simv after compile)}                      │ │
 route-list ──run──► select (unit, FAN-OUT) ─► ctx per test                              │ │
        ▼                                                                                 │ │
 filter ──keep──► load-model ─► ┐   └──skip───────────────────────────────────────────┐  │ │
        ▼                       │                                                       │  │ │
 sweep (FAN-OUT)                │                                                       │  │ │
        ▼         │                                                                    │   │ │
 preproc ◄─ root_cfg                                                                   │   │ │
        ▼         │                                                                    │   │ │
 gate-pre ──go──► ┤         └──stop───────────────────────────────────────────────►   │   │ │
        ▼         │                                                                  M │   │ │
 filelist ─► (ctx, filelist)                                                         E │   │ │
        ▼         │                                                                  R │   │ │
 cc-build ◄─ builder_cfg ─► ctx(+simv) ───────┐  + argv ─► cc-run (run-process)       G │   │ │
        │                                     │                  │ proc{key,rc,...}   E │   │ │
        └─────────────────────────────────────┴──► cc-int (keyed_join ctx⋈proc)      │   │ │
                                          ok ─► ctx          fail ──────────────────► ┤   │ │
        ▼                                                                             │   │ │
 gate-comp ──go──► ┤         └──stop──────────────────────────────────────────────►  │   │ │
        ▼          │                                                                  │   │ │
 runs (FAN-OUT per run-id) ◄─ run_ids                                                 │   │ │
        ▼          │                                                                  │   │ │
 resolve-seed ◄─ seed_mode, builder_cfg ─► (ctx, seed)                                │   │ │
        ▼          │                                                                  │   │ │
 sim-build ◄─ builder_cfg ─► ctx ────────────┐  + command{argv,log paths} ─► sim-run (run-process: redirects to .log/.err)│
        │                                     │                                │ proc{key,rc,paths}│ │
        └─────────────────────────────────────┴─► randseed (keyed_join; writes .randseed) ─► link-latest (symlinks) ─► interpret-sim
                                          ok ─► ctx          timeout ───────────────► ┤   │ │
        ▼          │                                                                  │   │ │
 gate-sim ──go──► ┤         └──stop───────────────────────────────────────────────►  │   │ │
        ▼                                                                             │   │ │
 route-post ─uvm─► parse-uvm-log ─► {key, result} ──────────────────────────────────►┤   │ │
           └plain► parse-log ─────► {key, result} ──────────────────────────────────►┘   │ │
                                                                                          │ │
 aggregate-results (merge contract + finalise) ◄── all terminal ports ───────────────────┘ │
        └─► summary; log.error on any non-pass → exit 1                                     │
                                                                                            │
 (persistent config fans out from parse-root / resolve-builder / seed-mode / CLI to nodes above)┘
```

`select`, `sweep`, and `runs` are the only fan-out points (generators). `cc-int` and
`randseed` are the only joins. The collector is the only fan-in (the `merge` contract).
Everything else is single-input/single-output with a plain `default` contract.

## Why this maps cleanly

| rtl_buddy concept | rtl-comrade realisation |
|---|---|
| `RtlBuddy` + `TestRunner` orchestration & loops | graph topology + contracts |
| nested `for test / for run_id` loops | fan-out generator modules (`select`, `sweep`, `runs`) |
| early `return CompileFailResults` etc. | named output port routes the item off the main line |
| `--early-stop` phase truncation | `early-stop-gate` nodes emitting on `stop` |
| compile vs sim | one reusable `run-process` module + two command builders |
| matching async results to their test | `keyed_join` on the correlation key at `cc-int`/`randseed` |
| collecting all outcomes | the custom `merge` contract on `aggregate-results` |
| OR-accumulated exit code | `aggregate-results.finalise()` → `log.error` (harness maps ERROR → exit 1) |
| `RootConfig`/`SuiteConfig` monolithic loaders | reimplemented as atomic setup nodes; config schema preserved |
