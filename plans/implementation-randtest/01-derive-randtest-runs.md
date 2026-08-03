# Spec 01: derive-randtest-runs (`DeriveRandtestRunsMod`)

**Depends on:** nothing — the module is self-contained.
**References:** [00-overview](00-overview.md); `rtl_buddy/src/rtl_buddy/rtl_buddy.py:213-243` — `do_rand_test` CLI signature and `rnd_rpt`/`rnd_cnt` to run-id list + seed mode derivation.

## Before you start

Read `docs/module-implementation/implementation.md` (input-port inference, output forms).

## Goal

Collapse the `rnd_cnt`/`rnd_rpt` CLI pair into the two values the downstream pipeline needs: a `run_ids` list for `expand-runs` and a `seed_mode` for `resolve-seed`. This replaces `test.yaml`'s `derive-seed-mode` node, which takes two booleans (`rnd_new`/`rnd_last`) — a different CLI surface driving the same downstream nodes.

## Surface

```
contract:          unit
inputs:            rnd_cnt:int = 2, rnd_rpt:int = -1
outputs:           ("run_ids", list[int]), ("seed_mode", SeedMode)
```

```python
class DeriveRandtestRunsMod:
    def run(self, rnd_cnt:int = 2, rnd_rpt:int = -1):
        if rnd_rpt >= 0:
            yield ("run_ids", [rnd_rpt])
            yield ("seed_mode", SeedMode.REPLAY)
        else:
            yield ("run_ids", list(range(1, rnd_cnt + 1)))
            yield ("seed_mode", SeedMode.NEW)
```

## Algorithm

1. If `rnd_rpt >= 0`: replay mode — emit `run_ids = [rnd_rpt]` (single run) and `seed_mode = SeedMode.REPLAY`.
2. Else: new-seed mode — emit `run_ids = [1, 2, ..., rnd_cnt]` and `seed_mode = SeedMode.NEW`.

## Sentinel convention

`rnd_rpt = -1` is the absent sentinel — the harness's primitive-only CLI edges cannot represent `None`, so a negative value stands in. Any negative value is treated as absent. rtl_buddy uses `rnd_rpt = None`; the mapping is at the CLI edge level.

## `run_ids` is config, not stream

The list is a fixed, startup-known, small-cardinality set (typically single-digit `rnd_cnt`). The streaming fan-out happens downstream at `expand-runs`, which takes the whole list and yields one edge-set per run-id per compiled test.

## Deliverables

- `DeriveRandtestRunsMod` in `modules/rtl_buddy/setup.py`.
- **Manifest** — append to the `- file: rtl_buddy/setup.py` block in `modules/config.yaml`:
  ```yaml
    - { name: derive-randtest-runs, class_name: DeriveRandtestRunsMod }
  ```

## Tests

In `modules/tests/test_setup.py`. Pure function — no fixtures needed.

- `(rnd_cnt=2, rnd_rpt=-1)` → yields `("run_ids", [1, 2])`, `("seed_mode", SeedMode.NEW)`.
- `(rnd_cnt=5, rnd_rpt=-1)` → yields `("run_ids", [1, 2, 3, 4, 5])`, `("seed_mode", SeedMode.NEW)`.
- `(rnd_cnt=2, rnd_rpt=3)` → yields `("run_ids", [3])`, `("seed_mode", SeedMode.REPLAY)`.
- `(rnd_cnt=2, rnd_rpt=0)` → yields `("run_ids", [0])`, `("seed_mode", SeedMode.REPLAY)` (boundary: zero is a valid replay index).
- `()` (defaults) → yields `("run_ids", [1, 2])`, `("seed_mode", SeedMode.NEW)`.

## Acceptance criteria

- All five test cases pass.
- `derive-randtest-runs` → `DeriveRandtestRunsMod` resolves in the manifest.
- `rnd_rpt = 0` is treated as replay, not absent.
- `rnd_rpt` negative → new-seed mode with `rnd_cnt` run IDs.

## Docs

Add a `docs/modules/derive-randtest-runs.md` page and update `docs/modules/index.md` to include it. Follow `docs/creating-documentation.md` and `docs/modules/doc-structure.md`.

## Constraints

- **No graph knowledge.** The module does not know about `expand-runs`, `resolve-seed`, or the graph; it transforms two integers into two outputs.
- **Contract: `unit`.** Both inputs arrive once from CLI edges; the module fires once.
- **`SeedMode` is imported**, not defined here — it already exists in the codebase from `derive-seed-mode`.
