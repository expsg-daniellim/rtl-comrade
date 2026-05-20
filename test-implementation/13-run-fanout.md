# Spec 13: RunFanout

## What this covers

Implement `RunFanout` in `modules/rtl_buddy_compat/sim.py`. This module fans one `CompileResult` into one `PerRunExecutionPlan` per run id. For plain `test`, this always yields exactly one item. It is the bridge between the compile stage and the per-run simulation stage.

## Prerequisites

Spec 00 (artefacts) must be complete.

## Before you start

Read:
- `rtl_buddy/src/rtl_buddy/runner/test_runner.py:L83-L122` — compile once, sim N times pattern

## File: `modules/rtl_buddy_compat/sim.py`

Create this file. Specs 14, 15, and 16 will add `SeedResolve`, `SimCommandBuild`, and `SimExecute`/`SimArtifactLink` to it.

### `RunFanout`

```
contract: latest, trigger_ports: [compile_result]
inputs:  compile_result: CompileResult, seed_mode: SeedModePlan
outputs: default → stream of PerRunExecutionPlan (generator)
```

`run()` is a generator. `seed_mode` is a state port (cached from graph startup).

Implementation steps:

1. `run_plan = compile_result.command.run_plan`.
2. `run_ids = [run_plan.key.run_id]` — for plain `test` this is `[None]`.
3. For each `run_id`:
   - Construct `key = TestInstanceKey(suite_path=run_plan.key.suite_path, original_test_name=run_plan.key.original_test_name, expanded_test_name=run_plan.key.expanded_test_name, expanded_index=run_plan.key.expanded_index, run_id=run_id)`.
   - Yield `PerRunExecutionPlan(key=key, test=run_plan.test, seed_mode=seed_mode, compile_result=compile_result)`.

Note: `seed_mode` is taken from the state port input, not from the compile result. This is correct — seed mode is a graph-level setting determined at startup, not per-compile.

Compatibility: `test_runner.py:L83-L122`.

## Register in `modules/rtl_buddy_compat/config.yaml`

Append to `files`:

```yaml
- file: sim.py
  plugins:
  - name: run_fanout
    class_name: RunFanout
```

Specs 14, 15, and 16 will add further entries to this plugin list.

## Tests

Write `modules/rtl_buddy_compat/tests/test_run_fanout.py`.

- Yields exactly one `PerRunExecutionPlan` with `key.run_id=None` for a plain test
- `seed_mode` in the yielded plan matches the state-port input (not derived from compile result)
- `compile_result` is forwarded into the yielded plan
- `key` fields match the upstream run plan's key fields

## Constraints

- `run()` must be a generator.
- `seed_mode` must come from the `seed_mode` input port, not reconstructed from `compile_result`.
