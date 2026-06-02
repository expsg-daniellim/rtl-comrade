# Implementation specs

Self-contained, dependency-ordered tickets for building the `test` graph and its modules.
Each spec is a buildable unit; pick them up in order. The plan files in the parent
directory (`../00`–`../07`) are the reference — specs point into them rather than duplicate.

Sibling graphs (`randtest`, `regression` — see [../08-sibling-graphs.md](../08-sibling-graphs.md))
are **out of scope** here; build those after the `test` graph is working end-to-end.

## Priority order

| # | Spec | Depends on | Notes |
|---|---|---|---|
| 01 | [shared-schema](01-shared-schema.md) | — | Reimplemented config dataclasses + `TestResults` + `SeedMode`. |
| 01a | [builder-schema](01a-builder-schema.md) | — | `RtlBuilderConfig` + `RtlBuilderConfigOpts` (extracted from 01 per TODO #9; consumed by 05, 07, 08). |
| 01b | [suite-schema](01b-suite-schema.md) | 01c (for `TestConfig.model` annotation) | `SuiteConfig` + `TestConfig` + `TestbenchConfig` + `UVMConfig` (extracted from 01 per TODO #10; consumed by 04, 05, 06, 07, 08, 09). |
| 01c | [model-schema](01c-model-schema.md) | — | `ModelConfig` + `ModelConfigLoader` (extracted from 01 per TODO #10; consumed by 05, 06). |
| 02 | [merge-contract](02-merge-contract.md) | harness change (see prerequisite) | Only new framework-level code. |
| 03 | [run-process](03-run-process.md) | — | The reusable subprocess star. |
| 04 | [setup-modules](04-setup-modules.md) | 01 | Setup chain + suite parse + seed-mode derivation. |
| 05 | [selection-expansion-modules](05-selection-expansion-modules.md) | 01 | List routing, select, filter, load-model, sweep. |
| 06 | [prep-modules](06-prep-modules.md) | 01 | `run-preproc`, `write-filelist`. |
| 07 | [compile-cycle-modules](07-compile-cycle-modules.md) | 03 | `build-compile-cmd`, `interpret-compile`. |
| 08 | [sim-cycle-modules](08-sim-cycle-modules.md) | 03 | `expand-runs`, `resolve-seed`, `build-sim-cmd`, `write-randseed`, `link-latest`, `interpret-sim`. |
| 09 | [post-modules](09-post-modules.md) | 01 | `route-post`, `parse-log`, `parse-uvm-log`. |
| 10 | [control-aggregate-modules](10-control-aggregate-modules.md) | 02 | `early-stop-gate`, `aggregate-results`. |
| 11 | [graph-and-manifests](11-graph-and-manifests.md) | 02-10 | `graphs/test.yaml`, plugin manifests, `rtl_comrade_config.yaml` entry. |
| 12 | [end-to-end](12-end-to-end.md) | 11 | Smoke test against a real rtl_buddy suite. |

Specs 01, 01a, 01b, 01c, and 03 can run in parallel from the start (01b has a
type-annotation dependency on 01c but no logic dependency). Spec 02 is blocked on
the harness change called out in its
[Prerequisite](02-merge-contract.md#prerequisite). Specs 04, 05, 06, 09, 10 can run
in parallel after their listed deps. Specs 07 and 08 share `run-process` (spec 03)
and reuse modules from 04/05/06. Schema fan-in: 01a → 05/07/08; 01b →
04/05/06/07/08/09; 01c → 05/06.

(Spec 00 — framework verification — was retired on 2026-06-02. Its three probes
(`**kwargs` port inference, persistent-without-edge, `keyed_join` payload unwrap) were
all settled by reading the harness docs/source. See
[07](../07-ambiguities-and-assumptions.md) Settled items 19, 21, 22.)
