# Spec 08e: link-latest (`LinkLatestMod`)

**Depends on:** spec [08d](08d-write-randseed.md) (`test_run`).
**References:** [03 — Simulation section](../03-module-catalog.md). Parent index:
[08 — Sim-cycle modules](08-sim-cycle-modules.md).

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

## Deliverables

In `modules/rtl_test/sim.py`:

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

Manifest entries per [06](../06-graph-yaml.md).

## Tests

In `modules/tests/test_sim_cycle.py`:

- `link-latest` forces symlinks atomically (use `os.replace` or unlink+symlink ordering)
  and emits `test_run` unchanged.

## Acceptance criteria

- Tests pass.
- The three `test.*` symlinks point at this run's files and `test_run` passes through
  unchanged.
