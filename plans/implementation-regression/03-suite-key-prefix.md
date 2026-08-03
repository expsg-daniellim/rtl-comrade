# Spec 03: suite-key prefixing (`ParseSuiteConfigMod` config change)

**Depends on:** nothing — the change is backwards-compatible and self-contained.
**References:** [00-overview](00-overview.md); `modules/rtl_buddy/setup.py` — existing `ParseSuiteConfigMod`; `rtl_buddy/src/rtl_buddy/config/reg.py:23-50` — `RegConfig.__init__` suite identity convention.

## Before you start

Read `docs/module-implementation/implementation.md` (config-bearing modules).

## Goal

Add a `Config` class to `ParseSuiteConfigMod` with a single field `prefix_suite:bool = False`. When true, each `TestConfig` is constructed with `key=f"{suite_name}/{t.name}"` (where `suite_name = path.parent.name`) instead of leaving `key` empty for `__post_init__` to default. When false (test/randtest), behaviour is unchanged.

## Why config-driven

The suite name distinguishes same-named tests across suites and groups the summary table by suite. The correlation key becomes `<suite>/<test>#<sweep>#<run>`. A separate `stamp-suite-key` module would add a node, an edge, and a contract config for something that amounts to one conditional at construction time.

The suite name is the directory name of `suite_dir` — matching rtl_buddy's convention where the suite identity is the directory containing `tests.yaml`. If a project has suites in directories with the same leaf name (e.g. `a/verif/tests.yaml` and `b/verif/tests.yaml`), both stamp as `verif/<test>`. Collision is unlikely in practice (rtl_buddy has the same limitation).

## Surface

```
contract:          unit (test/randtest) or default (regression) — contract-agnostic
config:            prefix_suite:bool = False
inputs:            unchanged — test_config:str = "tests.yaml"
outputs:           unchanged — default → SuiteConfig
```

```python
class ParseSuiteConfigMod:
    @serde
    class Config:
        prefix_suite:bool = False

    def __init__(self, config):
        self.prefix_suite = config.prefix_suite

    def run(self, test_config:str = "tests.yaml"):
        path = Path(test_config).resolve()
        # ... existing error handling (unchanged) ...
        tbs = { tb.get_name(): tb for tb in raw.testbenches }
        suite_name = path.parent.name
        tests = {}
        for t in raw.tests:
            try:
                tb = tbs[t.tb]
            except KeyError as e:
                log.fatal("unknown_testbench", path=str(path), test=t.name, testbench=t.tb, exc_info=e)
            key = f"{suite_name}/{t.name}" if self.prefix_suite else ""
            tests[t.name] = TestConfig(name=t.name, desc=t.desc, model=t.model, model_path=t.model_path, reglvl=t.reglvl, pa=t.pa, pd=t.pd, uvm=t.uvm, preproc_path=t.preproc_path, postproc_path=t.postproc_path, sweep_path=t.sweep_path, tb=tb, timeout=t.timeout, suite_dir=path.parent, key=key)
        suite_cfg = SuiteConfig(path=path, tests=tests)
        return ("default", suite_cfg)
```

## Changes to existing code

The only changes to `ParseSuiteConfigMod`:

1. Add `Config` inner class with `prefix_suite:bool = False`.
2. Add `__init__(self, config)` storing `self.prefix_suite`.
3. In the test loop, set `key = f"{suite_name}/{t.name}" if self.prefix_suite else ""`.

When `prefix_suite` is false and `key=""`, `TestConfig.__post_init__` sets `key = self.name` — identical to the current behaviour. Existing test/randtest graphs pass no config, so `prefix_suite` defaults to `False`. The module keeps its single-return form — no output-shape change.

## `parse-suite` in the regression graph

```yaml
- id: parse-suite
  module: { name: parse-suite-config, config: { prefix_suite: true } }
  contract: default
```

Two per-graph differences: **contract** switches from `unit` to `default` (runs once per `Path` from `parse-reg-config`), and **config** adds `prefix_suite: true`. The `EndSentinel` from `parse-reg-config` propagates through the `default` contract into the downstream pipeline, draining it correctly.

## Tests

In `modules/tests/test_setup.py`.

- `prefix_suite=False` (default) — `test.key` defaults to `test.name` via `__post_init__` (unchanged behaviour).
- `prefix_suite=True`, suite at `Path("/a/b/sandbox/tests.yaml")` — `test.key == "sandbox/<test_name>"` for each test.
- Existing tests (no config) continue to pass — `prefix_suite` defaults to `False`.

## Acceptance criteria

- All three test cases pass.
- Existing test and randtest graphs (no `config` block) are unaffected — `prefix_suite` defaults to `False`.
- With `prefix_suite=True`, the key is `<suite_dir.name>/<test_name>`.
- The module remains contract-agnostic: it runs under both `unit` and `default` without change.

## Constraints

- **Backwards-compatible.** No existing graph breaks. The default (`prefix_suite=False`) preserves current behaviour exactly.
- **No output-shape change.** The module still returns a single `("default", SuiteConfig)`. The key difference is inside the `TestConfig` objects.
- **No separate module.** The prefixing is a construction-time concern, not a transform worth its own node.
