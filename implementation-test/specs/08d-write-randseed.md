# Spec 08d: write-randseed (`WriteRandseedMod`)

**Depends on:** spec 03 (run-process), spec [08c](08c-build-sim-cmd.md) (`sim_cmd`).
**References:** [03 — Simulation section](../03-module-catalog.md),
[04 — keyed_join paragraph](../04-pipeline-and-contracts.md),
[02 — Shape 2](../02-payload-conventions.md). Parent index:
[08 — Sim-cycle modules](08-sim-cycle-modules.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)`
signature, the allowed output forms (plain return / named-port tuple / generator), the
`finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py`
are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry
below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit
`a69d962`). This module appends to `modules/rtl_test/sim.py`, shared with the sim-cycle modules
(`08a`–`08f`, index [08](08-sim-cycle-modules.md)) and the post modules (`09a`–`09c`, index
[09](09-post-modules.md)); coordinate shared imports and helpers with those specs.

## Goal

Write the `.randseed` file and assemble the `test_run` payload — the second `keyed_join`
node (the sim-side join).

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry —
the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract:        keyed_join
contract_config: key_field: key
inputs:          ctx, proc, sim_cmd   (3-port join by key)
outputs:         default → test_run
```

```python
class WriteRandseedMod:
    def run(self, ctx, proc, sim_cmd):
        Path(sim_cmd["randseed_path"]).write_text(f"{sim_cmd['seed']}\n")
        if "hier_inst_seed" in sim_cmd["argv"]:   # rtl_buddy membership check against the sim argv
            with open("HierInstanceSeed.txt") as f:
                Path(sim_cmd["randseed_path"]).open("a").writelines(f)
        return ("default", {
            "key": ctx["key"], "test": ctx["test"], "run_id": ctx["run_id"],
            "rc": proc["rc"], "timed_out": proc["timed_out"],
            "log": sim_cmd["log"], "err": sim_cmd["err"], "randseed_path": sim_cmd["randseed_path"],
        })
```

## Algorithm

1. Write the seed line: `Path(sim_cmd["randseed_path"]).write_text(f"{sim_cmd['seed']}\n")`.
   The directory already exists (`ensure-logs-dir`); this module does not `mkdir`.
2. **Hier-instance seed (conditional).** If `"hier_inst_seed" in sim_cmd["argv"]` — the
   membership check rtl_buddy performs against the sim argv — append the contents of
   `HierInstanceSeed.txt` (read from CWD, line by line) to the `.randseed` file. The argv
   reaches this node on the `sim_cmd` keyed port specifically so this check is possible
   (`build-sim-cmd` carries it for that reason — spec 08c). `keyed_join` cannot take a
   persistent input, so the argv must arrive as a keyed field.
3. Assemble and emit the single `test_run` record on `default`, joining `ctx` + `proc` +
   `sim_cmd` by key: `{"key": ctx["key"], "test": ctx["test"], "run_id": ctx["run_id"], "rc":
   proc["rc"], "timed_out": proc["timed_out"], "log": sim_cmd["log"], "err": sim_cmd["err"],
   "randseed_path": sim_cmd["randseed_path"]}`.

No port-routed failure path. An `OSError` writing the `.randseed` would be surprising (the
directory exists) and is left to propagate; a missing `HierInstanceSeed.txt` when the argv
asks for it mirrors rtl_buddy's unguarded `open` and likewise propagates.

## Deliverables

In `modules/rtl_test/sim.py`:

- `WriteRandseedMod` — `(ctx, proc, sim_cmd)`, 3-port `keyed_join`; writes
  `sim_cmd["randseed_path"]` from `sim_cmd["seed"]`, then appends `HierInstanceSeed.txt`
  contents when `"hier_inst_seed" in sim_cmd["argv"]`; assembles and emits `test_run` from
  `ctx` + `proc` + `sim_cmd`. The
  directory was materialised at startup by `ensure-logs-dir`; this module does not
  `mkdir`. `logs_dir` is **not** a persistent input — `keyed_join` joins every port by
  key and cannot carry one; instead `sim_cmd` delivers the pre-composed paths as a keyed
  port (see [02 — Shape 2](../02-payload-conventions.md) and
  [07 Implementation notes](../07-ambiguities-and-assumptions.md)).
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:263-269` — the `.randseed` write (+ `HierInstanceSeed.txt`) in `VlogSim.execute`.

**Manifest** — append to the `- file: rtl_test/sim.py` block in `modules/config.yaml`
(opened by [`08a`](08a-expand-runs.md); append, don't re-create):

```yaml
  - { name: write-randseed, class_name: WriteRandseedMod }
```

## Tests

In `modules/tests/test_sim_cycle.py`:

- `write-randseed` writes to `sim_cmd["randseed_path"]` (not a hard-coded `logs/...`
  path) — exercise with a custom `logs_dir` end-to-end.
- `hier_inst_seed` present: with `"hier_inst_seed"` in `sim_cmd["argv"]` and a
  `HierInstanceSeed.txt` in CWD, the `.randseed` file ends with the seed line **followed by**
  the `HierInstanceSeed.txt` lines; absent from argv, only the seed line is written and
  `HierInstanceSeed.txt` is never opened.

## Acceptance criteria

- Tests pass.
- Writes `.randseed` to `sim_cmd["randseed_path"]` and emits a single assembled `test_run`
  joining `ctx` + `proc` + `sim_cmd` by key.
- The `HierInstanceSeed.txt` append fires iff `"hier_inst_seed" in sim_cmd["argv"]` (rtl_buddy
  parity, `vlog_sim.py:265-269`).

## Constraints

- `keyed_join` contract (`key_field: key`), 3-port join of `ctx` + `proc` + `sim_cmd`. It takes
  **no** persistent input — `keyed_join` joins every port by key and cannot carry one; the
  paths/argv arrive via the `sim_cmd` keyed port.
- Write the seed line to `sim_cmd["randseed_path"]` (do not hard-code a `logs/...` path); do
  **not** `mkdir` — `ensure-logs-dir` already created the directory.
- Append `HierInstanceSeed.txt` **iff** `"hier_inst_seed" in sim_cmd["argv"]` (rtl_buddy parity)
  — never unconditionally.
- No port-routed failure path. An `OSError` writing `.randseed`, or a missing
  `HierInstanceSeed.txt` when the argv asks for it, propagates uncaught (rtl_buddy parity).
- Emit the single assembled `test_run` record on the string-literal `default` port.

## Notes

`write-randseed` is the **second** `keyed_join` node (the sim-side join). It holds the
join because it is the first node needing `proc` (for completion signal + rc), `sim_cmd`
(for the pre-composed paths), and `ctx` (for test identity). It assembles `test_run` once;
all downstream nodes (`link-latest`, `interpret-sim`, `gate-sim`, `route-post`,
`parse-log`, `parse-uvm-log`) are single-source `default` on `test_run`. No further joins.
Mirror [04 — Why each contract](../04-pipeline-and-contracts.md).
