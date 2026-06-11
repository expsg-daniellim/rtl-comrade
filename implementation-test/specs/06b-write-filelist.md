# Spec 06b: write-filelist (`WriteFilelistMod`)

**Depends on:** spec 01 (schema), spec [01b](01b-suite-schema.md)
(`WriteFilelistMod` reads `ctx["test"].get_testbench().get_filelist()`), spec
[01c](01c-model-schema.md) (`WriteFilelistMod` reads
`ctx["test"].get_model().get_filelist()` and `.path`).
**References:** [03 — Per-test preparation section](../03-module-catalog.md). Parent index:
[06 — Per-test prep modules](06-prep-modules.md).

## Goal

Reimplement rtl_buddy's `VlogFilelist` to produce the per-test `.f` file consumed by the
compile leg, writing a per-tag `run.{test_tag}.f` for concurrency safety.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry —
the catalog is the design view, this is the build view; update both when behaviour changes.
The two success ports are emitted in lockstep via a generator (one `(port, value)` per
yield — the harness has no multi-port single return).

```
contract: default
inputs:   ctx
outputs:  ctx      → ctx
          filelist → {key, filelist}
          fail     → result
```

```python
class WriteFilelistMod:
    def run(self, ctx):
        test_tag = re.sub(r"[^A-Za-z0-9_.-]", "_", ctx["test"].get_name())
        path = Path(f"run.{test_tag}.f")
        try:
            write_output(path, ctx["test"], unroll=True, deduplicate=True)
        except Exception as e:
            log.error("filelist_failed", key=ctx["key"], path=str(path), err=str(e))
            yield ("fail", { "key": ctx["key"], "result": ... })
            return
        yield ("ctx", ctx)
        yield ("filelist", { "key": ctx["key"], "filelist": path })
```

## Deliverables

In `modules/rtl_test/build.py` (continuing from spec 03):

- `WriteFilelistMod` — `(ctx)` → reimplements `VlogFilelist.write_output(unroll=True,
  flatten=False, strip=False, deduplicate=True,
  test_filelist=ctx["test"].get_testbench().get_filelist())` using
  `ctx["test"].get_model()` (the `ModelConfig` populated by `load-model` upstream,
  with `.filelist: list[str]` and `.path: str` per spec [01c](01c-model-schema.md))
  for `-F` include resolution. Writes the filelist file; emits two named outputs on
  success:
  - `("ctx", ctx)` (passthrough)
  - `("filelist", {"key": ctx["key"], "filelist": <Path>})` (consumed in lockstep by
    `build-compile-cmd` in spec [07a](07a-build-compile-cmd.md)).
  **Failure handling**: catch `Exception` from the filelist resolution / write
  (`FileNotFoundError`, `IsADirectoryError`, `OSError` / `PermissionError` for write
  errors; `KeyError` / `AttributeError` from a missing testbench filelist, or model-path
  resolution failure during `-F` recursion — e.g. `ctx["test"].get_model() is None`,
  meaning `load-model` did not fire upstream). Emit `("fail", {"key": ctx["key"],
  "result": <FAIL payload with `str(e)` in `desc`>})` and call `log.error` at emission
  with the attempted filelist path and the chain of `-F` includes the resolver was
  processing.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_filelist.py:137-159` — `VlogFilelist.write_output`; called from `VlogSim._write_filelist` at `tools/vlog_sim.py:88-93`. Per-tag `run.{test_tag}.f` is a Plan B divergence from the hard-coded `"run.f"` (`vlog_sim.py:157`).

Manifest entries per [06](../06-graph-yaml.md).

## Tests

In `modules/tests/test_prep.py`:

- `write-filelist` produces a syntactically valid `.f` file from a real `models.yaml` +
  testbench filelist; round-trip parse matches expected entries; `+incdir+` consolidation
  works.
- Missing testbench filelist / `get_model() is None` → emits `("fail", ...)` with `str(e)`
  in `desc` and `log.error`.

## Acceptance criteria

- Tests pass.
- The filelist module reproduces the byte-for-byte output of rtl_buddy's `VlogFilelist`
  on the same inputs (modulo ordering if dedup is non-stable).
- Both output ports (`ctx`/`filelist` on success, `fail`) are exercised.

## Notes

`write-filelist` is one of the few modules reimplementing nontrivial rtl_buddy logic
(`VlogFilelist`). Port it carefully — the option-parsing regex, `-F` recursion with
unroll, `+incdir+`/`+libext+` handling, dedup, and the existence checks are all
behaviour worth replicating. See `rtl_buddy/src/rtl_buddy/tools/vlog_filelist.py` for
the reference.

Filelist filename (TODO #30 / KIV 17): rtl_buddy writes a single `run.f` in CWD per compile,
so concurrent compiles would collide. `write-filelist` therefore writes a **per-tag** path
`run.{test_tag}.f`, where `test_tag = re.sub(r"[^A-Za-z0-9_.-]", "_",
ctx["test"].get_name())` (the same regex `build-compile-cmd` uses — spec
[07a](07a-build-compile-cmd.md)), and emits that `Path` on its `filelist` port.
`build-compile-cmd` passes `filelist["filelist"]` straight to `-f`, so it needs no change.
This per-tag naming is the interim, graph-local mitigation that replaced the removed
`serial_acquire` lock shim; the broader CWD isolation (non-verilator `simv`, symlinks,
tool-internal files) is the upstream per-invocation-subdir change
([07 item 17](../07-ambiguities-and-assumptions.md)), the reference fix that supersedes this
naming when it lands. See
[05 — Interim CWD-collision posture](../05-branching-and-results.md#interim-cwd-collision-posture--per-tag-artefact-naming).
