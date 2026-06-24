# Spec 08e: link-latest (`LinkLatestMod`)

**Depends on:** spec [08d](08d-write-randseed.md) (`randseed_done` ordering signal); reads `randseed` (spec [08c](08c-build-sim-cmd.md)) and `proc` (spec 03).
**References:** [03 — Simulation section](../03-module-catalog.md). Parent index: [idx-08 — Sim-cycle modules](../idx-08-sim-cycle.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)` signature, the allowed output forms (plain return / named-port tuple / generator), the `finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py` are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit `a69d962`). This module appends to `modules/rtl_buddy/sim.py`, which is created by spec [`08a`](08a-expand-runs.md) — append, do not overwrite. The file is shared with the sim-cycle modules (`08a`–`08f`, index [idx-08](../idx-08-sim-cycle.md)) and the post modules (`09a`–`09c`, index [idx-09](../idx-09-post.md)); coordinate shared imports and helpers with those specs. This spec defines the shared module-level helper `force_symlink` (Deliverables) and adds `import os` to `sim.py`; `link-latest` is its sole consumer.

## Goal

Force the `test.*` "latest" symlinks under `work_dir` to this run's log/err/randseed files.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry — the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract:          keyed_join
contract_config:   key_field: key
persistent_inputs: [work_dir]
inputs:            randseed, proc, randseed_done, work_dir:Path   (randseed/proc/randseed_done joined by key; randseed_done orders after write-randseed)
outputs:           none   (terminal side-effect — the side-effect branch's leaf)
```

`work_dir` is the artefact base from `work-dir` — the `test.*` "latest" pointers are placed **under it**, alongside the per-run files they point at, not in the ambient CWD.

```python
class LinkLatestMod:
    def run(self, randseed, proc, randseed_done, work_dir):   # randseed_done: ordering gate (after write-randseed); unread. work_dir persistent
        force_symlink(proc.stdout_path, Path(work_dir) / "test.log")             # log = proc's echoed stdout_path
        force_symlink(proc.stderr_path, Path(work_dir) / "test.err")             # err = proc's echoed stderr_path
        force_symlink(randseed.randseed_path, Path(work_dir) / "test.randseed")
        # terminal — emits nothing
```

## Algorithm

1. Force the three "latest" symlinks **under `work_dir`** to this run's files: `force_symlink(proc.stdout_path, Path(work_dir) / "test.log")`, `force_symlink(proc.stderr_path, Path(work_dir) / "test.err")`, `force_symlink(randseed.randseed_path, Path(work_dir) / "test.randseed")`. `work_dir` is the artefact base (`work-dir`), so the pointers sit beside the `logs/` tree they reference rather than in the ambient CWD. `log`/`err` are read from `proc` (which echoes the redirect paths); `randseed_path` from the `randseed` edge. `randseed_done` is joined only to **order** this node after `write-randseed` (so `test.randseed` points at a written file) and is otherwise unread. `force_symlink` is the shared `sim.py` helper this spec defines (Deliverables below) — it replaces any existing link atomically (`os.symlink` to a temp name then `os.replace`).
2. Emit nothing — terminal leaf of the side-effect branch. No failure path; the links are convenience pointers (last-writer-wins under concurrency — see the concurrency note).

## Deliverables

In `modules/rtl_buddy/sim.py`:

- `LinkLatestMod` — `(randseed, proc, randseed_done, work_dir:Path)`, `keyed_join` (joining `randseed`/`proc`/`randseed_done` by key) with `work_dir` as a `persistent_input` → force the symlinks `<work_dir>/test.log`/`test.err`/`test.randseed` to this run's files (`log`/`err` from `proc.stdout_path`/`["stderr_path"]`, `randseed_path` from `randseed.randseed_path`); `randseed_done` orders it after `write-randseed` (unread). Emits nothing — terminal leaf of the side-effect branch. The pointers are placed **under `work_dir`** (the artefact base from `work-dir`), beside the per-run files they reference — a divergence from rtl_buddy, which drops them in the ambient CWD because its sim `chdir`'d there. **Concurrency note (item 17):** these are fixed "latest" pointer names, so concurrent tests within one `work_dir` race on them (last-writer-wins). They are convenience pointers, not corrupting — the targets they point to are per-tag. Per-tag naming deliberately does **not** rename these; isolating them is the upstream per-invocation-subdir change ([07 item 17](../07-ambiguities-and-assumptions.md)). Do not add a lock.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:271-273` — the three `force_symlink` calls (placed in CWD = the sim's `chdir`'d dir); helper at `vlog_sim.py:26-30`. Divergence: rooted on `work_dir` here.

- **`force_symlink(target, link_name)` — shared module-level helper.** `link-latest` is its sole consumer (the three `test.*` symlinks above), so this spec owns the canonical definition. Requires `import os` in `sim.py`. It force-replaces an existing link **atomically** — unlike rtl_buddy's non-atomic `os.remove` + `os.symlink`, this plan symlinks to a unique temp name then `os.replace`s it over `link_name` (the atomicity the Constraints below require):

  ```python
  # modules/rtl_buddy/sim.py  (module-level helper)
  def force_symlink(target, link_name) -> None:
      tmp = f"{link_name}.{os.getpid()}.tmp"
      os.symlink(target, tmp)
      os.replace(tmp, link_name)   # atomic rename over any existing link (or absent target)
  ```

  **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:26-30` — `force_symlink` (this plan makes the replace atomic; recorded as a Notable divergence).

**Manifest** — append to the `- file: rtl_buddy/sim.py` block in `modules/config.yaml` (opened by [`08a`](08a-expand-runs.md); append, don't re-create):

```yaml
  - { name: link-latest, class_name: LinkLatestMod }
```

## Tests

In `modules/tests/test_sim_cycle.py`. Fixtures: `work_dir=tmp_path` passed as the port; `proc` (`{key, stdout_path, stderr_path, …}`), `randseed` (`{key, randseed_path, …}`), and `randseed_done` (`{key}`) dict fixtures. No `logging_handler` (no failure path). Drive `run(randseed, proc, randseed_done, work_dir)` directly.

- Fresh `work_dir`, no existing `test.*` links → after `run()`, `<work_dir>/test.log`/`test.err`/`test.randseed` are symlinks pointing at `proc.stdout_path`/`proc.stderr_path`/`randseed.randseed_path`; emits nothing.
- Links land in `work_dir`, **not** the process CWD: with `monkeypatch.chdir(other)` and `work_dir=tmp_path`, the three `test.*` links are created under `tmp_path` and **not** under `other` (boundary: pointers root on the provided base dir).
- Pre-existing `<work_dir>/test.*` symlinks pointing at an earlier run → force-replaced to this run's files (boundary: existing link replaced atomically, not appended-to or errored).
- A pre-existing `<work_dir>/test.log` that is a dangling symlink (target deleted) → still replaced cleanly to the new target (boundary: broken link).
- Two sequential invocations with different `proc`/`randseed` paths → the links end pointing at the second run's files (last-writer-wins).

## Acceptance criteria

- Tests pass.
- Terminal side-effect exercised: the three `test.*` symlinks (`test.log`/`test.err`/ `test.randseed`) point at this run's files; the node emits nothing.
- No failure path: the links are convenience pointers.
- The `modules/config.yaml` manifest entry `{ name: link-latest, class_name: LinkLatestMod }` validates and the harness resolves `link-latest` → `LinkLatestMod`.

## Constraints

- Force each `<work_dir>/test.log`/`test.err`/`test.randseed` symlink **atomically** (unlink+symlink, or `os.replace` of a temp link) — never leave a half-written link.
- Place the links **under `work_dir`** (`Path(work_dir) / "test.log"` etc.), the artefact base from `work-dir` — **not** the ambient CWD. `work_dir` is a `persistent_input`.
- Symlinks are fixed "latest" pointer names; concurrent runs within one `work_dir` race them (last-writer-wins). Do **not** rename them per-tag and do **not** add a lock — isolating them is the upstream per-invocation-subdir change ([07 item 17](../07-ambiguities-and-assumptions.md)).
- No failure path; terminal leaf — emit nothing. `keyed_join` over `randseed`+`proc`+`randseed_done` (key_field `key`), `work_dir` persistent; `randseed_done` is the ordering gate after `write-randseed`.
