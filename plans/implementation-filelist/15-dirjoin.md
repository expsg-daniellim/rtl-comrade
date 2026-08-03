# Spec 15: dirjoin (`DirjoinMod`)

**Depends on:** nothing — the module is domain-agnostic.
**References:** `modules/funcs.py` (the generic-module file it joins), [`docs/contracts/unit.md`](../docs/contracts/unit.md) (the contract it runs under in the `filelist` graph); consumer: [spec 16](16-filelist-graph.md)'s `config-path` node. Analogue: [dirname](10-dirname.md) — same file, same contract choices, inverse operation.

## Before you start

Read `docs/module-implementation/implementation.md` (input-port inference, output forms, the trailing-underscore rule for builtins) and `modules/funcs.py`. This is a generic module in the same sense as `add`, `alu`, and `dirname` — it names no domain type and knows nothing about filelists or model configs.

## Goal

Join a directory `Path` with a name to produce a resolved `Path`. Nothing else: no existence check, no `mkdir`, no resolution beyond the join.

The pipeline needs it because the CLI `model_config` parameter is a bare filename (default `"models.yaml"`) that must be resolved against the process CWD before it can be passed to `load-model` and `model-dir`. In rtl_buddy, `ModelConfigLoader` performs this resolution implicitly; in the graph, `work-dir` provides CWD as a `Path` and `dirjoin` makes the join explicit. The result fans to `load-model.model_path` (which expects `Path`) and `model-dir.path` (which accepts `str | Path`), solving both the type mismatch and the CWD-relative resolution in one node.

## Surface

```
contract:          unit   (in the filelist graph; a per-node graph choice, like dirname)
inputs:            dir_:Path, name:str|Path
outputs:           default → Path   (the joined path)
```

```python
class DirjoinMod:
    def run(self, dir_:Path, name:str|Path):
        return ("default", Path(dir_) / name)
```

`dir_` carries a trailing underscore because `dir` is a Python builtin; the harness exposes the input port as `dir` (the underscore is stripped — see `docs/module-implementation/implementation.md` § Avoiding builtin/keyword clashes). Graph edges write `port: dir`.

The contract is a per-node graph choice. The `filelist` command uses `unit` (two inputs, one invocation). Other graphs may choose differently.

## Algorithm

1. `Path(dir_) / name`.

`Path.__truediv__` handles all the cases: if `name` is absolute, the result is `name` unchanged (Python `pathlib` semantics — an absolute right operand replaces the left); if `name` is relative (the default `"models.yaml"` case), the result is `dir_ / name`. No `resolve()` — the caller (`work-dir`) already provides a resolved CWD, so the output is as resolved as its inputs.

## Deliverables

- `DirjoinMod` in `modules/funcs.py`, alongside `AddMod`, `ALUMod`, and `DirnameMod`.
- **Manifest** — `{ name: dirjoin, class_name: DirjoinMod }` in the `- file: funcs.py` block of `modules/config.yaml`. Already listed in [spec 16](16-filelist-graph.md)'s manifest block.
- No `Config` class, no contract.

## Tests

In `modules/tests/test_funcs.py`:

- `dir_=Path("/work"), name="models.yaml"` → `Path("/work/models.yaml")` — the typical CWD + bare filename case.
- `dir_=Path("/work"), name="sub/models.yaml"` → `Path("/work/sub/models.yaml")` — a relative path with directory components.
- `dir_=Path("/work"), name=Path("/abs/models.yaml")` → `Path("/abs/models.yaml")` — an absolute `name` replaces `dir_` (Python `pathlib` semantics).
- `dir_=Path("/work"), name=Path("models.yaml")` → `Path("/work/models.yaml")` — a `Path` input as well as a `str` → same result, so the port accepts either.

## Acceptance criteria

- Tests pass.
- The output is always a `Path`.
- `dirjoin` → `DirjoinMod` resolves in the manifest.
- Wired as `config-path` in [spec 16](16-filelist-graph.md)'s `filelist` graph, the module resolves `model_config` against CWD and fans the result to `load-model.model_path` and `model-dir.path`.

## Constraints

- **Path arithmetic only.** No `exists()`, no `resolve()`, no `mkdir()` — the value is derived from the inputs, and a path that does not exist is still a valid answer.
- **No config.** The operation has no parameters.
- **Domain-agnostic.** Lives in `modules/funcs.py`, names no `rtl_buddy` type, and is not part of the seven pipeline nodes ([spec 02 Deliverables](02-filelist-extract.md#deliverables)).
- **`dir_` trailing underscore.** The parameter is `dir_` in the Python signature, exposed as port `dir` by the harness's builtin-avoidance rule.
