# Spec 08: Sim-cycle modules

**Depends on:** spec 03 (run-process), spec 07 (compile cycle).
**References:** [03 — Run expansion + Simulation sections](../03-module-catalog.md), [04 — keyed_join paragraph](../04-pipeline-and-contracts.md).

## Goal

Build the per-run simulate leg: fan out per run-id, resolve the seed, assemble the sim
argv (with log paths in `command` and `seed`/`log` folded into `ctx`), run the subprocess,
then write `.randseed` (the second keyed_join), force the `test.*` symlinks, and route
on timeout.

## Deliverables

In `modules/rtl_test/sim.py`:

- `ExpandRunsMod` — `(ctx, run_ids:list=[None])` → generator yielding one `ctx` per
  `run_id` (key suffixed `#run`, `run_id` recorded in `ctx`).
- `ResolveSeedMod` — `(ctx, seed_mode, builder_cfg)` → integrated seed-producer for all
  three modes:
  - `NEW` → `random.randrange(1_000_000)`
  - `DEFAULT` → `builder_cfg.get_seed()`
  - `REPLAY` → reads `logs/<test>[_NNNN].randseed` (uses `ctx["run_id"]` for the
    suffix); on missing/invalid file, emit a `result` envelope with `SimTimeoutResults`-
    style FAIL? — actually per [03] writes a FAIL stub log + symlinks (verify against
    rtl_buddy `VlogSim.execute` REPLAY-missing path).
  Emits in lockstep: `("ctx", ctx)`, `("seed", {"key", "seed"})`.
- `BuildSimCmdMod` — `(ctx, seed, builder_cfg, builder_mode)` → assembles
  `[simv] + run_time_opts(mode, seed) + plusdefines + plusargs`; computes timeout from
  `test.get_timeout()` and log paths `logs/<test>[_NNNN].log`/`.err`. Emits in lockstep:
  `("ctx", ctx_with_seed_and_log)`, `("command", {"key", "argv", "stdout_path", "stderr_path"})`,
  `("timeout", float | None)`.
- `WriteRandseedMod` — `(ctx, proc)`, with `keyed_join` contract on the node; writes
  `logs/<test>[_NNNN].randseed` from `ctx["seed"]` (+ `HierInstanceSeed.txt` contents if
  present); folds `rc`/`timed_out` from `proc` into `ctx`; emits `ctx`.
- `LinkLatestMod` — `(ctx)` → force CWD symlinks `test.log`/`test.err`/`test.randseed`
  to this run's files (in `logs/`); emits `ctx`.
- `InterpretSimMod` — `(ctx)` → pure routing: `ctx["timed_out"]` → `("timeout",
  {"key", "result": SimTimeoutResults()})`, else `("ok", ctx)`.

Manifest entries per [06](../06-graph-yaml.md).

Tests in `modules/tests/test_sim_cycle.py`:
- `expand-runs` defaults `[None]` → single passthrough; explicit `[1,2,3]` → 3 ctxs with
  correct keys.
- `resolve-seed` covers all three modes; REPLAY round-trips a written `.randseed`.
- `build-sim-cmd` argv matches rtl_buddy `VlogSim.execute`; timeout pulled from test
  config.
- `write-randseed` writes correct file; `link-latest` forces symlinks atomically (use
  `os.replace` or unlink+symlink ordering); `interpret-sim` routes timeout-vs-ok.

## Acceptance criteria

- Tests pass.
- End-to-end against a real `simv` (or fake): a passing run produces correct log/err/
  randseed files and symlinks; a sleep-and-timeout run produces `rc=4444` and
  `interpret-sim` emits `timeout`.

## Notes

`write-randseed` is the **second** `keyed_join` node (the sim-side join). It holds the
join because it's the first node needing both `ctx` (for the seed) and `proc` (for the
completion signal + rc). `link-latest` and `interpret-sim` are downstream single-source
`default` nodes; no further joins. Mirror [04 — Why each contract](../04-pipeline-and-contracts.md).
