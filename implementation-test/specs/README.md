# Implementation specs

Self-contained, dependency-ordered tickets for building the `test` graph and its modules.
Each spec is a buildable unit; pick them up in order. The plan files in the parent
directory (`../00`–`../07`) are the reference — specs point into them rather than duplicate.

Sibling graphs (`randtest`, `regression`) are **not deliverables** of this plan.
[`../08-sibling-graphs.md`](../08-sibling-graphs.md) is a modularity analysis showing the
extension cost: 1 new module for `randtest`, 2 new modules + 1 contract switch for
`regression`, with the rest of the catalogue reused unchanged.

> **Compatibility sources.** Each module ticket carries a `Compatibility source:` bullet
> naming the rtl_buddy file:line it mirrors — copied from the inline `Source:` line in
> [`../03-module-catalog.md`](../03-module-catalog.md). All ranges are anchored to rtl_buddy
> **`v1.4.0`** (commit `a69d962`; see [`../00`](../00-overview.md)). If rtl_buddy is updated,
> re-verify every cited range in the catalog and propagate the change here.

## Priority order

| # | Spec | Depends on | Notes |
|---|---|---|---|
| 01 | [shared-schema](01-shared-schema.md) | — | Reimplemented config dataclasses + `TestResults` + `SeedMode`. |
| 01a | [builder-schema](01a-builder-schema.md) | — | `RtlBuilderConfig` + `RtlBuilderConfigOpts` (extracted from 01 per TODO #9; consumed by 05, 07, 08). |
| 01b | [suite-schema](01b-suite-schema.md) | 01c (for `TestConfig.model` annotation) | `SuiteConfig` + `TestConfig` + `TestbenchConfig` + `UVMConfig` (extracted from 01 per TODO #10; consumed by 04, 05, 06, 07, 08, 09). |
| 01c | [model-schema](01c-model-schema.md) | — | `ModelConfig` + `ModelConfigLoader` (extracted from 01 per TODO #10; consumed by 05, 06). |
| 02 | [any-contract-and-fan-in](02-any-contract-and-fan-in.md) | — | `AnyContract` only (plain, reusable; **unwired** in `test`). `FanInResultsMod` removed by TODO #15 — build only if another graph needs it. |
| 03 | [run-process](03-run-process.md) | — | The reusable subprocess star. |
| 04 | [setup-modules](04-setup-modules.md) (index) | 01 | Setup chain + suite parse + seed-mode derivation. Split into 04a–04i. |
| 05 | [selection-expansion-modules](05-selection-expansion-modules.md) (index) | 01 | List routing, select, filter, load-model, sweep. Split into 05a–05f. |
| 06 | [prep-modules](06-prep-modules.md) (index) | 01 | `run-preproc`, `write-filelist`. Split into 06a–06b. |
| 07 | [compile-cycle-modules](07-compile-cycle-modules.md) (index) | 03 | `build-compile-cmd`, `interpret-compile`. Split into 07a–07b. |
| 08 | [sim-cycle-modules](08-sim-cycle-modules.md) (index) | 03 | `expand-runs`, `resolve-seed`, `build-sim-cmd`, `write-randseed`, `link-latest`, `interpret-sim`. Split into 08a–08f. |
| 09 | [post-modules](09-post-modules.md) (index) | 01 | `route-post`, `parse-log`, `parse-uvm-log`. Split into 09a–09c. |
| 10 | [control-aggregate-modules](10-control-aggregate-modules.md) (index) | 01 | `early-stop-gate`, `git-status`, and the `SummaryProcessor` logging plugin (replaces `aggregate-results`, TODO #15). Split into 10a–10c. |
| 11 | [graph-and-manifests](11-graph-and-manifests.md) | 02-10 | `graphs/test.yaml`, plugin manifests, `rtl_comrade_config.yaml` entry. |
| 12 | [end-to-end](12-end-to-end.md) | 11 | Smoke test against a real rtl_buddy suite. |

### Per-module child specs

Specs 04–10 group several modules each; per TODO #17 each is split into one buildable
ticket per module, with the numbered file kept as a thin index. The children can be picked
up independently once their group's deps (above) are met.

| Group | Children |
|---|---|
| 04 (setup) | [04a discover-config-file](04a-discover-config-file.md) · [04b prepend-cwd-path](04b-prepend-cwd-path.md) · [04c parse-root-config](04c-parse-root-config.md) · [04d select-platform](04d-select-platform.md) · [04e resolve-builder](04e-resolve-builder.md) · [04f check-suite-cwd](04f-check-suite-cwd.md) · [04g ensure-logs-dir](04g-ensure-logs-dir.md) · [04h parse-suite-config](04h-parse-suite-config.md) · [04i derive-seed-mode](04i-derive-seed-mode.md) |
| 05 (selection/expansion) | [05a route-list-mode](05a-route-list-mode.md) · [05b list-test-names](05b-list-test-names.md) · [05c select-tests](05c-select-tests.md) · [05d filter-reglvl](05d-filter-reglvl.md) · [05e load-model](05e-load-model.md) · [05f expand-sweep](05f-expand-sweep.md) |
| 06 (prep) | [06a run-preproc](06a-run-preproc.md) · [06b write-filelist](06b-write-filelist.md) |
| 07 (compile cycle) | [07a build-compile-cmd](07a-build-compile-cmd.md) · [07b interpret-compile](07b-interpret-compile.md) |
| 08 (sim cycle) | [08a expand-runs](08a-expand-runs.md) · [08b resolve-seed](08b-resolve-seed.md) · [08c build-sim-cmd](08c-build-sim-cmd.md) · [08d write-randseed](08d-write-randseed.md) · [08e link-latest](08e-link-latest.md) · [08f interpret-sim](08f-interpret-sim.md) |
| 09 (post) | [09a route-post](09a-route-post.md) · [09b parse-log](09b-parse-log.md) · [09c parse-uvm-log](09c-parse-uvm-log.md) |
| 10 (control/summary) | [10a early-stop-gate](10a-early-stop-gate.md) · [10b git-status](10b-git-status.md) · [10c summary-handler](10c-summary-handler.md) |

Within a group the children are independent except for shared-file ordering and the
explicit `Depends on:` lines each child carries: 05f/06a share the `exec_hook` helper; 06b
feeds 07a; 07a sets `ctx["simv"]` for 07b and 08c; 08c feeds 08d, which feeds 08e/08f;
10a/10b emit the events 10c collects.

Specs 01, 01a, 01b, 01c, 02, and 03 can all run in parallel from the start (01b has a
type-annotation dependency on 01c but no logic dependency; 02 has no external blocker).
Specs 04, 05, 06, 09, 10 (and their children) can run
in parallel after their listed deps. Specs 07 and 08 share `run-process` (spec 03)
and reuse modules from 04/05/06. Schema fan-in: 01a → 05/07/08; 01b →
04/05/06/07/08/09; 01c → 05/06.

(Spec 00 — framework verification — was retired on 2026-06-02. Its three probes
(`**kwargs` port inference, persistent-without-edge, `keyed_join` payload unwrap) were
all settled by reading the harness docs/source. See
[07](../07-ambiguities-and-assumptions.md) Settled items 19, 21, 22.)
