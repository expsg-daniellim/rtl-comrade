# Spec 08: Sim-cycle modules (index)

**Depends on:** spec 03 (run-process), spec 07 (compile cycle), spec
[01a](01a-builder-schema.md) (`ResolveSeedMod` and `BuildSimCmdMod` consume
`RtlBuilderConfig` methods), spec [01b](01b-suite-schema.md) (`BuildSimCmdMod` reads
`ctx["test"].get_timeout()`, `get_plusargs()`, `get_plusdefines()`).
**References:** [03 — Run expansion + Simulation sections](../03-module-catalog.md), [04 — keyed_join paragraph](../04-pipeline-and-contracts.md).

## Goal

Build the per-run simulate leg: fan out per run-id, resolve the seed, assemble the sim
argv (with log paths in `command` and `seed`/`log`/`randseed_path` carried in `sim_cmd`), run the subprocess,
then write `.randseed` (the second keyed_join), force the `test.*` symlinks, and route
on timeout.

This spec is split into one ticket per module — build them as independent units. All live
in `modules/rtl_test/sim.py`; tests in `modules/tests/test_sim_cycle.py`.

| Ticket | Module | What it does |
|---|---|---|
| [08a](08a-expand-runs.md) | `ExpandRunsMod` | Fan out per run-id. |
| [08b](08b-resolve-seed.md) | `ResolveSeedMod` | Resolve the seed (NEW/DEFAULT/REPLAY). |
| [08c](08c-build-sim-cmd.md) | `BuildSimCmdMod` | Assemble sim argv + timeout. |
| [08d](08d-write-randseed.md) | `WriteRandseedMod` | Write `.randseed`; assemble `test_run` (`keyed_join`). |
| [08e](08e-link-latest.md) | `LinkLatestMod` | Force the `test.*` symlinks. |
| [08f](08f-interpret-sim.md) | `InterpretSimMod` | Route on timeout. |

**Manifest** — these six modules open the `rtl_test/sim.py` block in `modules/config.yaml`; the
post chain (`09a`–`09c`) appends to the same block:

```yaml
- file: rtl_test/sim.py
  plugins:
  - { name: expand-runs,    class_name: ExpandRunsMod }
  - { name: resolve-seed,   class_name: ResolveSeedMod }
  - { name: build-sim-cmd,  class_name: BuildSimCmdMod }
  - { name: write-randseed, class_name: WriteRandseedMod }
  - { name: link-latest,    class_name: LinkLatestMod }
  - { name: interpret-sim,  class_name: InterpretSimMod }
  # + route-post, parse-log, parse-uvm-log (09a-09c)
```

## Acceptance criteria

- Each child ticket's tests pass.
- End-to-end against a real `simv` (or fake): a passing run produces correct log/err/
  randseed files and symlinks; a sleep-and-timeout run produces `rc=4444` and
  `interpret-sim` emits `timeout`.

## Notes

`write-randseed` is the **second** `keyed_join` node (the sim-side join). It holds the
join because it is the first node needing `proc` (for completion signal + rc), `sim_cmd`
(for the pre-composed paths), and `ctx` (for test identity). It assembles `test_run` once;
all downstream nodes (`link-latest`, `interpret-sim`, `gate-sim`, `route-post`,
`parse-log`, `parse-uvm-log`) are single-source `default` on `test_run`. No further joins.
Mirror [04 — Why each contract](../04-pipeline-and-contracts.md).
