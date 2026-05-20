# Spec 05: ListTestsBranch + ListTestsRender + TestSelect

## What this covers

Implement `ListTestsBranch`, `ListTestsRender`, and `TestSelect` in `modules/rtl_buddy_compat/suite.py` (the file created by spec 04). All three are small: two are pure routing/rendering nodes, one is a generator with name lookup.

## Prerequisites

Specs 00 and 04 (artefacts + suite.py file exists with SuiteConfigLoad) must be complete.

## Before you start

Read:
- `rtl_buddy/src/rtl_buddy/rtl_buddy.py:L174-L176` — `--list` render and exit
- `rtl_buddy/src/rtl_buddy/config/suite.py:L41-L62` — `get_tests()` and `get_test_names()`

## Additions to `modules/rtl_buddy_compat/suite.py`

### `ListTestsBranch`

```
contract: zip
inputs:  cli: TestCliArgs, suite: SuiteContext
outputs: list → SuiteContext, run → SuiteContext
```

Pure routing. Emits `suite` unchanged on one of two named ports.

```python
def run(self, cli, suite):
    if cli.list_tests:
        return ("list", suite)
    return ("run", suite)
```

---

### `ListTestsRender`

```
contract: unit
inputs:  suite: SuiteContext
outputs: default → RenderedOutput
```

```python
def run(self, suite):
    return RenderedOutput(text="  ".join(suite.test_names))
```

Compatibility: `rtl_buddy.py:L174-L176` — names joined with two spaces.

---

### `TestSelect`

```
contract: zip
inputs:  cli: TestCliArgs, suite: SuiteContext
outputs: default → stream of TestConfigEnvelope (generator)
```

`run()` is a generator.

Implementation steps:
1. If `cli.test_name` is set: find the matching test by name. Fatal if not found.
2. Otherwise yield all tests in declaration order.

Compatibility: `suite.py:L41-L55`.

## Register in `modules/rtl_buddy_compat/config.yaml`

Add to the existing `suite.py` entry (created by spec 04):

```yaml
  - name: list_tests_branch
    class_name: ListTestsBranch
  - name: list_tests_render
    class_name: ListTestsRender
  - name: test_select
    class_name: TestSelect
```

## Tests

Write `modules/rtl_buddy_compat/tests/test_suite_routing.py`.

**`ListTestsBranch`**:
- `list_tests=True` → emits on `"list"` port with suite unchanged
- `list_tests=False` → emits on `"run"` port with suite unchanged

**`ListTestsRender`**:
- `test_names=["a", "b", "c"]` → `"a  b  c"` (two spaces between names)
- Single test → no trailing spaces

**`TestSelect`**:
- Named test present → yields exactly one `TestConfigEnvelope`
- Named test absent → fatal (`SystemExit`)
- No name → yields all tests in declaration order (verify count and order)

## Constraints

- `ListTestsBranch` and `ListTestsRender` must have zero filesystem access.
- `TestSelect` must emit tests in the order they appear in `suite.tests`, not sorted.
