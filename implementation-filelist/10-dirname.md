# Spec 10: dirname (`DirnameMod`)

**Depends on:** nothing — the module is domain-agnostic.
**References:** `modules/funcs.py` (the generic-module file it joins), [`docs/contracts/unit.md`](../docs/contracts/unit.md) (the contract it runs under), `modules/rtl_buddy/setup.py` (`WorkDirMod`, the existing directory-producing node); consumer: [filelist-normalise](03-filelist-normalise.md)'s `base_dir`.

## Before you start

Read `docs/module-implementation/implementation.md` (input-port inference, output forms) and `modules/funcs.py`. This is a generic module in the same sense as `add` and `alu` — it names no domain type and knows nothing about filelists.

## Goal

Emit the directory component of a path: if the path names an existing file, return its parent; if it names an existing directory, return it unchanged; if neither exists, fall back to `Path(path).parent`. Nothing else: no resolution, no `mkdir`.

The pipeline needs it because [filelist-normalise](03-filelist-normalise.md) takes a `base_dir` to relativise against, and in the `filelist` command that directory is the directory of the CLI `output_path` — a value no node produces. `work-dir` is the analogous producer in the `test` graph, and it is a node for the same reason. In the `test` graph, the model root (`fl-model-root`) uses it to extract the directory from a models.yaml path — or return an already-directory path unchanged when `model_path` is empty, matching the fused node's `dirname(abspath(model_path)) if model_path else work_dir` fallback.

## Surface

```
contract:          unit
inputs:            path:str|Path
outputs:           default → Path   (the directory)
```

```python
class DirnameMod:
    def run(self, path:str|Path):
        p = Path(path)
        if p.is_file():
            return ("default", p.parent)
        if p.is_dir():
            return ("default", p)
        return ("default", p.parent)
```

The contract is a per-node graph choice. The `filelist` command uses `unit`; the `test` graph uses `keyed_join` + `unwrap`, because the node receives `KeyedValue`-wrapped data and is generic — it must not touch envelopes, so the contract does the unwrap and rewrap.

## Algorithm

1. `p = Path(path)`.
2. If `p.is_file()` → `p.parent` (the common case: `path` is a file like `models.yaml`, return its directory).
3. If `p.is_dir()` → `p` unchanged (the edge case: `path` is already a directory, no parent-stripping).
4. Otherwise (path does not exist) → `p.parent` (best-effort, matching the file case).

The `is_dir()` guard is what keeps the fused node's fallback (`dirname(model_path) if model_path else work_dir`) parity: when `test.model_path` is empty, `suite_dir / ""` yields `suite_dir` (a directory), and `dirname` returns it unchanged. `PurePath.parent` would yield `suite_dir.parent`, breaking parity. rtl_buddy reaches the analogous result with the `os.path.dirname(x) or "."` idiom (`vlog_filelist.py:143`).

## Deliverables

- `DirnameMod` in `modules/funcs.py`, alongside `AddMod` and `ALUMod`.
- **Manifest** — `{ name: dirname, class_name: DirnameMod }` in the `- file: funcs.py` block of `modules/config.yaml`.
- No `Config` class, no contract.

## Tests

In `modules/tests/test_funcs.py`:

- A file at `tmp_path/"build/run.f"` (committed) → `Path("…/build")` — the file case, returns parent.
- A directory at `tmp_path/"build"` (committed) → that same `Path` unchanged — the directory case.
- `"/nonexistent/run.f"` → `Path("/nonexistent")` — the fallback case (not on disk), returns parent.
- `"run.f"` with no such file on disk → `Path(".")` — bare-filename fallback, where `os.path.dirname` would give `""`.
- `"/abs/dir/run.f"` (not on disk) → `Path("/abs/dir")`.
- A `Path` input as well as a `str` → same result, so the port accepts either.

## Acceptance criteria

- Tests pass.
- A path to a file returns the file's parent; a path to a directory returns it unchanged; a nonexistent path returns its parent.
- `dirname` → `DirnameMod` resolves in the manifest.
- Wired into [filelist-normalise](03-filelist-normalise.md)'s `base_dir` from the `filelist` command's `output_path`, entries relativise against the output file's own directory.

## Constraints

- **Directory extraction only.** No `resolve()`, no `mkdir()`.
- **No config.** The operation has no parameters; a node that needed to pick a component would be a different node.
- **Domain-agnostic.** Lives in `modules/funcs.py`, names no `rtl_buddy` type, and is not part of the seven pipeline nodes ([spec 02 Deliverables](02-filelist-extract.md#deliverables)).
