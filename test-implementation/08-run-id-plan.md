# Spec 08: RunIdPlan

## What this covers

Implement `RunIdPlan` in `modules/rtl_buddy_compat/planning.py` (the file created by spec 06). This module converts each expanded test into one or more `RunPlan` items — one per run id. For plain `test`, this always yields exactly one item with `run_id=None`.

## Prerequisites

Specs 00 and 06 (artefacts + planning.py file exists) must be complete.

## Before you start

Read:
- `rtl_buddy/src/rtl_buddy/rtl_buddy.py:L181-L191` — plain `test` uses `run_ids = [None]`
- `rtl_buddy/src/rtl_buddy/runner/test_runner.py:L83-L122` — multi-run path; compile once, sim per run id

## Addition to `modules/rtl_buddy_compat/planning.py`

### `RunIdPlan`

```
contract: latest, trigger_ports: [expanded_test]
inputs:  expanded_test: TestConfigEnvelope, cli: TestCliArgs, seed_mode: SeedModePlan
outputs: default → stream of RunPlan (generator)
```

`run()` is a generator. `cli` and `seed_mode` are state ports (arrive once and are cached).

Implementation steps:

1. For plain `test`, `run_ids = [None]`.

2. For each `run_id` in `run_ids`:
   - Construct `TestInstanceKey`:
     ```python
     TestInstanceKey(
         suite_path=expanded_test.suite_path,
         original_test_name=expanded_test.name,
         expanded_test_name=expanded_test.name,
         expanded_index=expanded_test.declaration_index,
         run_id=run_id,
     )
     ```
   - Yield `RunPlan(key=key, test=expanded_test, seed_mode=seed_mode)`.

Compatibility: `rtl_buddy.py:L181-L191`, `test_runner.py:L83-L122`.

## Register in `modules/rtl_buddy_compat/config.yaml`

Add to the existing `planning.py` entry:

```yaml
  - name: run_id_plan
    class_name: RunIdPlan
```

## Tests

Write `modules/rtl_buddy_compat/tests/test_run_id_plan.py`.

- Yields exactly one `RunPlan` with `run_id=None` for a plain test invocation
- `key.suite_path` matches `expanded_test.suite_path`
- `key.expanded_index` matches `expanded_test.declaration_index`
- `key.run_id` is `None`
- `seed_mode` in the emitted `RunPlan` matches the state-port input

## Constraints

- `run()` must be a generator (use `yield`).
- Do not hardcode `run_ids = [None]` in a way that prevents future extension to multi-run mode; use a variable.
