# Spec 06b: write-filelist (`WriteFilelistMod`)

**Depends on:** spec 01 (schema), spec [01b](01b-suite-schema.md) (`WriteFilelistMod` reads `ctx["test"].get_testbench().get_filelist()`), spec [01c](01c-model-schema.md) (`WriteFilelistMod` reads `ctx["test"].get_model().get_filelist()` and `.path`).
**References:** [03 — Per-test preparation section](../03-module-catalog.md). Parent index: [idx-06 — Per-test prep modules](../idx-06-prep.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)` signature, the allowed output forms (plain return / named-port tuple / generator), the `finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py` are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit `a69d962`). This module appends to `modules/rtl_buddy/build.py`, which is created by spec [`06a`](06a-run-preproc.md) — append, do not overwrite. The file is shared with run-process (`03`), the prep modules (`06a`–`06b`, index [idx-06](../idx-06-prep.md)), and the compile-cycle modules (`07a`–`07b`, index [idx-07](../idx-07-compile-cycle.md)); coordinate shared imports and helpers with those specs.

## Goal

Reimplement rtl_buddy's `VlogFilelist` to produce the per-test `.f` file consumed by the compile leg, writing a per-tag `run.{test_tag}.f` for concurrency safety.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry — the catalog is the design view, this is the build view; update both when behaviour changes. The two success ports are emitted in lockstep via a generator (one `(port, value)` per yield — the harness has no multi-port single return).

```
contract:          default
persistent_inputs: [work_dir]
inputs:            ctx, work_dir:Path
outputs:           ctx      → ctx
                   filelist → {key, filelist}
                   fail     → result
```

`work_dir` is the **validated base directory** (a `Path`) supplied by `check-suite-cwd` — the same artefact-location provider `ensure-logs-dir` consumes. This module joins the per-tag filename onto it and never touches the ambient CWD; it is load-bearing (read to decide where the `.f` lands), so it is a required (non-defaulted) port the harness edge-validates.

```python
class WriteFilelistMod:
    def run(self, ctx, work_dir):
        test_tag = re.sub(r"[^A-Za-z0-9_.-]", "_", ctx["test"].get_name())
        path = Path(work_dir) / f"run.{test_tag}.f"   # rooted on the validated base dir, not ambient CWD
        try:
            write_output(path, ctx["test"], unroll=True, deduplicate=True)
        except Exception as e:
            result = make_fail_result(desc=str(e))
            log.error("filelist_failed", key=ctx["key"], test_name=ctx["test"].get_name(), path=str(path), err=str(e),
                      result=result.results["result"], desc=result.results["desc"])   # → SummaryProcessor row
            yield ("fail", { "key": ctx["key"], "result": result })
            return
        yield ("ctx", ctx)
        yield ("filelist", { "key": ctx["key"], "filelist": path })
```

## Algorithm

1. Derive the per-tag filename rooted on the provided base: `test_tag = re.sub(r"[^A-Za-z0-9_.-]", "_", ctx["test"].get_name())` (the same regex `build-compile-cmd` uses) and `path = Path(work_dir) / f"run.{test_tag}.f"` — per-tag so concurrent tests don't collide on a shared `run.f`, and joined onto `work_dir` (the validated base dir from `check-suite-cwd`) so the location is decided by the provider, not the ambient CWD.
2. Resolve and write the filelist: port `VlogFilelist.write_output(unroll=True, flatten=False, strip=False, deduplicate=True, test_filelist=ctx["test"].get_testbench().get_filelist())`, using `ctx["test"].get_model()` (the `ModelConfig` from `load-model`, with `.filelist` / `.path` per spec 01c) for `-F` include resolution. The option-parsing regex, `-F` recursion with unroll, `+incdir+`/`+libext+` handling, dedup, and existence checks are all faithful to the reference (see Notes / Compatibility source).
3. On success emit in lockstep: `("ctx", ctx)` then `("filelist", {"key": ctx["key"], "filelist": path})` (consumed by `build-compile-cmd`).
4. **Failure — resolve/write error.** Wrap step 2 in `try/except Exception`: `FileNotFoundError`/`IsADirectoryError`/`OSError`/`PermissionError` (write), or `KeyError`/`AttributeError` from a missing testbench filelist or `ctx["test"].get_model() is None` (meaning `load-model` did not fire upstream) → emit `("fail", {"key": ctx["key"], "result": <FAIL with str(e) in desc>})` and `log.error("filelist_failed", …)` with the attempted path, the chain of `-F` includes the resolver was processing, **and `result`/`desc`** (so `SummaryProcessor`'s watch-list collects the row).

## Deliverables

In `modules/rtl_buddy/build.py` (continuing from spec 03):

- `WriteFilelistMod` — `(ctx, work_dir:Path)` → reimplements `VlogFilelist.write_output(unroll=True, flatten=False, strip=False, deduplicate=True, test_filelist=ctx["test"].get_testbench().get_filelist())` using `ctx["test"].get_model()` (the `ModelConfig` populated by `load-model` upstream, with `.filelist: list[str]` and `.path: str` per spec [01c](01c-model-schema.md)) for `-F` include resolution. Writes the filelist file to `Path(work_dir) / f"run.{test_tag}.f"`, joining the per-tag name onto the validated base directory `work_dir` supplied by `check-suite-cwd` (the same artefact-location provider `ensure-logs-dir` consumes; **load-bearing** persistent input, so a missing edge fails edge-validation rather than silently writing to the ambient CWD). Emits two named outputs on success:
  - `("ctx", ctx)` (passthrough)
  - `("filelist", {"key": ctx["key"], "filelist": <Path>})` (consumed in lockstep by `build-compile-cmd` in spec [07a](07a-build-compile-cmd.md)).
  **Failure handling**: catch `Exception` from the filelist resolution / write (`FileNotFoundError`, `IsADirectoryError`, `OSError` / `PermissionError` for write errors; `KeyError` / `AttributeError` from a missing testbench filelist, or model-path resolution failure during `-F` recursion — e.g. `ctx["test"].get_model() is None`, meaning `load-model` did not fire upstream). Emit `("fail", {"key": ctx["key"], "result": <FAIL payload with `str(e)` in `desc`>})` and call `log.error("filelist_failed", …)` at emission with the attempted filelist path, the chain of `-F` includes the resolver was processing, **and `result`/`desc`** (so the `SummaryProcessor` watch-list, [10c](10c-summary-handler.md), renders the row).
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_filelist.py:137-159` — `VlogFilelist.write_output`; called from `VlogSim._write_filelist` at `tools/vlog_sim.py:88-93`. Per-tag `run.{test_tag}.f` is a divergence in this plan from the hard-coded `"run.f"` (`vlog_sim.py:157`).

**Manifest** — append to the `- file: rtl_buddy/build.py` block in `modules/config.yaml` (opened by [`06a`](06a-run-preproc.md); append, don't re-create):

```yaml
  - { name: write-filelist, class_name: WriteFilelistMod }
```

## Tests

In `modules/tests/test_prep.py`. Fixtures: a committed `models.yaml` + testbench filelist fixture; `tmp_path` passed as the `work_dir` port (so `run.{test_tag}.f` lands under it); a `ctx` fixture carrying a resolved model + testbench; `logging_handler` for the fail paths.

- `ctx` with a real model + testbench filelist, `work_dir=tmp_path` → writes `tmp_path/"run.{test_tag}.f"`, yields `("ctx", ctx)` then `("filelist", {"key", "filelist": <Path under work_dir>})`; a round-trip parse of the `.f` matches the expected entries and `+incdir+` consolidation is applied.
- Location follows `work_dir`, **not** the process CWD: with `monkeypatch.chdir(other)` and `work_dir=tmp_path`, the `.f` is still written under `tmp_path` (boundary: rooting on the provided base dir, mirrors `ensure-logs-dir`).
- `ctx` whose `test.get_name()` has shell-unsafe chars (e.g. `a/b:c`) → the filelist filename is sanitised to `run.a_b_c.f` under `work_dir` (boundary: `test_tag` regex matches `build-compile-cmd`).
- `ctx` where `ctx["test"].get_model() is None` (load-model did not fire) → `AttributeError` during `-F` resolution → emits `("fail", {"key", "result": <FAIL with str(e)>})`, `log.error`, no abort.
- `ctx` whose testbench filelist file is missing → `FileNotFoundError` during resolution → emits `("fail", …)`, `log.error`.
- `work_dir` pointing into a read-only directory → `PermissionError` on write → emits `("fail", …)`, `log.error` (boundary: write-side error routed like a resolve error).

## Acceptance criteria

- Tests pass.
- All three output ports exercised: on success `ctx` forwards `ctx` and `filelist` emits `{key, filelist}`; on a resolve/write error the `fail` path routes a per-test FAIL `result` and logs at ERROR.
- The filelist contents reproduce the byte-for-byte output of rtl_buddy's `VlogFilelist` on the same inputs (modulo ordering if dedup is non-stable).
- The `modules/config.yaml` manifest entry `{ name: write-filelist, class_name: WriteFilelistMod }` validates and the harness resolves `write-filelist` → `WriteFilelistMod`.

## Constraints

- Write the per-tag filename `run.{test_tag}.f` (`test_tag = re.sub(r"[^A-Za-z0-9_.-]", "_", ctx["test"].get_name())`, the same regex `build-compile-cmd` uses) — **never** the bare `run.f`. This per-tag naming is the interim concurrency mitigation, and needs no serialising lock.
- Root the filename on the provided `work_dir`: `Path(work_dir) / f"run.{test_tag}.f"` — `work_dir` is the validated base directory from `check-suite-cwd` (the same provider `ensure-logs-dir` consumes), supplied as a **load-bearing** persistent input. Do **not** compose a CWD-relative `Path(f"run.{test_tag}.f")` or read the ambient process CWD — location is decided by the provider, so a relocation (`--work-dir`, regression's per-suite root) is a one-node change.
- Use the plain `default` contract.
- On success emit `("ctx", ctx)` then `("filelist", {key, filelist: <Path>})` in lockstep via the generator.
- Catch broad `Exception` from the resolve/write (`OSError`/`PermissionError`/`FileNotFoundError`/ `IsADirectoryError`, or `KeyError`/`AttributeError` from a missing testbench filelist or `ctx["test"].get_model() is None`) → emit `("fail", {key, result: <FAIL with str(e)>})` on the **unwired** `fail` port and `log.error("filelist_failed", …)` with the attempted path **and `result`/`desc`** (so the `SummaryProcessor` watch-list collects the row). Per-test FAIL, not abort.

## Notes

`write-filelist` is one of the few modules reimplementing nontrivial rtl_buddy logic (`VlogFilelist`). Port it carefully — the option-parsing regex, `-F` recursion with unroll, `+incdir+`/`+libext+` handling, dedup, and the existence checks are all behaviour worth replicating. See `rtl_buddy/src/rtl_buddy/tools/vlog_filelist.py` for the reference.

Filelist filename: rtl_buddy writes a single `run.f` in CWD per compile, so concurrent compiles would collide. `write-filelist` therefore writes a **per-tag** path `run.{test_tag}.f`, where `test_tag = re.sub(r"[^A-Za-z0-9_.-]", "_", ctx["test"].get_name())` (the same regex `build-compile-cmd` uses — spec [07a](07a-build-compile-cmd.md)), rooted on the `work_dir` provider (`Path(work_dir) / f"run.{test_tag}.f"`), and emits that `Path` on its `filelist` port. `build-compile-cmd` passes `filelist["filelist"]` straight to `-f`, so it needs no change. The per-tag naming is the interim concurrency mitigation; rooting on `work_dir` is the R14 slice that brings `run.f` under the same artefact-location provider model as `logs/` (`check-suite-cwd` → consumers). The residual CWD-relative artefacts this does **not** cover (non-verilator configured `simv`, `test.*` symlinks, tool-internal files) wait on the upstream per-invocation-subdir change ([07 item 17](../07-ambiguities-and-assumptions.md)), the reference fix that supersedes both when it lands. See [05 — Interim CWD-collision posture](../05-branching-and-results.md#interim-cwd-collision-posture--per-tag-artefact-naming).
