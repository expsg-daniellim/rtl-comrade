# Spec 07: LegacySweepExpand

## What this covers

Implement `LegacySweepExpand` in `modules/rtl_buddy_compat/planning.py` (the file created by spec 06). This module runs optional legacy sweep scripts and fans one `TestConfigEnvelope` into one or more expanded variants via a generator.

## Prerequisites

Specs 00 and 06 (artefacts + planning.py file exists) must be complete.

## Before you start

Read:
- `rtl_buddy/src/rtl_buddy/rtl_buddy.py:L243-L262` — sweep script execution namespace and `out_test_cfgs` output list
- `rtl_buddy/src/rtl_buddy/rtl_buddy.py:L322-L331` — sweep runs before preproc and runner construction
- `rtl_buddy/src/rtl_buddy/config/test.py:L201-L209` — `get_sweep_path()`

## Addition to `modules/rtl_buddy_compat/planning.py`

### `LegacySweepExpand`

```
contract: latest, trigger_ports: [test]
inputs:  test: TestConfigEnvelope, root: RootContext
outputs: default → stream of TestConfigEnvelope (generator)
```

`run()` is a generator.

Implementation steps:

1. If `test.sweep_path is None`: yield `test` unchanged (with `declaration_index` preserved). Done.

2. Otherwise, read the script file. Fatal if not readable.

3. Build the execution namespace matching `rtl_buddy.py:L243-L262`:
   ```python
   import logging
   ns = {
       "logger": logging.getLogger("sweep"),
       "TestConfig": TestConfigEnvelope,
       "test_cfg": test,
       "root_cfg": root,
       "out_test_cfgs": [],
   }
   ```

4. `exec(script_source, ns)`.

5. For each item in `ns["out_test_cfgs"]`, set `declaration_index` to its 0-based position within this sweep output (so downstream modules can build `TestInstanceKey` correctly), then yield.

If the sweep script produces zero items, nothing is yielded (the test is silently dropped — this matches legacy behavior where an empty sweep means no runs).

Compatibility: `rtl_buddy.py:L243-L262`, `rtl_buddy.py:L322-L331`.

## Register in `modules/rtl_buddy_compat/config.yaml`

Add to the existing `planning.py` entry:

```yaml
  - name: legacy_sweep_expand
    class_name: LegacySweepExpand
```

## Tests

Write `modules/rtl_buddy_compat/tests/test_legacy_sweep_expand.py`.

- `sweep_path=None` → yields original test unchanged, `declaration_index` preserved
- Script that appends two items to `out_test_cfgs` → yields those two items with `declaration_index` 0 and 1
- Script that appends zero items → yields nothing
- Missing sweep file → fatal (`SystemExit`)
- Script that raises an exception → propagate or log critical (match rtl_buddy behavior: `exec()` exceptions are unhandled and propagate)

## Constraints

- `run()` must be a generator (use `yield`, not `return`).
- The no-sweep case must yield the original `test` object (not a copy).
- `declaration_index` on yielded items must reflect position within the sweep output, not the original test's position in the suite.
