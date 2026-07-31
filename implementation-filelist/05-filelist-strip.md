# Spec 04: filelist-strip (`FilelistStripMod`)

**Depends on:** [spec 03](03-filelist-normalise.md) (`entries` input).
**References:** pipeline overview [00-overview](00-overview.md#why-this-pipeline-exists).

## Before you start

Read `docs/modules/implementation.md`. Second of the three ex-boolean transforms now composable as nodes. Native reimplementation of the `strip` intent of `VlogFilelist._process` — **fixing a bug in the reference** (see Algorithm).

## Goal

Optional transform: drop the option token from each entry, leaving a bare-path line. Wired only in the `filelist` graph, behind a [flag-gate](09-flag-gate.md) on `--strip/-s`.

## Surface

```
contract:          default   (keyed by test in the test graph; unwired unless requested)
inputs:            entries:list[tuple[str, str|None]]
outputs:           entries → list[tuple[str, str|None]]   (option set to None)
```

```python
class FilelistStripMod:
    def run(self, entries:list[tuple[str, str|None]]):
        out = [ (path, option) if option == "+libext+" else (path, None)
                for path, option in entries ]
        yield ("entries", out)
```

## Algorithm

Set each entry's option to `None` so render (spec [07](07-write-filelist.md)) emits just the path.

**Reference bug — do not reproduce.** rtl_buddy's `_process` (`vlog_filelist.py:126-133`) builds the rendered `line` *before* the `if strip: line_option = ''`, then appends the already-built `line` — so upstream `strip=True` is a silent no-op. Reimplement it to actually drop the option (filling in the incomplete behaviour is a fix, not a divergence to preserve — the option exists to strip, and here it does).

`+libext+` entries pass through untouched — stripping a `+libext+` token would corrupt the coalesced extension line.

## Deliverables

- `FilelistStripMod` — `(entries)` → `("entries", …)`. In `modules/rtl_buddy/build.py`.
- **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_filelist.py:131-132` (the `strip` intent; the reference no-op is corrected here).
- Manifest `{ name: filelist-strip, class_name: FilelistStripMod }` (with the pipeline — [spec 02](02-filelist-extract.md#deliverables)).
- **Divergence entry** — record in `docs/divergences.md` that `--strip` drops the option token, where rtl_buddy renders the line at `vlog_filelist.py:123` before assigning `line_option = ''` (129-130) and appends the already-rendered line, so the upstream flag emits identical output whether or not it is set.

## Tests

In `modules/tests/test_prep.py`:

- Entry `("path/a.sv", "-v ")` → `("path/a.sv", None)`; render then emits `path/a.sv` with no `-v ` prefix (assert the rtl_buddy no-op is fixed — the option is genuinely gone).
- `+libext+` entry passes through unchanged.

## Acceptance criteria

- Tests pass; every non-`+libext+` entry's option is `None` after this node, and the rendered line carries no option prefix.
- `filelist-strip` → `FilelistStripMod` resolves in the manifest.

## Constraints

- Option-drop only — no path rewrite.
- Composable/optional: no boolean in this module. The graph decides — by wiring where the choice is known at load time, by a [flag-gate](09-flag-gate.md) where it is a runtime flag (`--strip/-s`, `rtl_buddy.py:446`).
- Keep `entries` **non-defaulted**: a default makes the port non-gating, which stops the gate's arm label propagating through this node and breaks the downstream rejoin ([spec 09](09-flag-gate.md#rejoining-the-arms)).
- **Actually strip** (fix the reference no-op). `+libext+` untouched. Reimplement natively; never import rtl_buddy's `VlogFilelist`.
