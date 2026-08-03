# Spec 08b: resolve-seed (`ResolveSeedMod`)

**Depends on:** spec 03 (run-process), spec [01a](01a-builder-schema.md) (`ResolveSeedMod` consumes `RtlBuilderConfig.get_seed()`).
**References:** [03 — Run expansion section](../03-module-catalog.md), [05 — Log idioms](../05-branching-and-results.md#log-idioms-per-failure-site). Parent index: [idx-08 — Sim-cycle modules](../idx-08-sim-cycle.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)` signature, the allowed output forms (plain return / named-port tuple / generator), the `finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py` are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit `a69d962`). This module appends to `modules/rtl_buddy/sim.py`, which is created by spec [`08a`](08a-expand-runs.md) — append, do not overwrite. The file is shared with the sim-cycle modules (`08a`–`08f`, index [idx-08](../idx-08-sim-cycle.md)) and the post modules (`09a`–`09c`, index [idx-09](../idx-09-post.md)); coordinate shared imports and helpers with those specs. This spec defines the shared module-level helper `run_suffix` (Deliverables), also consumed by [08c](08c-build-sim-cmd.md).

## Goal

Resolve the per-run seed across all three seed modes, routing a per-test FAIL on a missing or malformed REPLAY `.randseed`.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry — the catalog is the design view, this is the build view; update both when behaviour changes. On success the forwarded edges (`test`/`run_id`/`simv`) and `seed` are emitted via a generator.

```
contract:          keyed_join
contract_config:   key_field: key
persistent_inputs: [seed_mode, builder_cfg, logs_dir]
inputs:            test, run_id, simv, seed_mode, builder_cfg, logs_dir:Path
outputs:           test   → TestConfig (self-keyed)   (forwarded)
                   run_id → {key, value}   (forwarded)
                   simv   → {key, value}   (forwarded — co-gated through to build-sim-cmd)
                   seed   → {key, value}
                   fail   → TestResult (self-keyed)   (REPLAY only)
```

`logs_dir` is the **resolved artefact directory** (a `Path`) supplied by `ensure-logs-dir`, not the CLI subdir name — the REPLAY read joins onto it and never touches the ambient CWD.

```python
class ResolveSeedMod:
    def run(self, test:TestConfig, run_id:KeyedValue[int | None], simv:KeyedValue[str], seed_mode:SeedMode, builder_cfg:RtlBuilderConfig, logs_dir:Path):
        if seed_mode == SeedMode.NEW:
            seed = random.randrange(1_000_000)   # upper bound exclusive
        elif seed_mode == SeedMode.DEFAULT:
            seed = builder_cfg.get_seed()
        else:   # REPLAY
            path = logs_dir / f"{test.get_name()}{run_suffix(run_id.value)}.randseed"
            try:
                seed = int(Path(path).open().readline().strip())
            # one except per class — distinct log events; the FAIL desc stays the rtl_buddy-parity message for all three
            except FileNotFoundError:
                log.error("replay_seed_not_found", key=test.key, test_name=test.get_name(), path=str(path))
                yield ("fail", TestResult.prep(test.key, test.get_name(), f"Replay seed missing or invalid at {path}")); return
            except ValueError as e:
                log.error("replay_seed_malformed", key=test.key, test_name=test.get_name(), path=str(path), err=str(e))
                yield ("fail", TestResult.prep(test.key, test.get_name(), f"Replay seed missing or invalid at {path}")); return
            except PermissionError as e:
                log.error("replay_seed_permission", key=test.key, test_name=test.get_name(), path=str(path), err=e.strerror)
                yield ("fail", TestResult.prep(test.key, test.get_name(), f"Replay seed missing or invalid at {path}")); return
        yield ("test", test)            # forward test+run_id+simv co-gated with success
        yield ("run_id", run_id)
        yield ("simv", simv)
        yield ("seed", KeyedValue(test.key, seed))
```

## Algorithm

1. Branch on `seed_mode`:
   - `NEW` → `seed = random.randrange(1_000_000)` (upper bound exclusive).
   - `DEFAULT` → `seed = builder_cfg.get_seed()`.
   - `REPLAY` → go to step 2.
2. **REPLAY read.** Compose `path = logs_dir / f"{test.get_name()}{run_suffix(run_id.value)}.randseed"` (joining onto the resolved `logs_dir` `Path` from `ensure-logs-dir` — no ambient-CWD assumption) and parse `seed = int(Path(path).open().readline().strip())`. `run_suffix(run_id.value)` is the shared `sim.py` helper this spec defines (Deliverables below); it returns `""` when the `run_id` value is `None`, else `f"_{run_id:04d}"` (run-id zero-padded to four digits) — matching rtl_buddy `_get_log_path` (`tools/vlog_sim.py:82-86`); e.g. run-id 3 reads `<logs_dir>/my_test_0003.randseed`.
3. On success (any mode) forward the three input edges and add `seed`: `("test", test)`, `("run_id", run_id)`, `("simv", simv)`, `("seed", KeyedValue(test.key, seed))`. `simv` is co-gated here (it bypasses neither this node nor its fail branch) so the downstream `build-sim-cmd` join can't dangle on a REPLAY failure.
4. **Failure — REPLAY missing/malformed, one event per case.** REPLAY only: wrap step 2's parse in a `try` with **one `except` per class** — `FileNotFoundError`→`replay_seed_not_found`, `ValueError`→`replay_seed_malformed` (`err=str(e)`), `PermissionError`→`replay_seed_permission` (`err=e.strerror`). Each logs its event with the attempted `path` (**not** `result`/`desc`) and emits `("fail", TestResult.prep(test.key, test.get_name(), f"Replay seed missing or invalid at {path}"))` — the FAIL `desc` stays the **rtl_buddy-parity** message for all three (`vlog_sim.py:203`), while the *log event* distinguishes the cause — then returns (dropping `test`/`run_id`/`simv`). The per-exception `log.error` drives the exit; the emitted `TestResult` → `results-summary` (spec [10d](10d-summarise-results.md)). `NEW`/`DEFAULT` have no failure path.

## Deliverables

In `modules/rtl_buddy/sim.py`:

- `ResolveSeedMod` — `(test, run_id, simv, seed_mode, builder_cfg, logs_dir:Path)`, `keyed_join` over `test`+`run_id`+`simv` with the config singletons as `persistent_inputs` → integrated seed-producer for all three modes:
  - `NEW` → `random.randrange(1_000_000)`
  - `DEFAULT` → `builder_cfg.get_seed()`
  - `REPLAY` → reads `logs_dir / f"{test_name}{run_suffix}.randseed"`, where `run_suffix = run_suffix(run_id.value)` is `""` when the `run_id` value is `None` and `f"_{run_id:04d}"` (the run-id zero-padded to four digits) otherwise — e.g. `<logs_dir>/my_test.randseed` for a single run, `<logs_dir>/my_test_0003.randseed` for run-id 3 (path format is rtl_buddy `_get_log_path`, `tools/vlog_sim.py:82-86`; `logs_dir` is the resolved artefact `Path` persistent input supplied by `ensure-logs-dir`, matching rtl_buddy `tools/vlog_sim.py:199-203`); on missing/malformed file, catch **each class in its own `except`** — `replay_seed_not_found` (`FileNotFoundError`), `replay_seed_malformed` (`ValueError`, `err=str(e)`), `replay_seed_permission` (`PermissionError`, `err=e.strerror`) — each logging its event with the attempted `path` (**not** `result`/`desc`) and emitting `("fail", TestResult.prep(key, test_name, f"Replay seed missing or invalid at {path}"))`. See [05 — Log idioms](../05-branching-and-results.md#log-idioms-per-failure-site).
  Emits on success: `("test", test)`, `("run_id", run_id)`, `("simv", simv)`, `("seed", KeyedValue(key, seed))`; on REPLAY failure: `("fail", result)`.
  **Failure handling**: REPLAY only — **one `except` per class** around the `int(open(path).readline().strip())` parse: `FileNotFoundError`→`replay_seed_not_found`, `ValueError`→`replay_seed_malformed` (the parse, matching `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:200-203`), `PermissionError`→`replay_seed_permission`. Each logs its event with the attempted `path` + exception-specific fields; the FAIL payload's `desc` stays `f"Replay seed missing or invalid at {path}"` for all three (rtl_buddy parity, `vlog_sim.py:203`) — the *log event* distinguishes the cause. `NEW` and `DEFAULT` modes have no failure path.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:191-219` — `VlogSim.execute` seed resolution (REPLAY `:197-213`, NEW `:214-216`, DEFAULT `:218-219`).

- **`run_suffix(run_id)` — shared module-level helper.** This spec is the first sim module to need the run-id suffix (the REPLAY path above), so it owns the canonical definition. Also consumed by `build-sim-cmd` [08c](08c-build-sim-cmd.md) as `run_suffix(run_id.value)`; `write-randseed` [08d](08d-write-randseed.md) receives the pre-composed paths and does not call it. It mirrors the run-id suffixing in rtl_buddy's `_get_log_path`:

  ```python
  # modules/rtl_buddy/sim.py  (module-level helper)
  def run_suffix(run_id) -> str:
      return "" if run_id is None else f"_{run_id:04d}"   # run-id zero-padded to four digits
  ```

  Returns `""` when `run_id is None` (single run), else `f"_{run_id:04d}"` — e.g. run-id 3 → `_0003`. The `is None` test (not falsiness) keeps run-id `0` suffixed. Callers pass the `run_id` edge's value (`run_suffix(run_id.value)`) and join the result onto the test-name stem they compose under `logs_dir`.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:82-86` — `VlogSim._get_log_path`'s `if run_id is not None: log_path += f"_{run_id:04d}"`.

**Manifest** — append to the `- file: rtl_buddy/sim.py` block in `modules/config.yaml` (opened by [`08a`](08a-expand-runs.md); append, don't re-create):

```yaml
  - { name: resolve-seed, class_name: ResolveSeedMod }
```

## Tests

In `modules/tests/test_sim_cycle.py`. Fixtures: `tmp_path` passed as the resolved `logs_dir` `Path` for the `.randseed` files; `monkeypatch` on `random.randrange` to pin the NEW value; `test` (`{key, value}`, value with `get_name`), `run_id` (`{key, value}`), `simv` (`{key, value}`) edge dicts; a `builder_cfg` with `get_seed`; `logging_handler` for the REPLAY-fail path. Drive `run(test, run_id, simv, …)` directly.

- `seed_mode=NEW` → yields `("test", …)`, `("run_id", …)`, `("simv", …)`, then `("seed", KeyedValue(key, seed))` with `seed ==` the pinned `random.randrange(1_000_000)` value (assert `0 <= seed < 1_000_000`).
- `seed_mode=DEFAULT` → forwards the three edges + `seed` with `seed == builder_cfg.get_seed()`.
- `seed_mode=REPLAY` with a written `.randseed` (under the resolved `logs_dir` `Path`, with the `run_id` value's suffix) → reads it back, forwards the three edges + `seed` equal to the written integer (round-trip).
- `seed_mode=REPLAY` with `logs_dir=Path("/work/custom_logs")` → writes/reads under that directory; the path is joined onto the provided `logs_dir` `Path`, not a hard-coded `logs/` or the ambient CWD.
- `seed_mode=REPLAY` with a missing `.randseed` → `FileNotFoundError` → yields only `("fail", TestResult.prep(key, test_name, …))` (no `test`/`run_id`/`simv`) whose `desc` is `f"Replay seed missing or invalid at {path}"` and quotes the `logs_dir`-prefixed path, `logging_handler.failure is True`, no `typer.Exit`.
- `seed_mode=REPLAY` with a `.randseed` whose first line is not an int → `ValueError` → yields `("fail", …)`, `log.error` (boundary: malformed file routes like a missing one).

## Acceptance criteria

- Tests pass.
- All output ports exercised: on success `test`/`run_id`/`simv` are forwarded and `seed` emits `{key, value}` for each of the three seed modes; the REPLAY-missing case routes the `fail` port (dropping the forwarded edges) with a per-test FAIL carrying the `logs_dir`-prefixed path in `desc` and logs at ERROR.
- The `modules/config.yaml` manifest entry `{ name: resolve-seed, class_name: ResolveSeedMod }` validates and the harness resolves `resolve-seed` → `ResolveSeedMod`.

## Constraints

- `NEW` seed uses `random.randrange(1_000_000)` (upper bound **exclusive** — matches rtl_buddy); `DEFAULT` uses `builder_cfg.get_seed()` — do not invent a value for either.
- `keyed_join` over `test`+`run_id`+`simv` (key_field `key`); `seed_mode`/`builder_cfg`/`logs_dir` are `persistent_inputs`. On success forward `("test", test)`, `("run_id", run_id)`, `("simv", simv)`, then `("seed", {key, value: seed})` via the generator — co-gate `simv` through so `build-sim-cmd`'s join can't dangle on a REPLAY fail.
- REPLAY only: catch **each class in its own `except`** around the `int(open(path).readline().strip())` parse — `FileNotFoundError`→`replay_seed_not_found`, `ValueError`→`replay_seed_malformed`, `PermissionError`→`replay_seed_permission` — each logging its event with the attempted `path` + exception-specific fields (**not** `result`/`desc`) and emitting `("fail", TestResult.prep(test.key, test.get_name(), f"Replay seed missing or invalid at {path}"))` on the `fail` port (→ `results-summary`) (dropping the forwarded edges); the FAIL `desc` is the rtl_buddy-parity message for all three. The per-exception `log.error` drives the exit. Do **not** collapse the clauses into one tuple-`except`/one event. `NEW`/`DEFAULT` have **no** failure path.
- Compose the REPLAY path by joining onto the resolved `logs_dir` `Path` persistent input from `ensure-logs-dir` (`logs_dir / name`); do not hard-code `logs/` or read the ambient CWD.
