# Spec 03: filelist-normalise (`FilelistNormaliseMod`)

**Depends on:** [spec 02](02-filelist-extract.md) (the per-source entries), [spec 08 — prioritised-merge](08-prioritised-merge.md) (the fan-in that feeds this node in the `test` graph).
**References:** [implementation-test spec 06b](../implementation-test/specs/06b-write-filelist.md). Pipeline overview: [00-overview](00-overview.md#why-this-pipeline-exists).

## Before you start

Read `docs/modules/implementation.md`. Native reimplementation of the *path-rebase + existence-check* portion of rtl_buddy's `VlogFilelist._process` — **do not import rtl_buddy**.

## Goal

The always-present first transform after the merge: relativise each path against a `base_dir`, and emit the `+incdir+`/`-y ` is-a-dir and source is-a-file existence warnings. It consumes entries as a bare `list[tuple[str, str | None]]` — `KeyedValue` threading is the contract's job, not the module's — and outputs `entries` (not lines) so the optional flatten/strip/dedup nodes can compose after it.

## Where relpath lives

`os.path.relpath` turns a resolved entry into its emitted form → it is a normalise function, keyed off a `base_dir` input, not a resolution step. `filelist-extract` stays a pure resolver; **`filelist-normalise` owns the path rebase.** `base_dir` = `work_dir` in the test graph, the output-file's directory in the `filelist` command. Placement is not forced by dataflow (spec [02](02-filelist-extract.md)'s finding — nothing consumes the intermediate before the write), only by function.

Existence checks belong here too (not in extract): they read the *resolved absolute* path, which is exactly what arrives — and they run **before** relativise/flatten, so a later `flatten` (`basename`) can't hide which real file was missing.

## Contract — per-graph, module is envelope-agnostic

The module takes a bare `list[entry]` and returns a bare `list[entry]`. It never reads or writes `KeyedValue` envelopes — envelope threading is the contract's job.

- **`filelist` graph:** `default` with `persistent_inputs: [base_dir]`. Entries are unkeyed throughout; the module sees bare lists directly.
- **`test`/`randtest`/`regression` graphs:** `keyed_join` with `unwrap: true` and `persistent_inputs: [base_dir]`. Entries arrive as `KeyedValue[list[entry]]` from [prioritised-merge](08-prioritised-merge.md); the contract unwraps to a bare `list[entry]` before calling `run()` and rewraps the output under the assembled key. The module code is identical in both cases.

This replaces the earlier design where the module threaded `entries.value`/`entries.key` itself, which coupled it to `KeyedValue` and broke on the unkeyed data the `filelist` graph produces.

## Surface

```
contract:          per-graph (see Contract section)
inputs:            entries:list[tuple[str, str|None]], base_dir:Path
outputs:           entries → list[tuple[str, str|None]]   (paths base_dir-relative)
```

`entries` is the entry list — bare in the `filelist` graph, unwrapped from `KeyedValue` by `keyed_join` in the `test` graph. `base_dir` is the relativise root, a persistent singleton (`work_dir` in the test graph, the output-file directory in the `filelist` command).

```python
class FilelistNormaliseMod:
    def run(self, entries:list[tuple[str, str|None]], base_dir:Path):
        out = []
        for path, option in entries:
            if option == "+libext+":
                out.append((path, option))
                continue
            if option in ("+incdir+", "-y "):
                if not os.path.isdir(path):
                    log.error("filelist_incdir_not_a_dir", path=str(path))
            elif not os.path.isfile(path):
                log.error("filelist_file_not_found", path=str(path))
            out.append((os.path.relpath(path, base_dir), option))
        yield ("entries", out)
```

## Algorithm

Port the rebase + checks of `VlogFilelist._process` (`vlog_filelist.py:107-120`), taking `base_dir` instead of the implicit CWD:

1. For each `(path, option)` in `entries`:
   - `+libext+` → pass through untouched (the coalesced value is not a path; no relpath, no check). Later render (spec [07](07-write-filelist.md)) emits it verbatim.
   - Existence warning, best-effort: `+incdir+`/`-y ` → `log.error("filelist_incdir_not_a_dir")` if not a dir; any other option → `log.error("filelist_file_not_found")` if not a file. Run continues.
   - Emit `(os.path.relpath(path, base_dir), option)`.
2. rtl_buddy uses bare `os.path.relpath(path)` (CWD-implicit). The `base_dir` argument makes output correct under a relocated `work_dir` and byte-identical when `base_dir == CWD`.

No flatten/strip/dedup/render here — each is a separate node.

## Deliverables

In `modules/rtl_buddy/build.py`, the normalise stage replacing the front of the fused node's `filelist_process`:

- `FilelistNormaliseMod` — `(entries:list[tuple[str, str | None]], base_dir:Path)` → `("entries", list[...])`. Lifts the relpath + existence-check loop from `filelist_process` (`build.py:99-113`), generalising the hard-coded `work_dir` to the `base_dir` port, and dropping the line-rendering/dedup tail (moved to specs [06](06-filelist-dedup.md)/[07](07-write-filelist.md)). `KeyedValue` threading is the contract's job — the module works on bare lists in every graph.
- **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_filelist.py:107-120` — the rebase + existence portion of `_process`.

Manifest entry `{ name: filelist-normalise, class_name: FilelistNormaliseMod }` (registered with the pipeline — see [spec 02 Deliverables](02-filelist-extract.md#deliverables)).

## Tests

In `modules/tests/test_prep.py`:

- Entries with `+incdir+`, source files, a `+libext+` entry as a bare `list[tuple[str, str | None]]`, `base_dir=tmp_path` → each path relativised against `tmp_path`; `+libext+` passed through unchanged; output is a bare `list`.
- **Relpath base_dir, not CWD:** `monkeypatch.chdir(other)`, `base_dir=tmp_path`, entry `tmp_path/"src/a.sv"` → emits `src/a.sv`, not `../…/src/a.sv`. (The byte-parity boundary from 06b moves here.)
- `+incdir+` target not a dir, and a missing source path → `log.error("filelist_incdir_not_a_dir")` / `filelist_file_not_found`, best-effort (entry still emitted, run continues).

## Acceptance criteria

- Tests pass.
- Output paths are `base_dir`-relative; `+libext+` untouched.
- Existence problems log at ERROR without dropping the entry or aborting.
- `filelist-normalise` → `FilelistNormaliseMod` resolves in the manifest.

## Constraints

- **Owns the path rebase and existence checks — nothing else.** No basename (spec [04](04-filelist-flatten.md)), no option-drop (spec [05](05-filelist-strip.md)), no dedup (spec [06](06-filelist-dedup.md)), no line rendering (spec [07](07-write-filelist.md)).
- **Envelope-agnostic.** The module takes and returns bare `list[entry]`. `KeyedValue` threading is the contract's job: `default` in the `filelist` graph, `keyed_join` with `unwrap: true` in the `test` graph. See the Contract section above.
- `base_dir` is a required input port, not a hard-coded `work_dir` — that is what lets `test` pass `work_dir` and `filelist` pass the output directory into the same node.
- Existence checks are `log.error` warnings, best-effort: the entry is still emitted and the run continues. Like extract's resolve error they carry no `key`/`test_name` and are not registered in `graphs/log/summary.py`, so they render no summary row.
- `+libext+` entries pass through untouched.
- Reimplement natively; never import rtl_buddy's `VlogFilelist`.
