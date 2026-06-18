# idx-08 — Sim-cycle modules (group index)

> Navigation only — not a build ticket. The buildable units are the child specs under [`specs/`](specs/).

**Depends on:** spec 03 (run-process), spec 07 (compile cycle), spec
[01a](specs/01a-builder-schema.md) (`ResolveSeedMod` and `BuildSimCmdMod` consume
`RtlBuilderConfig` methods), spec [01b](specs/01b-suite-schema.md) (`BuildSimCmdMod` reads
`ctx["test"].get_timeout()`, `get_plusargs()`, `get_plusdefines()`).
**References:** [03 — Run expansion + Simulation sections](03-module-catalog.md), [04 — keyed_join paragraph](04-pipeline-and-contracts.md).

## Goal

Build the per-run simulate leg: fan out per run-id, resolve the seed, assemble the sim
argv (with log paths in `command` and `seed`/`log`/`randseed_path` carried in `sim_cmd`), run the subprocess,
then write `.randseed` (the second keyed_join), force the `test.*` symlinks, and route
on timeout.

This spec is split into one ticket per module — build them as independent units. All live
in `modules/rtl_buddy/sim.py`; tests in `modules/tests/test_sim_cycle.py`.

| Ticket | Module | What it does |
|---|---|---|
| [08a](specs/08a-expand-runs.md) | `ExpandRunsMod` | Fan out per run-id. |
| [08b](specs/08b-resolve-seed.md) | `ResolveSeedMod` | Resolve the seed (NEW/DEFAULT/REPLAY). |
| [08c](specs/08c-build-sim-cmd.md) | `BuildSimCmdMod` | Assemble sim argv + timeout. |
| [08d](specs/08d-write-randseed.md) | `WriteRandseedMod` | Write `.randseed`; assemble `test_run` (`keyed_join`). |
| [08e](specs/08e-link-latest.md) | `LinkLatestMod` | Force the `test.*` symlinks. |
| [08f](specs/08f-interpret-sim.md) | `InterpretSimMod` | Route on timeout. |

**Manifest** — these six modules open the `rtl_buddy/sim.py` block in `modules/config.yaml`; the
post chain (`09a`–`09c`) appends to the same block:

```yaml
- file: rtl_buddy/sim.py
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
- Integration coverage lives in the child tickets' own acceptance criteria (`.log`/`.err`/
  `.randseed` + `test.*` symlinks on a passing run; `rc=4444` → `timeout` port on a
  sleep-and-timeout run); the sim leg is wired and exercised end-to-end in
  [spec 11](specs/11-graph-and-manifests.md) and [spec 12](specs/12-end-to-end.md).
- Every child's `modules/config.yaml` entry validates and resolves: `expand-runs`,
  `resolve-seed`, `build-sim-cmd`, `write-randseed`, `link-latest`, `interpret-sim` each map
  to their `*Mod` class, reusing the shared `run-process` instance (see
  [11](specs/11-graph-and-manifests.md#acceptance-criteria)).
