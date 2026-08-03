# Spec 13: filelist-path (`FilelistPathMod`)

**Depends on:** [implementation-test spec 01b](../implementation-test/specs/01b-suite-schema.md) (`TestConfig`), [04f](../implementation-test/specs/04f-work-dir.md) (`work_dir`, the artefact base).
**References:** [spec 07 — write-filelist](07-write-filelist.md) (the consumer; `path` arrives there fully resolved), [implementation-test spec 06b](../implementation-test/specs/06b-write-filelist.md) (where this naming lived before), `modules/rtl_buddy/build.py` (`BuildCompileCmdMod`, which sanitises the same tag).

## Before you start

Read `docs/module-implementation/implementation.md` (input-port inference, output forms). This module carries the per-tag destination naming that [spec 07](07-write-filelist.md) removed from the writer — it is not new behaviour, it is the fused node's own `path` computation given a node of its own.

## Goal

Compute the destination `.f` path for one test: `work_dir / f"run.{tag}.f"`, where `tag` is the test name with filesystem-hostile characters replaced. Nothing else — no write, no existence check, no `mkdir`.

[Spec 07](07-write-filelist.md) makes `write-filelist` render-and-write only, taking `path` as a fully-resolved input so the same writer serves the `test` graph's per-tag names and the `filelist` command's CLI `output_path`. That leaves the per-tag name with nowhere to live in the `test` graph, because no node produces it: `work-dir` supplies the directory and `gate-pre` supplies the test, but the join and the naming convention belong to neither. This node is that join.

## Why a domain node

The name `run.<tag>.f` and the sanitising pattern are `rtl_buddy` conventions, not path arithmetic, so the module sits in `modules/rtl_buddy/build.py` with the pipeline rather than in `modules/funcs.py` with `dirname`. `BuildCompileCmdMod` already applies the identical `re.sub(r"[^A-Za-z0-9_.-]", "_", test.get_name())` for `obj_dir_<tag>` and its two log filenames (`build.py:198`), so the convention is one the domain layer already owns in two places; a generic template-and-projection node would move it into graph YAML and put the regex somewhere no other user of it can see.

## Surface

```
contract:          keyed_join   (test graph: test keyed, work_dir persistent)
inputs:            test:TestConfig, work_dir:Path
outputs:           path → Path   (the contract rewraps it as KeyedValue)
```

```yaml
contract:
  name: keyed_join
  config:
    key_field: key
    persistent_inputs: [ work_dir ]
    unwrap: true
```

```python
class FilelistPathMod:
    def run(self, test:TestConfig, work_dir:Path):
        tag = re.sub(r"[^A-Za-z0-9_.-]", "_", test.get_name())
        return ("path", Path(work_dir) / f"run.{tag}.f")
```

`test` is a self-keyed record (a `key` with no `value` beside it), so `keyed_join` delivers it whole under `unwrap` and `test.key` is what the emitted `path` is rewrapped under. `work_dir` is the persistent singleton every artefact writer in the graph already takes. `path` is the only output port, so no `ignore` list is needed.

**`test` is consumed, not forwarded** — the same removal [spec 07](07-write-filelist.md) makes in the writer and `ResolveModelRefMod` made upstream. `write-filelist` takes its own `test` edge from `gate-pre`.

## Algorithm

1. `tag = re.sub(r"[^A-Za-z0-9_.-]", "_", test.get_name())`.
2. Return `("path", Path(work_dir) / f"run.{tag}.f")`.

No failure path: the node performs no I/O, and a directory that does not exist is still a valid answer — the writer's `FileNotFoundError` arm is what reports it ([spec 07](07-write-filelist.md)).

Per-tag rather than a shared `run.f` so concurrent tests do not collide on one destination. Upstream has no equivalent: `VlogSim._write_filelist` passes an `output_path` built per test (`vlog_sim.py:88-93`), and the sanitising is rtl-comrade's, matching what it already does for `obj_dir_<tag>`.

## Deliverables

- `FilelistPathMod` in `modules/rtl_buddy/build.py`, beside the pipeline modules — `(test:TestConfig, work_dir:Path)` → `("path", Path)`.
- **Manifest** — `{ name: filelist-path, class_name: FilelistPathMod }` in the `- file: rtl_buddy/build.py` block of `modules/config.yaml`, alongside the seven ([spec 02 Deliverables](02-filelist-extract.md#deliverables)).
- **Compatibility source:** `implementation-test` spec 06b's `WriteFilelistMod` (`modules/rtl_buddy/build.py:117-118`) — the `test_tag` / `run.<tag>.f` computation, lifted out of the writer unchanged.
- No `Config` class, no contract.

## Tests

In `modules/tests/test_prep.py`. The module is driven with bare values, as the contract delivers them:

- A `TestConfig` named `foo` with `work_dir=tmp_path` → `("path", tmp_path / "run.foo.f")`.
- A name holding `/`, spaces and `+` → each replaced with `_`; `.`, `-` and `_` survive.
- Two `TestConfig`s with different names, same `work_dir` → distinct paths (the per-tag property).
- The result is the same tag `BuildCompileCmdMod` derives for the same name, so `run.<tag>.f` and `obj_dir_<tag>` agree.
- A `work_dir` that does not exist → still returns the joined path, no error and no `mkdir`.

## Acceptance criteria

- Tests pass.
- Output is `work_dir / f"run.{tag}.f"` with the tag sanitised by `[^A-Za-z0-9_.-]` → `_`.
- `path` is the only port that fires; `test` is never re-emitted.
- Byte-identical destination to the fused 06b node for the same `test` and `work_dir`.
- `filelist-path` → `FilelistPathMod` resolves in the manifest.

## Constraints

- **Path computation only.** No write, no `exists()`, no `mkdir()` — the writer owns the I/O and its failures ([spec 07](07-write-filelist.md)).
- **`path` is the only output port**; `test` is read for the name and never forwarded.
- **The module never touches the key** — `unwrap: true` goes on the `contract` plugin's config, and the contract attaches `test.key` to the emitted path.
- Keep the sanitising pattern identical to `BuildCompileCmdMod`'s (`build.py:198`); the two names are read side by side in a working directory.
- The `filelist` command does **not** wire this node — its destination is the CLI `output_path` ([00-overview](00-overview.md#the-pipeline-at-a-glance)).
