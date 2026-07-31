# Spec 06: filelist-dedup (`FilelistDedupMod`)

**Depends on:** [spec 03](03-filelist-normalise.md) (`entries` input).
**References:** pipeline overview [00-overview](00-overview.md#why-this-pipeline-exists).

## Before you start

Read `docs/module-implementation/implementation.md`. Third of the three ex-boolean transforms now composable as nodes. Native reimplementation of the `deduplicate` branch of `VlogFilelist._process`.

## Goal

Optional transform: drop duplicate entries, keeping first occurrence and order. `test`/`randtest`/`regression` wire it unconditionally (matching `VlogSim`'s `deduplicate=True`); the `filelist` graph wires it behind a [flag-gate](09-flag-gate.md) on `--deduplicate/-d`.

## Ordering

Must sit **after** `filelist-flatten`/`filelist-strip` (when those are wired): both create new duplicates (two paths sharing a basename collide after flatten; two entries differing only in option collide after strip). Deduping earlier would miss those. So dedup is the **last** transform before the writer.

## Surface

```
contract:          default   (keyed by test in the test graph)
inputs:            entries:list[FilelistEntry]
outputs:           entries → list[FilelistEntry]
```

```python
class FilelistDedupMod:
    def run(self, entries:list[FilelistEntry]):
        seen, out = set(), []
        for entry in entries:
            if entry in seen:
                continue
            seen.add(entry)
            out.append(entry)
        yield ("entries", out)
```

## Algorithm

rtl_buddy dedups on the *rendered line string* (`vlog_filelist.py:128-130`). After `normalise`/`flatten`/`strip`, an entry's `(path, option)` tuple maps one-to-one onto its rendered line (render is deterministic — spec [07](07-write-filelist.md)), so deduping on the tuple is equivalent and needs no rendering here. Keep first occurrence; preserve order (`set` for membership, list for output).

## Deliverables

- `FilelistDedupMod` — `(entries)` → `("entries", …)`. In `modules/rtl_buddy/build.py`.
- **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_filelist.py:128-130` (`deduplicate` branch).
- Manifest `{ name: filelist-dedup, class_name: FilelistDedupMod }` (with the pipeline — [spec 02](02-filelist-extract.md#deliverables)).

## Tests

In `modules/tests/test_prep.py`:

- Entries with a repeated `(path, option)` → one copy kept, first-occurrence order preserved.
- Two entries same path, different option → both kept (dedup is on the full entry, matching the rendered line).
- After a wired `filelist-flatten`, two entries whose basenames now collide → deduped (ordering rationale: dedup runs last).

## Acceptance criteria

- Tests pass; duplicates dropped on the full `(path, option)`, order stable.
- With `test`-graph wiring (`normalise → dedup`, no flatten/strip), output matches rtl_buddy's `_process(deduplicate=True)` on the same entries.
- `filelist-dedup` → `FilelistDedupMod` resolves in the manifest.

## Constraints

- Dedup only — no path rewrite, no rendering.
- Wire **last** among the transforms (after flatten/strip), so post-transform duplicates are caught.
- Composable/optional: no boolean in this module. The graph decides — wired in unconditionally for `test`/`randtest`/`regression` (`vlog_sim.py:93`), behind a [flag-gate](09-flag-gate.md) for the `filelist` command's per-invocation `--deduplicate/-d` (`rtl_buddy.py:447`).
- Keep `entries` **non-defaulted**: a default makes the port non-gating, which stops the gate's arm label propagating through this node and breaks the downstream rejoin ([spec 09](09-flag-gate.md#rejoining-the-arms)).
- Reimplement natively; never import rtl_buddy's `VlogFilelist`.
