# Spec 06b: write-filelist (`WriteFilelistMod`)

**Depends on:** spec 01 (schema), spec [01b](01b-suite-schema.md)
(`WriteFilelistMod` reads `ctx["test"].get_testbench().get_filelist()`), spec
[01c](01c-model-schema.md) (`WriteFilelistMod` reads
`ctx["test"].get_model().get_filelist()` and `.path`).
**References:** [03 — Per-test preparation section](../03-module-catalog.md). Parent index:
[06 — Per-test prep modules](06-prep-modules.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)`
signature, the allowed output forms (plain return / named-port tuple / generator), the
`finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py`
are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry
below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit
`a69d962`). This module appends to `modules/rtl_test/build.py`, which is created by spec
[`06a`](06a-run-preproc.md) — append, do not overwrite. The file is shared with run-process
(`03`), the prep modules (`06a`–`06b`, index [06](06-prep-modules.md)), and the compile-cycle
modules (`07a`–`07b`, index [07](07-compile-cycle-modules.md)); coordinate shared imports and
helpers with those specs.

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

## Algorithm

1. Derive the per-tag filename: `test_tag = re.sub(r"[^A-Za-z0-9_.-]", "_",
   ctx["test"].get_name())` (the same regex `build-compile-cmd` uses) and `path =
   Path(f"run.{test_tag}.f")` — per-tag so concurrent tests don't collide on a shared `run.f`.
2. Resolve and write the filelist: port `VlogFilelist.write_output(unroll=True, flatten=False,
   strip=False, deduplicate=True, test_filelist=ctx["test"].get_testbench().get_filelist())`,
   using `ctx["test"].get_model()` (the `ModelConfig` from `load-model`, with `.filelist` /
   `.path` per spec 01c) for `-F` include resolution. The option-parsing regex, `-F` recursion
   with unroll, `+incdir+`/`+libext+` handling, dedup, and existence checks are all faithful to
   the reference (see Notes / Compatibility source).
3. On success emit in lockstep: `("ctx", ctx)` then `("filelist", {"key": ctx["key"],
   "filelist": path})` (consumed by `build-compile-cmd`).
4. **Failure — resolve/write error.** Wrap step 2 in `try/except Exception`:
   `FileNotFoundError`/`IsADirectoryError`/`OSError`/`PermissionError` (write), or
   `KeyError`/`AttributeError` from a missing testbench filelist or `ctx["test"].get_model() is
   None` (meaning `load-model` did not fire upstream) → emit `("fail", {"key": ctx["key"],
   "result": <FAIL with str(e) in desc>})` and `log.error` with the attempted path and the chain
   of `-F` includes the resolver was processing.

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

**Manifest** — append to the `- file: rtl_test/build.py` block in `modules/config.yaml`
(opened by [`06a`](06a-run-preproc.md); append, don't re-create):

```yaml
  - { name: write-filelist, class_name: WriteFilelistMod }
```

## Tests

In `modules/tests/test_prep.py`. Fixtures: a committed `models.yaml` + testbench filelist
fixture; `tmp_path` CWD via `monkeypatch.chdir` (so `run.{test_tag}.f` lands in a temp dir);
a `ctx` fixture carrying a resolved model + testbench; `logging_handler` for the fail paths.

- `ctx` with a real model + testbench filelist → writes `run.{test_tag}.f`, yields `("ctx",
  ctx)` then `("filelist", {"key", "filelist": <Path>})`; a round-trip parse of the `.f`
  matches the expected entries and `+incdir+` consolidation is applied.
- `ctx` whose `test.get_name()` has shell-unsafe chars (e.g. `a/b:c`) → the filelist filename
  is sanitised to `run.a_b_c.f` (boundary: `test_tag` regex matches `build-compile-cmd`).
- `ctx` where `ctx["test"].get_model() is None` (load-model did not fire) → `AttributeError`
  during `-F` resolution → emits `("fail", {"key", "result": <FAIL with str(e)>})`,
  `log.error`, no abort.
- `ctx` whose testbench filelist file is missing → `FileNotFoundError` during resolution →
  emits `("fail", …)`, `log.error`.
- `ctx` written into a read-only CWD → `PermissionError` on write → emits `("fail", …)`,
  `log.error` (boundary: write-side error routed like a resolve error).

## Acceptance criteria

- Tests pass.
- All three output ports exercised: on success `ctx` forwards `ctx` and `filelist` emits
  `{key, filelist}`; on a resolve/write error the `fail` path routes a per-test FAIL `result`
  and logs at ERROR.
- The filelist contents reproduce the byte-for-byte output of rtl_buddy's `VlogFilelist`
  on the same inputs (modulo ordering if dedup is non-stable).
- The `modules/config.yaml` manifest entry `{ name: write-filelist, class_name: WriteFilelistMod }`
  validates and the harness resolves `write-filelist` → `WriteFilelistMod`.

## Constraints

- Write the per-tag filename `run.{test_tag}.f` (`test_tag = re.sub(r"[^A-Za-z0-9_.-]", "_",
  ctx["test"].get_name())`, the same regex `build-compile-cmd` uses) — **never** the bare
  `run.f`. This per-tag naming is the interim concurrency mitigation; do **not** reintroduce a
  serialising lock (the `serial_acquire` shim was removed, TODO #30).
- Use the plain `default` contract (reverted from `serial_acquire`).
- On success emit `("ctx", ctx)` then `("filelist", {key, filelist: <Path>})` in lockstep via
  the generator.
- Catch broad `Exception` from the resolve/write (`OSError`/`PermissionError`/`FileNotFoundError`/
  `IsADirectoryError`, or `KeyError`/`AttributeError` from a missing testbench filelist or
  `ctx["test"].get_model() is None`) → emit `("fail", {key, result: <FAIL with str(e)>})` on the
  **unwired** `fail` port and `log.error` with the attempted path. Per-test FAIL, not abort.

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
