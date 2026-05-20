# Spec 14: SeedResolve

## What this covers

Implement `SeedResolve` in `modules/rtl_buddy_compat/sim.py` (the file created by spec 13). This module resolves the concrete simulation seed for one run, routing to `success` or `failure` depending on whether the seed is obtainable.

## Prerequisites

Specs 00 and 13 (artefacts + sim.py file exists) must be complete.

## Before you start

Read:
- `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:L211-L245` — replay/new/default seed logic and replay failure file writes
- `rtl_buddy/src/rtl_buddy/runner/test_runner.py:L105-L111` — replay run id handling

## Addition to `modules/rtl_buddy_compat/sim.py`

### `SeedResolve`

```
contract: latest, trigger_ports: [run]
inputs:  run: PerRunExecutionPlan, root: RootContext
outputs: success → ResolvedRunPlan
         failure → TestResultRow
```

Implementation steps:

1. Reconstruct builder config from `root.rtl_builder_cfg` dict to access `get_seed()`.

2. `mode = run.seed_mode.mode`.

3. **Replay** (`mode == "replay"`):
   - Determine randseed file path:
     - `run_id=None` → `<build_dir>/test.randseed`
     - `run_id=N` → `<build_dir>/test_<N:04d>.randseed`
   - Read and parse first line as `int`. On `FileNotFoundError`, `ValueError`, or any read error: emit `("failure", TestResultRow(key=run.key, result="FAIL", desc="replay seed not found"))`.

4. **New** (`mode == "new"`):
   - `seed = random.randrange(1000000)` (matches `vlog_sim.py:L228`).

5. **Default** (`mode == "default"`):
   - `seed = rtl_builder_cfg["seed"]` or `0` if not present.

6. On success: emit `("success", ResolvedRunPlan(key=run.key, test=run.test, seed=seed, seed_mode=run.seed_mode, compile_result=run.compile_result))`.

Compatibility: `vlog_sim.py:L211-L245`, `test_runner.py:L105-L111`.

## Register in `modules/rtl_buddy_compat/config.yaml`

Add to the existing `sim.py` entry:

```yaml
  - name: seed_resolve
    class_name: SeedResolve
```

## Tests

Write `modules/rtl_buddy_compat/tests/test_seed_resolve.py`.

- `mode="default"` → seed from builder config (or 0 if absent)
- `mode="new"` → seed is in `[0, 1000000)`, emits on `"success"`
- `mode="replay"` with valid `.randseed` file containing `"42\n"` → `seed=42`, emits on `"success"`
- `mode="replay"` with missing file → emits on `"failure"` with `result="FAIL"`
- `mode="replay"` with non-integer content → emits on `"failure"`
- `run_id=None` → looks for `test.randseed`
- `run_id=3` → looks for `test_0003.randseed`
- `ResolvedRunPlan.compile_result` forwards the input `compile_result`

## Constraints

- Use `random.randrange(1000000)` for new seeds; range must match legacy behavior.
- Failure on replay must emit a `TestResultRow` on the `"failure"` port, not raise an exception.
