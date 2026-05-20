# Spec 09: LegacyPreproc

## What this covers

Implement `LegacyPreproc` in `modules/rtl_buddy_compat/preproc.py`. This module runs an optional legacy preproc hook script that may mutate the test config before filelist generation and compile. `RunDepthGate` — the other module in this file — is spec 10.

## Prerequisites

Spec 00 (artefacts) must be complete.

## Before you start

Read:
- `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:L121-L141` — preproc script execution namespace and mutation semantics
- `rtl_buddy/src/rtl_buddy/runner/test_runner.py:L56-L60` — preproc runs before `RunDepth.PRE` gate and before compile

## File: `modules/rtl_buddy_compat/preproc.py`

Create this file. Spec 10 will add `RunDepthGate` to it.

### `LegacyPreproc`

```
contract: latest, trigger_ports: [run_plan]
inputs:  run_plan: RunPlan, root: RootContext
outputs: default → PreprocessedRunPlan
```

Implementation steps:

1. If `run_plan.test.preproc_path is None`: emit `PreprocessedRunPlan(key=run_plan.key, test=run_plan.test, seed_mode=run_plan.seed_mode)` immediately. Done.

2. Otherwise, read the script file. Fatal if not readable.

3. Build execution namespace matching `vlog_sim.py:L121-L141`:
   ```python
   import logging
   ns = {
       "logger": logging.getLogger("preproc"),
       "test_cfg": run_plan.test,
       "root_cfg": root,
   }
   ```

4. `exec(script_source, ns)`. The script may mutate `ns["test_cfg"]` in place, or replace it entirely.

5. Emit `PreprocessedRunPlan(key=run_plan.key, test=ns["test_cfg"], seed_mode=run_plan.seed_mode)`.

The emitted `test` is `ns["test_cfg"]` after exec — it may differ from `run_plan.test` if the script mutated it.

Compatibility: `vlog_sim.py:L121-L141`, `test_runner.py:L56-L60`.

## Create `modules/rtl_buddy_compat/config.yaml` entry

Append to `files`:

```yaml
- file: preproc.py
  plugins:
  - name: legacy_preproc
    class_name: LegacyPreproc
```

Spec 10 will add `RunDepthGate` to this entry.

## Tests

Write `modules/rtl_buddy_compat/tests/test_legacy_preproc.py`.

- `preproc_path=None` → emits with `test` unchanged (same object)
- Script that mutates `test_cfg.plusargs` → emitted `PreprocessedRunPlan.test` has mutated plusargs
- Script that replaces `test_cfg` entirely with a new object → emitted plan uses the new object
- Missing script file → fatal (`SystemExit`)
- `key` and `seed_mode` are always forwarded unchanged regardless of script behavior

## Constraints

- Preproc runs once per expanded test (one `RunPlan` in, one `PreprocessedRunPlan` out).
- Use `ns["test_cfg"]` after exec as the emitted test, not the original `run_plan.test`.
