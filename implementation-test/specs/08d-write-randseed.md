# Spec 08d: write-randseed (`WriteRandseedMod`)

**Depends on:** spec 03 (run-process — `proc`), spec [08c](08c-build-sim-cmd.md) (`randseed`).
**References:** [03 — Simulation section](../03-module-catalog.md), [04 — keyed_join paragraph](../04-pipeline-and-contracts.md), [02 — Shape 2](../02-payload-conventions.md). Parent index: [idx-08 — Sim-cycle modules](../idx-08-sim-cycle.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)` signature, the allowed output forms (plain return / named-port tuple / generator), the `finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py` are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit `a69d962`). This module appends to `modules/rtl_buddy/sim.py`, which is created by spec [`08a`](08a-expand-runs.md) — append, do not overwrite. The file is shared with the sim-cycle modules (`08a`–`08f`, index [idx-08](../idx-08-sim-cycle.md)) and the post modules (`09a`–`09c`, index [idx-09](../idx-09-post.md)); coordinate shared imports and helpers with those specs.

## Goal

Write the `.randseed` file (persist the seed record) — a side-effect leaf. `test_run` is dissolved in the post-sim split, so this node no longer assembles a result bundle; it `keyed_join`s `randseed` + a `proc` completion gate and emits a `randseed_done` ordering signal.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry — the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract:        keyed_join
contract_config: key_field: key
inputs:          randseed, proc   (joined by key; proc is a completion gate, not read)
outputs:         randseed_done → {key}   (ordering signal for link-latest)
```

```python
class WriteRandseedMod:
    def run(self, randseed, proc):   # proc joined as a completion gate (rc/timed_out unread)
        Path(randseed["randseed_path"]).write_text(f"{randseed['seed']}\n")
        if "hier_inst_seed" in randseed["argv"]:   # rtl_buddy membership check against the sim argv
            with open("HierInstanceSeed.txt") as f:
                Path(randseed["randseed_path"]).open("a").writelines(f)
        return ("randseed_done", { "key": randseed["key"] })   # side-effect leaf; no test_run assembly
```

## Algorithm

1. Write the seed line: `Path(randseed["randseed_path"]).write_text(f"{randseed['seed']}\n")`. The directory already exists (`ensure-logs-dir`); this module does not `mkdir`. `proc` is joined only as a **completion gate** — the sim must have run before the conditional append below — and is otherwise unread (`rc`/`timed_out` are the classification branch's concern, not this one).
2. **Hier-instance seed (conditional).** If `"hier_inst_seed" in randseed["argv"]` — the membership check rtl_buddy performs against the sim argv — append the contents of `HierInstanceSeed.txt` (read from CWD, line by line) to the `.randseed` file. The argv reaches this node on the `randseed` keyed edge (`build-sim-cmd` carries it there for exactly this check — spec 08c).
3. Emit the ordering signal `("randseed_done", {"key": randseed["key"]})` — `link-latest` sequences after it (so `test.randseed` points at a written file). **This node does not assemble `test_run`**: it is a side-effect leaf (write the seed record), nothing more. It reads neither `test` nor `run_id` (they aren't its inputs).

No port-routed failure path. An `OSError` writing the `.randseed` would be surprising (the directory exists) and is left to propagate; a missing `HierInstanceSeed.txt` when the argv asks for it mirrors rtl_buddy's unguarded `open` and likewise propagates.

## Deliverables

In `modules/rtl_buddy/sim.py`:

- `WriteRandseedMod` — `(randseed, proc)`, 2-port `keyed_join`; writes `randseed["randseed_path"]` from `randseed["seed"]`, then appends `HierInstanceSeed.txt` contents when `"hier_inst_seed" in randseed["argv"]`; emits the `randseed_done` ordering signal. **Side-effect leaf — does not assemble `test_run`** (its function is "persist the seed record", per the atomicity fix; `test_run` is dissolved in the post-sim split). `proc` is joined only as a completion gate (unread). The directory was materialised at startup by `ensure-logs-dir`; this module does not `mkdir`. The pre-composed paths/seed/argv arrive on the `randseed` keyed edge from `build-sim-cmd` (spec 08c).
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:263-269` — the `.randseed` write (+ `HierInstanceSeed.txt`) in `VlogSim.execute`.

**Manifest** — append to the `- file: rtl_buddy/sim.py` block in `modules/config.yaml` (opened by [`08a`](08a-expand-runs.md); append, don't re-create):

```yaml
  - { name: write-randseed, class_name: WriteRandseedMod }
```

## Tests

In `modules/tests/test_sim_cycle.py`. Fixtures: `tmp_path` CWD via `monkeypatch.chdir`; `randseed` (`{key, seed, randseed_path, argv}`) and `proc` dict fixtures; a `HierInstanceSeed.txt` written into CWD for the append cases. Drive `run(randseed, proc)` directly — the 2-port `keyed_join` is the contract's concern.

- `randseed["argv"]` without `hier_inst_seed` → writes `randseed["randseed_path"]` with exactly `f"{randseed['seed']}\n"`, and emits `("randseed_done", {"key": randseed["key"]})` (no `test_run`).
- `randseed["randseed_path"]` under a custom `logs_dir` → the file is written at that exact path (boundary: honours the passed path, never a hard-coded `logs/...`).
- `"hier_inst_seed" in randseed["argv"]` with a `HierInstanceSeed.txt` in CWD → the `.randseed` ends with the seed line **followed by** the `HierInstanceSeed.txt` lines (boundary: conditional append fires).
- `"hier_inst_seed"` absent from `randseed["argv"]` → only the seed line is written and `HierInstanceSeed.txt` is never opened (assert by leaving the file absent and seeing no error).
- `"hier_inst_seed" in randseed["argv"]` but no `HierInstanceSeed.txt` in CWD → the unguarded `open` raises `FileNotFoundError`, propagates uncaught → `pytest.raises(FileNotFoundError)` (boundary: rtl_buddy parity, surprising error not swallowed).

## Acceptance criteria

- Tests pass.
- Output port `randseed_done` exercised: writes `.randseed` to `randseed["randseed_path"]` and emits the ordering signal `{"key": randseed["key"]}` (2-port `keyed_join` of `randseed` + `proc`-gate; **no** `test_run` assembly).
- No port-routed failure path: an `OSError` writing `.randseed` is left to propagate.
- The `modules/config.yaml` manifest entry `{ name: write-randseed, class_name: WriteRandseedMod }` validates and the harness resolves `write-randseed` → `WriteRandseedMod`.
- The `HierInstanceSeed.txt` append fires iff `"hier_inst_seed" in randseed["argv"]` (rtl_buddy parity, `vlog_sim.py:265-269`).

## Constraints

- `keyed_join` contract (`key_field: key`), 2-port join of `randseed` + `proc`. `proc` is a **completion gate** only — unread; `rc`/`timed_out` belong to the classification branch.
- Write the seed line to `randseed["randseed_path"]` (do not hard-code a `logs/...` path); do **not** `mkdir` — `ensure-logs-dir` already created the directory.
- Append `HierInstanceSeed.txt` **iff** `"hier_inst_seed" in randseed["argv"]` (rtl_buddy parity) — never unconditionally.
- No port-routed failure path. An `OSError` writing `.randseed`, or a missing `HierInstanceSeed.txt` when the argv asks for it, propagates uncaught (rtl_buddy parity).
- **Do not assemble `test_run`** — emit only the `("randseed_done", {key})` ordering signal. This is a side-effect leaf; the atomicity fix removed the assembly responsibility.

## Notes

`write-randseed` is a **side-effect leaf**, not an assembler — the earlier "first node that has `proc`+`sim_cmd`+`ctx`, so it builds `test_run`" justification was the atomicity violation the split removed (assembly is not its function; persisting the seed record is). The post-sim region now has **no `test_run` bag** and splits into two parallel branches off `proc`: the **side-effect** branch (`write-randseed` → `link-latest`, sequenced by the `randseed_done` signal) and the **classification** branch (`interpret-sim` → `route-post` → `parse-log`/`parse-uvm-log`, each `keyed_join`ing `test` + `proc`). The two branches are independent and concurrent. Mirror [04 — Why each contract](../04-pipeline-and-contracts.md).
