# Spec 08d: write-randseed (`WriteRandseedMod`)

**Depends on:** spec 03 (run-process — `proc`), spec [08c](08c-build-sim-cmd.md) (`randseed`).
**References:** [03 — Simulation section](../03-module-catalog.md), [04 — keyed_join paragraph](../04-pipeline-and-contracts.md), [02 — Shape 2](../02-payload-conventions.md). Parent index: [idx-08 — Sim-cycle modules](../idx-08-sim-cycle.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)` signature, the allowed output forms (plain return / named-port tuple / generator), the `finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py` are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit `a69d962`). This module appends to `modules/rtl_buddy/sim.py`, which is created by spec [`08a`](08a-expand-runs.md) — append, do not overwrite. The file is shared with the sim-cycle modules (`08a`–`08f`, index [idx-08](../idx-08-sim-cycle.md)) and the post modules (`09a`–`09c`, index [idx-09](../idx-09-post.md)); coordinate shared imports and helpers with those specs.

## Goal

Write the `.randseed` file (persist the seed record) — a side-effect leaf. It does not assemble a result bundle; it `keyed_join`s `randseed` + a `proc` completion gate and emits a `randseed_done` ordering signal.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry — the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract:          keyed_join
contract_config:   key_field: key
persistent_inputs: [work_dir]
inputs:            randseed, proc, work_dir:Path   (randseed/proc joined by key; proc is a completion gate, not read)
outputs:           randseed_done → {key}   (ordering signal for link-latest)
```

`work_dir` is the artefact base from `work-dir` — the directory the sim ran in (`run-process` `cwd=work_dir`, spec [03](03-run-process.md)) and therefore where it dropped `HierInstanceSeed.txt`. This module reads that file from `work_dir`, not the ambient CWD.

```python
class WriteRandseedMod:
    def run(self, randseed, proc, work_dir):   # proc joined as a completion gate (rc unread); work_dir persistent
        try:
            Path(randseed.randseed_path).write_text(f"{randseed.seed}\n")
            if "hier_inst_seed" in randseed.argv:   # rtl_buddy membership check against the sim argv
                with open(Path(work_dir) / "HierInstanceSeed.txt") as f, Path(randseed.randseed_path).open("a") as out:
                    out.writelines(f)   # read from work_dir (where the sim dropped it), not ambient CWD (rtl_buddy vlog_sim.py:263-269 parity)
        except OSError as e:   # FileNotFoundError (missing HierInstanceSeed.txt) is an OSError subclass
            log.error("randseed_write_failed", key=randseed.key, path=randseed.randseed_path, exc_info=e)
        return ("randseed_done", RandSeedDone(randseed.key))   # ordering signal emitted regardless, so link-latest can't dangle
```

## Algorithm

1. Write the seed line: `Path(randseed.randseed_path).write_text(f"{randseed.seed}\n")`. The directory already exists (`ensure-logs-dir`); this module does not `mkdir`. `proc` is joined only as a **completion gate** — the sim must have run before the conditional append below — and is otherwise unread (`rc` is the classification branch's concern, not this one).
2. **Hier-instance seed (conditional).** If `"hier_inst_seed" in randseed.argv` — the membership check rtl_buddy performs against the sim argv — append the contents of `HierInstanceSeed.txt` (read from `work_dir`, line by line) to the `.randseed` file. `work_dir` is the artefact base (`work-dir`) the sim ran in (`run-process` `cwd=work_dir`), so that is where it wrote `HierInstanceSeed.txt`; do **not** read it from the ambient CWD (rtl_buddy reads it from CWD only because its sim `chdir`'d there — `vlog_sim.py:267`). The argv reaches this node on the `randseed` keyed edge (`build-sim-cmd` carries it there for exactly this check — spec 08c).
3. Emit the ordering signal `("randseed_done", RandSeedDone(randseed.key))` — `link-latest` sequences after it (so `test.randseed` points at a written file). **This node does not assemble a result bundle**: it is a side-effect leaf (write the seed record), nothing more. It reads neither `test` nor `run_id` (they aren't its inputs).

No port-routed failure path, but the module still **catches** its own I/O errors: an `OSError` writing the `.randseed`, or a missing `HierInstanceSeed.txt` when the argv asks for it (a `FileNotFoundError`, an `OSError` subclass), is caught and converted to `log.error("randseed_write_failed", …)` — a deferred per-test failure (the seed record / hier-seed could not be persisted), consistent with the other per-test modules. The `randseed_done` ordering signal is emitted **regardless** so `link-latest`'s join cannot dangle. This diverges from rtl_buddy's unguarded `open` so a raw traceback never escapes `run()`.

## Deliverables

In `modules/rtl_buddy/sim.py`:

- `WriteRandseedMod` — `(randseed, proc, work_dir:Path)`, `keyed_join` joining `randseed` + `proc` by key with `work_dir` as a `persistent_input`; writes `randseed.randseed_path` from `randseed.seed`, then appends `(Path(work_dir) / "HierInstanceSeed.txt")` contents when `"hier_inst_seed" in randseed.argv`; emits the `randseed_done` ordering signal. **Side-effect leaf — does not assemble a result bundle** (its function is "persist the seed record", nothing more). `proc` is joined only as a completion gate (unread); `work_dir` (`work-dir`) is the directory the sim ran in and dropped `HierInstanceSeed.txt` in. The directory was materialised at startup by `ensure-logs-dir`; this module does not `mkdir`. The pre-composed paths/seed/argv arrive on the `randseed` keyed edge from `build-sim-cmd` (spec 08c).
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:263-269` — the `.randseed` write (+ `HierInstanceSeed.txt`) in `VlogSim.execute`. Divergence: `HierInstanceSeed.txt` is read from `work_dir` (where `run-process`'s `cwd=work_dir` put it), not the ambient CWD that rtl_buddy's `chdir`'d sim happened to share.

**Manifest** — append to the `- file: rtl_buddy/sim.py` block in `modules/config.yaml` (opened by [`08a`](08a-expand-runs.md); append, don't re-create):

```yaml
  - { name: write-randseed, class_name: WriteRandseedMod }
```

## Tests

In `modules/tests/test_sim_cycle.py`. Fixtures: `work_dir=tmp_path` passed as the port; `randseed` (`{key, seed, randseed_path, argv}`) and `proc` dict fixtures; a `HierInstanceSeed.txt` written into `work_dir` for the append cases. Drive `run(randseed, proc, work_dir)` directly — the `keyed_join` (randseed + proc) is the contract's concern.

- `randseed.argv` without `hier_inst_seed` → writes `randseed.randseed_path` with exactly `f"{randseed.seed}\n"`, and emits `("randseed_done", RandSeedDone(randseed.key))` (no result bundle).
- `randseed.randseed_path` under a custom `logs_dir` → the file is written at that exact path (boundary: honours the passed path, never a hard-coded `logs/...`).
- `"hier_inst_seed" in randseed.argv` with a `HierInstanceSeed.txt` in `work_dir` → the `.randseed` ends with the seed line **followed by** the `HierInstanceSeed.txt` lines (boundary: conditional append fires, file read from `work_dir`).
- `HierInstanceSeed.txt` is read from `work_dir`, **not** the process CWD: with `monkeypatch.chdir(other)`, `work_dir=tmp_path`, and the file present only in `tmp_path` (absent from `other`) → the append still fires from `tmp_path` (boundary: the read roots on `work_dir`, so a `HierInstanceSeed.txt` in the ambient CWD is ignored).
- `"hier_inst_seed"` absent from `randseed.argv` → only the seed line is written and `HierInstanceSeed.txt` is never opened (assert by leaving the file absent and seeing no error).
- `"hier_inst_seed" in randseed.argv` but no `HierInstanceSeed.txt` in `work_dir` → the `open` raises `FileNotFoundError`, which is **caught** → `log.error("randseed_write_failed", …)` (`logging_handler.failure is True`) and `("randseed_done", RandSeedDone(randseed.key))` is **still** emitted; no exception escapes `run()`.

## Acceptance criteria

- Tests pass.
- Output port `randseed_done` exercised: writes `.randseed` to `randseed.randseed_path` and emits the ordering signal `RandSeedDone(randseed.key)` (2-port `keyed_join` of `randseed` + `proc`-gate; **no** result-bundle assembly).
- No port-routed failure path: an `OSError`/`FileNotFoundError` writing `.randseed` (or appending `HierInstanceSeed.txt`) is caught → `log.error("randseed_write_failed", …)` (deferred per-test failure) and `randseed_done` is still emitted.
- The `modules/config.yaml` manifest entry `{ name: write-randseed, class_name: WriteRandseedMod }` validates and the harness resolves `write-randseed` → `WriteRandseedMod`.
- The `HierInstanceSeed.txt` append fires iff `"hier_inst_seed" in randseed.argv` (rtl_buddy parity, `vlog_sim.py:265-269`).

## Constraints

- `keyed_join` contract (`key_field: key`), joining `randseed` + `proc` by key with `work_dir` as a `persistent_input`. `proc` is a **completion gate** only — unread; `rc` belongs to the classification branch.
- Write the seed line to `randseed.randseed_path` (do not hard-code a `logs/...` path); do **not** `mkdir` — `ensure-logs-dir` already created the directory.
- Append `HierInstanceSeed.txt` **iff** `"hier_inst_seed" in randseed.argv` (rtl_buddy parity) — never unconditionally. Read it from `(Path(work_dir) / "HierInstanceSeed.txt")` — the artefact base the sim ran in (`run-process` `cwd=work_dir`, spec [03](03-run-process.md)) — **not** `open("HierInstanceSeed.txt")` against the ambient CWD.
- No port-routed failure path. An `OSError` writing `.randseed`, or a missing `HierInstanceSeed.txt` when the argv asks for it (a `FileNotFoundError`), is caught and logged at ERROR (deferred per-test failure); `randseed_done` is still emitted regardless. This diverges from rtl_buddy's unguarded `open` so a raw traceback never escapes `run()`.
- **Do not assemble a result bundle** — emit only the `("randseed_done", {key})` ordering signal. This is a side-effect leaf; persisting the seed record is its sole responsibility.

## Notes

`write-randseed` is a **side-effect leaf**, not an assembler — its function is persisting the seed record, not assembly. The post-sim region splits into two parallel branches off `proc`: the **side-effect** branch (`write-randseed` → `link-latest`, sequenced by the `randseed_done` signal) and the **classification** branch (`interpret-sim` → `route-post` → `parse-log`/`parse-uvm-log`, each `keyed_join`ing `test` + `proc`). The two branches are independent and concurrent. Mirror [04 — Why each contract](../04-pipeline-and-contracts.md).
