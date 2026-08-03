# Spec 04f: work-dir (`WorkDirMod`)

**Depends on:** none (zero-input).
**References:** [03 — Setup section](../03-module-catalog.md), [01 — Where to invoke `rtl-comrade test` from](../01-cli-and-entry.md). Parent index: [idx-04 — Setup modules](../idx-04-setup.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)` signature, the allowed output forms (plain return / named-port tuple / generator), the `finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py` are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit `a69d962`). This module appends to `modules/rtl_buddy/setup.py`, which is created by spec [`04a`](04a-discover-config-file.md) — append, do not overwrite. The file is shared with the setup chain (`04a`–`04i`, index [idx-04](../idx-04-setup.md)), the selection/expansion chain (`05a`–`05f`, index [idx-05](../idx-05-selection-expansion.md)), and git-status (`10b`); coordinate shared imports and helpers with those specs.

## Goal

Provide the artefact **base directory** `work_dir` as a single data source, so the leaf writers and the subprocess `cwd` root on a *provided* directory instead of each reading the ambient process CWD. For `test`/`randtest`, `work_dir` **is** the CWD — faithful to rtl_buddy's `do_cmd_test`, which never `chdir`s and so works in the directory it was invoked from (run here, output here). The `regression` graph supplies a **per-suite** `work_dir` from `parse-suite-config`'s `suite_dir` instead of wiring this node (see [08](../08-sibling-graphs.md)).

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry — the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract: default   (zero-input → default, not unit; see 04 — with no ports unit/default are identical and unit would assert a one-shot guarantee it doesn't supply)
inputs:   (none)
outputs:  default → Path   (the artefact base = Path.cwd().resolve())
```

```python
class WorkDirMod:
    def run(self):
        return Path.cwd().resolve()   # the artefact base; test/randtest work in (and output to) CWD
```

## Algorithm

1. Read the process CWD: `Path.cwd().resolve()` — `.resolve()` collapses symlinks so the value is a stable realpath the leaf modules can join filenames onto and the runner can pass as `cwd`.
2. Emit `("default", <that Path>)` — the single artefact base. Every artefact writer (`ensure-logs-dir`, `write-filelist`, `build-compile-cmd`, `build-sim-cmd`, `write-randseed`, `link-latest`) joins filenames onto it, and `run-process` launches subprocesses with `cwd=work_dir`. Because location is decided **once** and flows as data, a future `--work-dir` override (or regression's per-suite root) is a change to this provider alone — the leaf modules never read the ambient CWD themselves.

No failure path — reading the CWD does not fail meaningfully. (The missing-suite-config failure now lives in `parse-suite`, which opens the file — spec [04h](04h-parse-suite-config.md).)

## Deliverables

In `modules/rtl_buddy/setup.py`:

- `WorkDirMod` — a zero-input `default` node emitting `Path.cwd().resolve()` on `default` (zero-input → `default`, not `unit`; see [04](../04-pipeline-and-contracts.md)). This hoists "the CWD" into a **single data source** so no leaf module calls `os.getcwd()`/`Path.cwd()` itself; they consume `work_dir` as a persistent input and root every path on it (and `run-process` roots the subprocess `cwd` on it). Faithful to rtl_buddy's `do_cmd_test` (`rtl_buddy/src/rtl_buddy/rtl_buddy.py:166-209`), which never `chdir`s — `test`/`randtest` work in, and write to, the invocation CWD. A future `--work-dir` CLI override is the natural extension here (add an optional input defaulting to CWD); it is kept **zero-input** for now. The `regression` graph does **not** wire this node — it sources a per-suite `work_dir` from `parse-suite-config`'s `suite_dir` (the per-suite artefact base, mirroring `do_rtl_regression`'s per-suite `chdir`), see [08](../08-sibling-graphs.md).
  **Failure handling**: none (no I/O that can fail).
  **Compatibility source:** rtl_buddy `do_cmd_test` (`rtl_buddy/src/rtl_buddy/rtl_buddy.py:166-209`) never `chdir`s — the test command works in the ambient CWD, and all artefacts (`logs/`, `run.f`, `obj_dir_<tag>/`, `test.*` symlinks) land there. Contrast `do_rtl_regression`'s per-suite `os.chdir(suite_cfg_dir)` (`rtl_buddy.py:404`), which the regression graph mirrors with a per-suite `work_dir`.

**Manifest** — append to the `- file: rtl_buddy/setup.py` block in `modules/config.yaml` (opened by [`04a`](04a-discover-config-file.md); append, don't re-create):

```yaml
  - { name: work-dir, class_name: WorkDirMod }
```

## Tests

In `modules/tests/test_setup.py`. Fixtures: `tmp_path` + `monkeypatch.chdir` to set CWD.

- `run()` from a known CWD → emits `("default", Path.cwd().resolve())`.
- `monkeypatch.chdir(other)` → emits `other.resolve()` (boundary: the node *is* the CWD provider — its output follows the process CWD).
- CWD is a symlink (`/tmp/link → /tmp/real`) → emits `/tmp/real` (boundary: `.resolve()` collapses to the realpath).

## Acceptance criteria

- Tests pass.
- Output port `default` emits `Path.cwd().resolve()`.
- The `modules/config.yaml` manifest entry `{ name: work-dir, class_name: WorkDirMod }` validates and the harness resolves `work-dir` → `WorkDirMod`.

## Constraints

- Zero-input `default` node (zero-input → `default`, not `unit`); emit `Path.cwd().resolve()` on the string-literal `default` port.
- This is the **single artefact-location source** for `test`/`randtest`. Leaf modules must consume this `work_dir` (as a persistent input) and never read the ambient process CWD themselves — so relocating artefacts (a future `--work-dir`, regression's per-suite root) is a one-node change.
- Do **not** wire this node in the regression graph — regression sources a per-suite `work_dir` from `parse-suite-config`'s `suite_dir` ([08](../08-sibling-graphs.md)).

## Notes

`work-dir` is kept a **separate node** from `parse-suite` (spec [04h](04h-parse-suite-config.md), which resolves and opens the suite-config file): the artefact base and the suite-config path share nothing but `Path.cwd()`, so the base lives in its own tiny provider rather than folded into the parser.
