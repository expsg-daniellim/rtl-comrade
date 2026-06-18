# Spec 08b: resolve-seed (`ResolveSeedMod`)

**Depends on:** spec 03 (run-process), spec [01a](01a-builder-schema.md) (`ResolveSeedMod` consumes `RtlBuilderConfig.get_seed()`).
**References:** [03 — Run expansion section](../03-module-catalog.md), [05 — Log idioms](../05-branching-and-results.md#log-idioms-per-failure-site). Parent index: [idx-08 — Sim-cycle modules](../idx-08-sim-cycle.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)` signature, the allowed output forms (plain return / named-port tuple / generator), the `finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py` are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit `a69d962`). This module appends to `modules/rtl_buddy/sim.py`, which is created by spec [`08a`](08a-expand-runs.md) — append, do not overwrite. The file is shared with the sim-cycle modules (`08a`–`08f`, index [idx-08](../idx-08-sim-cycle.md)) and the post modules (`09a`–`09c`, index [idx-09](../idx-09-post.md)); coordinate shared imports and helpers with those specs.

## Goal

Resolve the per-run seed across all three seed modes, routing a per-test FAIL on a missing or malformed REPLAY `.randseed`.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry — the catalog is the design view, this is the build view; update both when behaviour changes. On success the `ctx`/`seed` ports are emitted in lockstep via a generator.

```
contract:          default
persistent_inputs: [seed_mode, builder_cfg, logs_dir]
inputs:            ctx, seed_mode, builder_cfg, logs_dir:Path
outputs:           ctx  → ctx
                   seed → {key, seed}
                   fail → result   (REPLAY only)
```

`logs_dir` is the **resolved artefact directory** (a `Path`) supplied by `ensure-logs-dir`, not the CLI subdir name — the REPLAY read joins onto it and never touches the ambient CWD.

```python
class ResolveSeedMod:
    def run(self, ctx, seed_mode, builder_cfg, logs_dir):
        if seed_mode == SeedMode.NEW:
            seed = random.randrange(1_000_000)   # upper bound exclusive
        elif seed_mode == SeedMode.DEFAULT:
            seed = builder_cfg.get_seed()
        else:   # REPLAY
            path = logs_dir / f"{ctx['test'].get_name()}{run_suffix(ctx)}.randseed"
            try:
                seed = int(Path(path).open().readline().strip())
            except (FileNotFoundError, ValueError, PermissionError):
                result = make_fail_result(desc=f"Replay seed missing or invalid at {path}")
                log.error("replay_seed_invalid", key=ctx["key"], test_name=ctx["test"].get_name(), path=str(path),
                          result=result.results["result"], desc=result.results["desc"])   # → SummaryProcessor row
                yield ("fail", { "key": ctx["key"], "result": result })
                return
        yield ("ctx", ctx)
        yield ("seed", { "key": ctx["key"], "seed": seed })
```

## Algorithm

1. Branch on `seed_mode`:
   - `NEW` → `seed = random.randrange(1_000_000)` (upper bound exclusive).
   - `DEFAULT` → `seed = builder_cfg.get_seed()`.
   - `REPLAY` → go to step 2.
2. **REPLAY read.** Compose `path = logs_dir / f"{ctx['test'].get_name()}{run_suffix(ctx)}.randseed"` (joining onto the resolved `logs_dir` `Path` from `ensure-logs-dir` — no ambient-CWD assumption) and parse `seed = int(Path(path).open().readline().strip())`. `run_suffix(ctx)` returns `""` when `ctx["run_id"] is None`, else `f"_{ctx['run_id']:04d}"` (run-id zero-padded to four digits) — matching rtl_buddy `_get_log_path` (`tools/vlog_sim.py:82-86`); e.g. run-id 3 reads `<logs_dir>/my_test_0003.randseed`.
3. On success (any mode) emit in lockstep: `("ctx", ctx)` then `("seed", {"key": ctx["key"], "seed": seed})`.
4. **Failure — REPLAY missing/malformed.** REPLAY only: wrap step 2 in `try/except (FileNotFoundError, ValueError, PermissionError)` → `log.error("replay_seed_invalid", key=ctx["key"], path=str(path), result=…, desc=…)` (the `result`/`desc` kwargs let `SummaryProcessor`'s watch-list collect the row), emit `("fail", {"key": ctx["key"], "result": <FAIL whose desc is f"Replay seed missing or invalid at {path}">})`, and return. `NEW`/`DEFAULT` have no failure path.

## Deliverables

In `modules/rtl_buddy/sim.py`:

- `ResolveSeedMod` — `(ctx, seed_mode, builder_cfg, logs_dir:Path)` → integrated seed-producer for all three modes:
  - `NEW` → `random.randrange(1_000_000)`
  - `DEFAULT` → `builder_cfg.get_seed()`
  - `REPLAY` → reads `logs_dir / f"{test_name}{run_suffix}.randseed"`, where `run_suffix` is `""` when `ctx["run_id"] is None` and `f"_{run_id:04d}"` (the run-id zero-padded to four digits) otherwise — e.g. `<logs_dir>/my_test.randseed` for a single run, `<logs_dir>/my_test_0003.randseed` for run-id 3 (path format is rtl_buddy `_get_log_path`, `tools/vlog_sim.py:82-86`; `logs_dir` is the resolved artefact `Path` persistent input supplied by `ensure-logs-dir`, matching rtl_buddy `tools/vlog_sim.py:199-203`); on missing/malformed file, emit `("fail", {"key", "result": <FAIL payload>})` and call `log.error("replay_seed_invalid", …)` at emission with the attempted path **and `result`/`desc`** (so the `SummaryProcessor` watch-list, [10c](10c-summary-handler.md), renders the row). See [05 — Log idioms](../05-branching-and-results.md#log-idioms-per-failure-site).
  Emits in lockstep on success: `("ctx", ctx)`, `("seed", {"key", "seed"})`; on REPLAY failure: `("fail", result)`.
  **Failure handling**: REPLAY only — catch `(FileNotFoundError, ValueError)` around the `int(open(path).readline().strip())` parse (exactly matches `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:200-203`). `PermissionError` also possible; include in the catch. FAIL payload's `desc` is `f"Replay seed missing or invalid at {path}"` (rtl_buddy parity, `vlog_sim.py:203`). `NEW` and `DEFAULT` modes have no failure path.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:191-219` — `VlogSim.execute` seed resolution (REPLAY `:197-213`, NEW `:214-216`, DEFAULT `:218-219`).

**Manifest** — append to the `- file: rtl_buddy/sim.py` block in `modules/config.yaml` (opened by [`08a`](08a-expand-runs.md); append, don't re-create):

```yaml
  - { name: resolve-seed, class_name: ResolveSeedMod }
```

## Tests

In `modules/tests/test_sim_cycle.py`. Fixtures: `tmp_path` passed as the resolved `logs_dir` `Path` for the `.randseed` files; `monkeypatch` on `random.randrange` to pin the NEW value; a `ctx` fixture (`test.get_name`, `run_id`); a `builder_cfg` with `get_seed`; `logging_handler` for the REPLAY-fail path.

- `seed_mode=NEW` → yields `("ctx", ctx)` then `("seed", {"key", "seed"})` with `seed ==` the pinned `random.randrange(1_000_000)` value (assert `0 <= seed < 1_000_000`).
- `seed_mode=DEFAULT` → yields `ctx` + `seed` with `seed == builder_cfg.get_seed()`.
- `seed_mode=REPLAY` with a written `.randseed` (under the resolved `logs_dir` `Path`, with the `run_id` suffix) → reads it back, yields `ctx` + `seed` equal to the written integer (round-trip).
- `seed_mode=REPLAY` with `logs_dir=Path("/work/custom_logs")` → writes/reads under that directory; the path is joined onto the provided `logs_dir` `Path`, not a hard-coded `logs/` or the ambient CWD.
- `seed_mode=REPLAY` with a missing `.randseed` → `FileNotFoundError` → yields `("fail", {"key", "result"})` whose `desc` is `f"Replay seed missing or invalid at {path}"` and quotes the `logs_dir`-prefixed path, `logging_handler.failure is True`, no `SystemExit`.
- `seed_mode=REPLAY` with a `.randseed` whose first line is not an int → `ValueError` → yields `("fail", …)`, `log.error` (boundary: malformed file routes like a missing one).

## Acceptance criteria

- Tests pass.
- All three output ports exercised: `ctx` forwards `ctx` and `seed` emits `{key, seed}` for each of the three seed modes; the REPLAY-missing case routes the `fail` port with a per-test FAIL carrying the `logs_dir`-prefixed path in `desc` and logs at ERROR.
- The `modules/config.yaml` manifest entry `{ name: resolve-seed, class_name: ResolveSeedMod }` validates and the harness resolves `resolve-seed` → `ResolveSeedMod`.

## Constraints

- `NEW` seed uses `random.randrange(1_000_000)` (upper bound **exclusive** — matches rtl_buddy); `DEFAULT` uses `builder_cfg.get_seed()` — do not invent a value for either.
- On success emit `("ctx", ctx)` then `("seed", {key, seed})` in lockstep via the generator.
- REPLAY only: catch `(FileNotFoundError, ValueError, PermissionError)` around the `int(open(path).readline().strip())` parse → emit `("fail", {key, result: <FAIL>})` on the **unwired** `fail` port and `log.error("replay_seed_invalid", …)` at emission with the attempted path **and `result`/`desc`** (so the `SummaryProcessor` watch-list collects the row). `NEW`/`DEFAULT` have **no** failure path.
- Compose the REPLAY path by joining onto the resolved `logs_dir` `Path` persistent input from `ensure-logs-dir` (`logs_dir / name`); do not hard-code `logs/` or read the ambient CWD.
