# Plan: `regression` graph

This directory is an **implementation plan**, not code. It describes how to port `rtl_buddy`'s `do_rtl_regression` command as a sibling graph to the existing `test` graph — multiple suites, per-suite working directories, level filtering, suite-key prefixing, and the `work_dir`/`logs_dir` persistent-to-keyed migration.

Read in order:

- [00-overview.md](00-overview.md) — goal, relationship to the `test` graph, the graph delta at a glance, CLI surface, structural notes, and acceptance criteria.
- [01-resolve-reg-config-path.md](01-resolve-reg-config-path.md) — `ResolveRegConfigPathMod`: bridge the CLI `reg_config` default to `root_cfg.cfg_rtl_reg.path`.
- [02-parse-reg-config.md](02-parse-reg-config.md) — `ParseRegConfigMod`: deserialise `regressions.yaml` and yield one `Path` per suite config entry.
- [03-suite-key-prefix.md](03-suite-key-prefix.md) — `ParseSuiteConfigMod` config change: `prefix_suite:bool` to stamp `<suite>/<test>` keys.
- [04-extract-suite-dir.md](04-extract-suite-dir.md) — `ExtractSuiteDirMod`: per-suite `work_dir`, `base_dir`, and `logs_dir` extraction, replacing `work-dir` and `ensure-logs`.
- [05-regression-graph.md](05-regression-graph.md) — the `regression.yaml` graph YAML, node/edge delta from `test.yaml`, command registration, and graph-level tests.

## Priority order

| # | Spec | Depends on | Notes |
|---|---|---|---|
| 01 | [resolve-reg-config-path](01-resolve-reg-config-path.md) | — | New module. No graph dependency. |
| 02 | [parse-reg-config](02-parse-reg-config.md) | — | New module. No graph dependency. |
| 03 | [suite-key-prefix](03-suite-key-prefix.md) | — | Change to existing module. Backwards-compatible. |
| 04 | [extract-suite-dir](04-extract-suite-dir.md) | — | New module. No graph dependency. |
| 05 | [regression-graph](05-regression-graph.md) | 01, 02, 03, 04 | Graph YAML, manifest, command registration. Requires all module specs to be landed. |

Specs 01–04 have no internal dependencies and can run in parallel from the start. Spec 05 is integration — all module specs must land first.
