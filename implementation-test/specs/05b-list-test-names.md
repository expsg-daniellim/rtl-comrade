# Spec 05b: list-test-names (`ListTestNamesMod`)

**Depends on:** spec 01 (schema), spec [01b](01b-suite-schema.md) (`SuiteConfig`).
**References:** [03 — Selection/expansion section](../03-module-catalog.md). Parent index:
[idx-05 — Selection and expansion modules](../idx-05-selection-expansion.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)`
signature, the allowed output forms (plain return / named-port tuple / generator), the
`finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py`
are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry
below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit
`a69d962`). This module appends to `modules/rtl_buddy/setup.py`, which is created by spec
[`04a`](04a-discover-config-file.md) — append, do not overwrite. The file is shared with the
setup chain (`04a`–`04i`, index [idx-04](../idx-04-setup.md)), the selection/expansion chain
(`05a`–`05f`, index [idx-05](../idx-05-selection-expansion.md)), and git-status (`10b`);
coordinate shared imports and helpers with those specs.

## Goal

Print the suite's test names in declaration order — the list-mode terminal sink.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry —
the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract: default
inputs:   suite_cfg
outputs:  none  (terminal sink)
```

> `default`, **not** `unit`: the unfired `list`/`run` branch leaves this node fed only an
> `EndSentinel`, which `unit` would treat as `missing_required_inputs` (→ exit 1). Rationale in
> [04 — Why each contract](../04-pipeline-and-contracts.md#default--the-post-branch-run-once-nodes-select-list-names).

```python
class ListTestNamesMod:
    def run(self, suite_cfg):
        print("  ".join(suite_cfg.get_test_names()))   # terminal: emits nothing
```

## Algorithm

1. Fetch names in declaration order: `suite_cfg.get_test_names()` (spec 01b → `list[str]`).
2. Print them two-space-joined: `print("  ".join(...))`. Terminal sink — emits nothing, no
   failure path.

## Deliverables

In `modules/rtl_buddy/setup.py` (continuing from spec 04):

- `ListTestNamesMod` — `(suite_cfg)` → prints `"  ".join(suite_cfg.get_test_names())`
  (spec [01b](01b-suite-schema.md) — returns `list[str]` of test names in declaration
  order) and emits nothing. Terminal sink.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/rtl_buddy.py:183` — the `typer.echo` of `get_test_names()`; `get_test_names` at `config/suite.py:69-76`.

**Manifest** — append to the `- file: rtl_buddy/setup.py` block in `modules/config.yaml`
(opened by [`04a`](04a-discover-config-file.md); append, don't re-create):

```yaml
  - { name: list-test-names, class_name: ListTestNamesMod }
```

## Tests

In `modules/tests/test_selection.py`. Fixtures: `capsys` to capture stdout; `suite_cfg`
fixtures (multi-test, single-test, empty).

- A 3-test `suite_cfg` → stdout is the three names two-space joined in declaration order;
  emits nothing (terminal sink, `expected_emissions={}`).
- A `suite_cfg` whose names would sort differently from declaration order (e.g. tests defined
  `zebra`, `alpha`) → stdout is `"zebra  alpha"`, not alphabetised (verifies declaration order).
- A single-test `suite_cfg` → stdout is just that name with no separator (boundary: one test).
- An empty `suite_cfg` (no tests) → stdout is an empty line; emits nothing (boundary: empty
  suite, `"  ".join([])` is `""`).

## Acceptance criteria

- Tests pass.
- Terminal sink: prints test names two-space-joined in declaration order and emits nothing
  (no output ports, no failure path).
- The `modules/config.yaml` manifest entry `{ name: list-test-names, class_name: ListTestNamesMod }`
  validates and the harness resolves `list-test-names` → `ListTestNamesMod`.

## Constraints

- Terminal sink: `print("  ".join(suite_cfg.get_test_names()))` — names in declaration order,
  two-space joined — and **emit nothing** (no output ports).
- No failure path, no log call.
