# Spec 08e: link-latest (`LinkLatestMod`)

**Depends on:** spec [08d](08d-write-randseed.md) (`test_run`).
**References:** [03 — Simulation section](../03-module-catalog.md). Parent index:
[08 — Sim-cycle modules](08-sim-cycle-modules.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)`
signature, the allowed output forms (plain return / named-port tuple / generator), the
`finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py`
are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry
below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit
`a69d962`). This module appends to `modules/rtl_buddy/sim.py`, which is created by spec
[`08a`](08a-expand-runs.md) — append, do not overwrite. The file is shared with the sim-cycle
modules (`08a`–`08f`, index [08](08-sim-cycle-modules.md)) and the post modules (`09a`–`09c`,
index [09](09-post-modules.md)); coordinate shared imports and helpers with those specs.

## Goal

Force the `test.*` "latest" symlinks in CWD to this run's log/err/randseed files.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry —
the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract: default
inputs:   test_run
outputs:  default → test_run
```

```python
class LinkLatestMod:
    def run(self, test_run):
        force_symlink(test_run["log"], "test.log")
        force_symlink(test_run["err"], "test.err")
        force_symlink(test_run["randseed_path"], "test.randseed")
        return ("default", test_run)
```

## Algorithm

1. Force the three CWD "latest" symlinks to this run's files:
   `force_symlink(test_run["log"], "test.log")`, `force_symlink(test_run["err"], "test.err")`,
   `force_symlink(test_run["randseed_path"], "test.randseed")`. `force_symlink` replaces any
   existing link atomically (unlink+symlink, or `os.replace` of a temp link).
2. Emit `("default", test_run)` unchanged. No failure path; the links are convenience pointers
   (last-writer-wins under concurrency — see the concurrency note).

## Deliverables

In `modules/rtl_buddy/sim.py`:

- `LinkLatestMod` — `(test_run)` → force CWD symlinks `test.log`/`test.err`/`test.randseed`
  to this run's files (paths from `test_run["log"]`, `test_run["err"]`,
  `test_run["randseed_path"]`); emits `test_run` unchanged. Symlinks themselves are
  always placed in CWD, matching rtl_buddy. **Concurrency note (TODO #30 / item 17):** these
  are fixed "latest" pointer names, so concurrent tests race on them (last-writer-wins). They
  are convenience pointers, not corrupting — the targets they point to are per-tag. Per-tag
  naming (TODO #30) deliberately does **not** rename these; isolating them is the upstream
  per-invocation-subdir change ([07 item 17](../07-ambiguities-and-assumptions.md)). Do not add
  a lock — the `serial_acquire` shim was removed.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:271-273` — the three `force_symlink` calls; helper at `vlog_sim.py:26-30`.

**Manifest** — append to the `- file: rtl_buddy/sim.py` block in `modules/config.yaml`
(opened by [`08a`](08a-expand-runs.md); append, don't re-create):

```yaml
  - { name: link-latest, class_name: LinkLatestMod }
```

## Tests

In `modules/tests/test_sim_cycle.py`. Fixtures: `tmp_path` CWD via `monkeypatch.chdir`; a
`test_run` dict carrying `log`/`err`/`randseed_path`. No `logging_handler` (no failure path).

- Fresh CWD, no existing `test.*` links → after `run()`, `test.log`/`test.err`/`test.randseed`
  are symlinks pointing at `test_run["log"]`/`["err"]`/`["randseed_path"]`; emits
  `("default", test_run)` unchanged.
- Pre-existing `test.*` symlinks pointing at an earlier run → force-replaced to this run's
  files (boundary: existing link replaced atomically, not appended-to or errored).
- A pre-existing `test.log` that is a dangling symlink (target deleted) → still replaced
  cleanly to the new target (boundary: broken link).
- Two sequential invocations with different `test_run` paths → the links end pointing at the
  second run's files (last-writer-wins), and each call returns its own `test_run` unchanged.

## Acceptance criteria

- Tests pass.
- Output port `default` exercised: the three `test.*` symlinks (`test.log`/`test.err`/
  `test.randseed`) point at this run's files and `test_run` passes through unchanged.
- No failure path: the links are convenience pointers.
- The `modules/config.yaml` manifest entry `{ name: link-latest, class_name: LinkLatestMod }`
  validates and the harness resolves `link-latest` → `LinkLatestMod`.

## Constraints

- Force each `test.log`/`test.err`/`test.randseed` symlink **atomically** (unlink+symlink, or
  `os.replace` of a temp link) — never leave a half-written link.
- Symlinks are fixed "latest" pointer names in CWD; concurrent runs race them (last-writer-wins).
  Do **not** rename them per-tag and do **not** add a lock — isolating them is the upstream
  per-invocation-subdir change ([07 item 17](../07-ambiguities-and-assumptions.md)).
- No failure path; emit `("default", test_run)` unchanged.
