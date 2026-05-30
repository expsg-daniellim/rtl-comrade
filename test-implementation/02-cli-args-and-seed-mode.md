# Spec 02: SeedModeSelect

## What this covers

Implement `SeedModeSelect` in `modules/rtl_buddy_compat/bootstrap.py`. This module maps seed-mode flags arriving from CLI edges directly into a three-way `SeedModePlan` enum. `RootBootstrap` — the complex bootstrap module — is spec 03.

## Prerequisites

Spec 00 (artefacts) must be complete. Import from `modules/rtl_buddy_compat/artefacts.py`.

## Before you start

Read `CLAUDE.md` and `docs/module-implementation.md` for module authoring conventions.

Compatibility source: `rtl_buddy/src/rtl_buddy/rtl_buddy.py:L184-L190`.

## File: `modules/rtl_buddy_compat/bootstrap.py`

Create this file. `RootBootstrap` will be added by spec 03.

### `SeedModeSelect`

```
contract: zip
inputs:  rnd_new: bool, rnd_last: bool
outputs: default → SeedModePlan
```

Both inputs arrive from CLI edges. Priority: `rnd_new` wins if both flags are set.

```
rnd_new=True  → mode="new"
rnd_last=True → mode="replay"
else          → mode="default"
```

```python
class SeedModeSelect:
    def run(self, rnd_new, rnd_last):
        if rnd_new:
            return SeedModePlan(mode="new")
        if rnd_last:
            return SeedModePlan(mode="replay")
        return SeedModePlan(mode="default")
```

Compatibility: `rtl_buddy.py:L184-L190`.

## Register in `modules/rtl_buddy_compat/config.yaml`

Replace `files: []` with:

```yaml
files:
- file: bootstrap.py
  plugins:
  - name: seed_mode_select
    class_name: SeedModeSelect
```

`RootBootstrap` will be added to this entry by spec 03.

## Tests

Write `modules/rtl_buddy_compat/tests/__init__.py` (empty) and `modules/rtl_buddy_compat/tests/test_bootstrap.py`.

**`SeedModeSelect`**:
- `rnd_new=True, rnd_last=False` → `mode="new"`
- `rnd_new=False, rnd_last=True` → `mode="replay"`
- `rnd_new=False, rnd_last=False` → `mode="default"`
- `rnd_new=True, rnd_last=True` → `mode="new"` (rnd_new wins)

## Constraints

- No filesystem access in `SeedModeSelect`.
- `SeedModeSelect` must have no `Config` class — all values come from `run()` parameters.
