# Spec 06: RegressionLevelSkipFilter

## What this covers

Implement `RegressionLevelSkipFilter` in `modules/rtl_buddy_compat/planning.py`. This module applies regression-level start/end gates before sweep expansion. Tests outside the configured bounds are routed to the `skip` port as `SKIP` result rows; tests within bounds pass through on `run`.

## Prerequisites

Spec 00 (artefacts) must be complete.

## Before you start

Read:
- `rtl_buddy/src/rtl_buddy/config/test.py:L211-L240` — `get_reglvl(builder_name)` logic; handles `int`, `dict`, and `None`
- `rtl_buddy/src/rtl_buddy/rtl_buddy.py:L306-L321` — skip conditions and row construction
- `rtl_buddy/src/rtl_buddy/rtl_buddy.py:L237-L241` — skipped tests produce one row per run id

## File: `modules/rtl_buddy_compat/planning.py`

Create this file. Specs 07 and 08 will add `LegacySweepExpand` and `RunIdPlan` to it.

### `RegressionLevelSkipFilter`

```
contract: latest, trigger_ports: [test]
inputs:  test: TestConfigEnvelope,
         root: RootContext,
         reg_level: int | None = None,
         start_level: int | None = None
outputs: run → TestConfigEnvelope
         skip → TestResultRow
```

`reg_level` and `start_level` are optional `run()` parameters with default values of `None`. They are not upstream edges in the graph; they are intended for regression-mode usage (left unset for plain `test`).

**Default-valued input behaviour**: when no upstream edge is wired for `reg_level` or `start_level`, the harness omits those keys from the dict passed to `run()` entirely — Python's own parameter default (`None`) takes effect. No `Payload` wrapper is injected. The `if reg_level is not None` checks in the implementation therefore work as written.

Implementation steps:

1. Resolve `t_lvl` from `test.reglvl` and `root.builder_name`:
   - `None` → `t_lvl = 0`
   - `int` → `t_lvl = reglvl`
   - `dict` → `t_lvl = reglvl.get(root.builder_name, 0)`

2. If `reg_level is not None and t_lvl > reg_level`:
   emit `("skip", TestResultRow(key=_make_key(test), result="SKIP", desc=f"reglvl {t_lvl} exceeds limit {reg_level}"))`.

3. Else if `start_level is not None and t_lvl < start_level`:
   emit `("skip", TestResultRow(key=_make_key(test), result="SKIP", desc=f"reglvl {t_lvl} below start {start_level}"))`.

4. Otherwise emit `("run", test)`.

For the skip `TestInstanceKey`, use:
`TestInstanceKey(suite_path=test.suite_path, original_test_name=test.name, expanded_test_name=test.name, expanded_index=test.declaration_index, run_id=None)`.

Compatibility: `rtl_buddy.py:L306-L321`, `test.py:L211-L240`.

## Register in `modules/rtl_buddy_compat/config.yaml`

Append to `files`:

```yaml
- file: planning.py
  plugins:
  - name: regression_level_skip_filter
    class_name: RegressionLevelSkipFilter
```

Specs 07 and 08 will add `LegacySweepExpand` and `RunIdPlan` to this entry.

## Tests

Write `modules/rtl_buddy_compat/tests/test_regression_level_skip_filter.py`.

- `reglvl=None`, no bounds → emits on `"run"`
- `reglvl=5, reg_level=3` → emits `"skip"` (`5 > 3`)
- `reglvl=3, reg_level=3` → emits `"run"` (equal is not over limit)
- `reglvl=1, start_level=3` → emits `"skip"` (`1 < 3`)
- `reglvl=3, start_level=3` → emits `"run"` (equal is not below start)
- `reglvl={"vcs": 5}, builder_name="vcs", reg_level=3` → emits `"skip"`
- `reglvl={"vcs": 5}, builder_name="other", reg_level=3` → `t_lvl=0`, emits `"run"` (missing key → 0)
- Emitted `SKIP` row has `result="SKIP"` and a non-empty `desc`

## Constraints

- `SKIP` result is pass-like for exit code purposes (this is upstream behavior; just ensure `result="SKIP"` is emitted correctly).
- Do not emit a `SKIP` row and a `run` item for the same test.
