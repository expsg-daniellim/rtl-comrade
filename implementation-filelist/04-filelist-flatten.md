# Spec 04: filelist-flatten (`FilelistFlattenMod`)

**Depends on:** [spec 03](03-filelist-normalise.md) (`entries` input, already base-relative).
**References:** pipeline overview [00-overview](00-overview.md#why-this-pipeline-exists).

## Before you start

Read `docs/module-implementation/implementation.md`. This is one of the three transforms that were baked booleans in the fused node (`flatten`/`strip`/`deduplicate`) and are now composable nodes — wired in only when a command wants them. Native reimplementation of the `flatten` branch of `VlogFilelist._process`.

## Goal

Optional transform: reduce each entry's path to its basename. Wired only in the `filelist` graph, behind a [flag-gate](09-flag-gate.md) on `--flatten/-f`.

## Ordering

Must sit **after** `filelist-normalise`: `flatten` is `os.path.basename`, which discards the directory, so running it before relativize would leave a bare filename that `relpath` mangles. This ordering constraint is why `normalise` (relativize) and the writer's render are separate endpoint nodes with the optional transforms between them.

## Surface

```
contract:          default   (keyed by test in the test graph; unwired unless requested)
inputs:            entries:list[FilelistEntry]
outputs:           entries → list[FilelistEntry]
```

```python
class FilelistFlattenMod:
    def run(self, entries:list[FilelistEntry]):
        out = [ e if e.option == "+libext+" else FilelistEntry(os.path.basename(e.path), e.option)
                for e in entries ]
        yield ("entries", out)
```

## Algorithm

Port the `flatten` branch of `_process` (`vlog_filelist.py:122`): `line_path = os.path.basename(line_path)`. `+libext+` entries pass through untouched (the value is not a path).

## Deliverables

- `FilelistFlattenMod` — `(entries)` → `("entries", …)`. In `modules/rtl_buddy/build.py`.
- **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_filelist.py:122` (`flatten` branch).
- Manifest `{ name: filelist-flatten, class_name: FilelistFlattenMod }` (with the pipeline — [spec 02](02-filelist-extract.md#deliverables)).

## Tests

In `modules/tests/test_prep.py`:

- Entries `("a/b/c.sv", None)`, `("a/b/inc", "+incdir+")` etc. → paths become basenames (`c.sv`, `inc`), options preserved.
- `+libext+` entry passes through unchanged.

## Acceptance criteria

- Tests pass; each non-`+libext+` path is `basename`d, options unchanged.
- `filelist-flatten` → `FilelistFlattenMod` resolves in the manifest.

## Constraints

- Basename only — no relpath (spec [03](03-filelist-normalise.md)), no option-drop (spec [05](05-filelist-strip.md)).
- Composable/optional: no boolean in this module. The graph decides — by wiring where the choice is known at load time, by a [flag-gate](09-flag-gate.md) where it is a runtime flag (`--flatten/-f`, `rtl_buddy.py:445`).
- Keep `entries` **non-defaulted**: a default makes the port non-gating, which stops the gate's arm label propagating through this node and breaks the downstream rejoin ([spec 09](09-flag-gate.md#rejoining-the-arms)).
- `+libext+` untouched. Reimplement natively; never import rtl_buddy's `VlogFilelist`.
