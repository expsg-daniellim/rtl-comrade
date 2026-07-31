# Spec 10: dirname (`DirnameMod`)

**Depends on:** nothing — the module is domain-agnostic.
**References:** `modules/funcs.py` (the generic-module file it joins), [`docs/contracts/unit.md`](../docs/contracts/unit.md) (the contract it runs under), `modules/rtl_buddy/setup.py` (`WorkDirMod`, the existing directory-producing node); consumer: [filelist-normalise](03-filelist-normalise.md)'s `base_dir`.

## Before you start

Read `docs/module-implementation/implementation.md` (input-port inference, output forms) and `modules/funcs.py`. This is a generic module in the same sense as `add` and `alu` — it names no domain type and knows nothing about filelists.

## Goal

Emit the directory component of a path. Nothing else: no existence check, no resolution, no `mkdir`.

The pipeline needs it because [filelist-normalise](03-filelist-normalise.md) takes a `base_dir` to relativise against, and in the `filelist` command that directory is the directory of the CLI `output_path` — a value no node produces. `work-dir` is the analogous producer in the `test` graph, and it is a node for the same reason.

## Surface

```
contract:          unit
inputs:            path:str|Path
outputs:           default → Path   (the directory component)
```

```python
class DirnameMod:
    def run(self, path:str|Path):
        return ("default", Path(path).parent)
```

The contract is a per-node graph choice. The `filelist` command uses `unit`; the `test` graph uses `keyed_join` + `unwrap`, because the node receives `KeyedValue`-wrapped data and is generic — it must not touch envelopes, so the contract does the unwrap and rewrap.

## Algorithm

1. `Path(path).parent`.

`PurePath.parent` is what makes this a one-liner: a bare filename yields `Path(".")` rather than the empty string `os.path.dirname` returns, so the result is always a usable directory. rtl_buddy reaches the same result with the `os.path.dirname(x) or "."` idiom, written out twice on one line (`vlog_filelist.py:143`).

## Deliverables

- `DirnameMod` in `modules/funcs.py`, alongside `AddMod` and `ALUMod`.
- **Manifest** — `{ name: dirname, class_name: DirnameMod }` in the `- file: funcs.py` block of `modules/config.yaml`.
- No `Config` class, no contract.

## Tests

In `modules/tests/test_funcs.py`:

- `"build/run.f"` → `Path("build")`.
- `"run.f"` → `Path(".")` — the bare-filename case, where `os.path.dirname` would give `""`.
- `"/abs/dir/run.f"` → `Path("/abs/dir")`.
- A `Path` input as well as a `str` → same result, so the port accepts either.

## Acceptance criteria

- Tests pass.
- The output is always a usable directory, `Path(".")` for a bare filename.
- `dirname` → `DirnameMod` resolves in the manifest.
- Wired into [filelist-normalise](03-filelist-normalise.md)'s `base_dir` from the `filelist` command's `output_path`, entries relativise against the output file's own directory.

## Constraints

- **Path arithmetic only.** No `exists()`, no `resolve()`, no `mkdir()` — the value is derived from the string, and a directory that does not exist is still a valid answer.
- **No config.** The operation has no parameters; a node that needed to pick a component would be a different node.
- **Domain-agnostic.** Lives in `modules/funcs.py`, names no `rtl_buddy` type, and is not part of the seven pipeline nodes ([spec 02 Deliverables](02-filelist-extract.md#deliverables)).
