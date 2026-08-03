# Plan: `randtest` graph

This directory is an **implementation plan**, not code. It describes how to port `rtl_buddy`'s `do_rand_test` command as a sibling graph to the existing `test` graph — one new module, CLI rewiring, removal of list mode.

Read in order:

- [00-overview.md](00-overview.md) — goal, relationship to the `test` graph, the graph delta at a glance, CLI surface, and acceptance criteria.
- [01-derive-randtest-runs.md](01-derive-randtest-runs.md) — `DeriveRandtestRunsMod`: the one new module, collapsing `rnd_cnt`/`rnd_rpt` into `run_ids` + `seed_mode`.
- [02-randtest-graph.md](02-randtest-graph.md) — the `randtest.yaml` graph YAML, node/edge delta from `test.yaml`, command registration, and graph-level tests.

## Priority order

| # | Spec | Depends on | Notes |
|---|---|---|---|
| 01 | [derive-randtest-runs](01-derive-randtest-runs.md) | — | New module. No graph dependency. |
| 02 | [randtest-graph](02-randtest-graph.md) | 01 | Graph YAML, manifest, command registration. Requires the module to be landed. |

Spec 01 has no internal dependencies and can start immediately. Spec 02 is integration — the module spec must land first.
