# Spec 08b: resolve-seed (`ResolveSeedMod`)

**Depends on:** spec 03 (run-process), spec [01a](01a-builder-schema.md)
(`ResolveSeedMod` consumes `RtlBuilderConfig.get_seed()`).
**References:** [03 — Run expansion section](../03-module-catalog.md),
[05 — Log idioms](../05-branching-and-results.md#log-idioms-per-failure-site). Parent
index: [08 — Sim-cycle modules](08-sim-cycle-modules.md).

## Goal

Resolve the per-run seed across all three seed modes, routing a per-test FAIL on a missing
or malformed REPLAY `.randseed`.

## Deliverables

In `modules/rtl_test/sim.py`:

- `ResolveSeedMod` — `(ctx, seed_mode, builder_cfg, logs_dir:str="logs")` → integrated
  seed-producer for all three modes:
  - `NEW` → `random.randrange(1_000_000)`
  - `DEFAULT` → `builder_cfg.get_seed()`
  - `REPLAY` → reads `f"{logs_dir}/{test_name}[_{run_id:04d}].randseed"` (uses
    `ctx["run_id"]` for the suffix; `logs_dir` is a persistent input fed by `--logs-dir`,
    default `"logs"`, matching rtl_buddy `tools/vlog_sim.py:199-203`); on
    missing/malformed file, emit `("fail", {"key", "result": <FAIL payload>})` and call
    `log.error` at emission with the attempted path. See
    [05 — Log idioms](../05-branching-and-results.md#log-idioms-per-failure-site).
  Emits in lockstep on success: `("ctx", ctx)`, `("seed", {"key", "seed"})`; on REPLAY
  failure: `("fail", result)`.
  **Failure handling**: REPLAY only — catch `(FileNotFoundError, ValueError)` around the
  `int(open(path).readline().strip())` parse (exactly matches
  `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:200-203`). `PermissionError` also possible;
  include in the catch. FAIL payload's `desc` is `f"Replay seed missing or invalid at
  {path}"` (rtl_buddy parity, `vlog_sim.py:203`). `NEW` and `DEFAULT` modes have no
  failure path.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:191-219` — `VlogSim.execute` seed resolution (REPLAY `:197-213`, NEW `:214-216`, DEFAULT `:218-219`).

Manifest entries per [06](../06-graph-yaml.md).

## Tests

In `modules/tests/test_sim_cycle.py`:

- `resolve-seed` covers all three modes; REPLAY round-trips a written `.randseed`.
- `resolve-seed` REPLAY honours `logs_dir`: write `.randseed` under a custom
  `logs_dir="custom_logs"`, then resolve-seed REPLAY with the same `logs_dir` reads it
  back. The REPLAY-missing fail path quotes the `logs_dir`-prefixed path in the FAIL
  payload's `desc`.

## Acceptance criteria

- Tests pass.
- All three modes produce a seed; the REPLAY-missing path routes a per-test FAIL with the
  `logs_dir`-prefixed path in `desc` and logs at ERROR.

## Constraints

- `NEW` seed uses `random.randrange(1_000_000)` (upper bound exclusive — matches
  rtl_buddy).
