# Spec 06b: write-filelist (`WriteFilelistMod`)

**Depends on:** spec 01 (schema), spec [01b](01b-suite-schema.md) (`WriteFilelistMod` reads `test.get_testbench().get_filelist()`), spec [01c](01c-model-schema.md) (`WriteFilelistMod` reads the joined `model.value.get_filelist()` and `.path`).
**References:** [03 — Per-test preparation section](../03-module-catalog.md). Parent index: [idx-06 — Per-test prep modules](../idx-06-prep.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)` signature, the allowed output forms (plain return / named-port tuple / generator), the `finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py` are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit `a69d962`). This module appends to `modules/rtl_buddy/build.py`, which is created by spec [`06a`](06a-run-preproc.md) — append, do not overwrite. The file is shared with run-process (`03`), the prep modules (`06a`–`06b`, index [idx-06](../idx-06-prep.md)), and the compile-cycle modules (`07a`–`07b`, index [idx-07](../idx-07-compile-cycle.md)); coordinate shared imports and helpers with those specs.

## Goal

Reimplement rtl_buddy's `VlogFilelist` to produce the per-test `.f` file consumed by the compile leg, writing a per-tag `run.{test_tag}.f` for concurrency safety.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry — the catalog is the design view, this is the build view; update both when behaviour changes. The two success ports are emitted in lockstep via a generator (one `(port, value)` per yield — the harness has no multi-port single return).

```
contract:          keyed_join                     (joins test + model by key)
persistent_inputs: [work_dir]
inputs:            test, model, work_dir:Path
outputs:           test     → TestConfig (self-keyed)
                   filelist → {key, value}   (value is the .f Path)
                   fail     → TestResult (self-keyed)
```

The `model` input is the resolved `ModelConfig` carried on its own keyed edge by `load-model` (spec [05e](05e-load-model.md)), `keyed_join`ed to `test` by key — so this node never fires until the model is present (the old `get_model() is None` runtime guard becomes a structural dependency). `work_dir` is the **validated base directory** (a `Path`) supplied by `work-dir` — the same artefact-location provider `ensure-logs-dir` consumes. This module joins the per-tag filename onto it; it is load-bearing (read to decide where the `.f` lands), so it is a required (non-defaulted) port the harness edge-validates.

```python
class WriteFilelistMod:
    def run(self, test:TestConfig, model:KeyedValue[ModelConfig], work_dir:Path):
        test_tag = re.sub(r"[^A-Za-z0-9_.-]", "_", test.get_name())
        path = Path(work_dir) / f"run.{test_tag}.f"
        try:
            # native reimplementation of VlogFilelist.write_output — module-private logic, no rtl_buddy import
            self._write_filelist(output_path=path, model=model.value,
                                 test_filelist=test.get_testbench().get_filelist(),
                                 unroll=True, flatten=False, strip=False, deduplicate=True)
            yield ("test", test)
            yield ("filelist", KeyedValue(test.key, path))
        # write errors (OSError family) and resolve errors (KeyError/AttributeError) are disjoint types → one except per case, each its own event.
        # FileNotFound/IsADirectory/Permission precede OSError (subclasses); the log omits result/desc (they ride the emitted TestResult).
        except FileNotFoundError:
            log.error("filelist_dir_not_found", key=test.key, test_name=test.get_name(), path=str(path))
            yield ("fail", TestResult.prep(test.key, test.get_name(), f"output directory missing for {path}"))
        except IsADirectoryError:
            log.error("filelist_is_directory", key=test.key, test_name=test.get_name(), path=str(path))
            yield ("fail", TestResult.prep(test.key, test.get_name(), f"{path} is a directory"))
        except PermissionError as e:
            log.error("filelist_permission_denied", key=test.key, test_name=test.get_name(), path=str(path), err=e.strerror)
            yield ("fail", TestResult.prep(test.key, test.get_name(), f"cannot write {path}"))
        except (KeyError, AttributeError) as e:
            log.error("filelist_resolve_error", key=test.key, test_name=test.get_name(), path=str(path), err=str(e))
            yield ("fail", TestResult.prep(test.key, test.get_name(), f"filelist resolve failed: {e}"))
        except OSError as e:
            log.error("filelist_write_error", key=test.key, test_name=test.get_name(), path=str(path), err=e.strerror, errno=e.errno)
            yield ("fail", TestResult.prep(test.key, test.get_name(), f"cannot write {path}"))
```

`self._write_filelist(...)` is a **placeholder** for the inlined `VlogFilelist` reimplementation, not a prescribed method to add — write the ported `write_output`/`_extract`/`_process` logic directly here (see [Notes](#notes)). Don't manufacture a `_write_filelist` indirection just because the skeleton names one.

## Algorithm

1. Derive the per-tag filename rooted on the provided base: `test_tag = re.sub(r"[^A-Za-z0-9_.-]", "_", test.get_name())` (the same regex `build-compile-cmd` uses) and `path = Path(work_dir) / f"run.{test_tag}.f"` — per-tag so concurrent tests don't collide on a shared `run.f`, and joined onto `work_dir` (the validated base dir from `work-dir`) so the location is decided by the provider.
2. Resolve and write the filelist: port `VlogFilelist.write_output(unroll=True, flatten=False, strip=False, deduplicate=True, test_filelist=test.get_testbench().get_filelist())`, using `model.value` (the joined `ModelConfig` from `load-model`, with `.filelist` / `.path` per spec 01c) for `-F` include resolution. The option-parsing regex, `-F` recursion with unroll, `+incdir+`/`+libext+` handling, dedup, and existence checks are all faithful to the reference (see Notes / Compatibility source).
3. **Root the `.f` contents on `work_dir`** (= `path.parent`). The reference normalises every entry with `os.path.relpath(line_path)` (`vlog_filelist.py:111`, implicit-CWD base) and derives the test-filelist prefix from `os.path.relpath(".", output_dir)` (`:150`, where `"."` is the CWD it *assumes* holds `tests.yaml`). The reimplementation passes `work_dir` as that base instead: `os.path.relpath(entry, work_dir)` for each written entry, and `os.path.relpath(work_dir, path.parent)` for the test-filelist prefix. Because `work_dir` is both where the `.f` is written **and** — via `run-process`'s `cwd=work_dir` (spec [03](03-run-process.md)) — where the simulator consumes it, the written relative paths resolve correctly. This reproduces rtl_buddy's relative-to-CWD output byte-for-byte under the `work_dir == CWD` happy path while staying correct when they differ (a relocated `-c <dir>/tests.yaml`).
4. On success emit in lockstep: `("test", test)` then `("filelist", KeyedValue(test.key, path))` (consumed by `build-compile-cmd`).
5. **Failure — resolve/write error, one event per case.** Wrap step 2 in a `try` with **one `except` per failure class** (the write classes are `OSError`-family, the resolve classes are `KeyError`/`AttributeError` — disjoint types, so they separate cleanly): `FileNotFoundError`→`filelist_dir_not_found`, `IsADirectoryError`→`filelist_is_directory`, `PermissionError`→`filelist_permission_denied` (`err=e.strerror`), `OSError`→`filelist_write_error` (`err`/`errno`; **last** — the others subclass it); `KeyError`/`AttributeError`→`filelist_resolve_error` (a missing testbench filelist or a `-F` include that fails to resolve; `err=str(e)`). Each logs its event with the exception-specific fields plus the attempted `path` (**not** `result`/`desc`) and emits `("fail", TestResult.prep(test.key, test.get_name(), <per-case desc>))`; the per-exception `log.error` drives the exit, and the emitted `TestResult` → `results-summary` (spec [10d](10d-summarise-results.md)).

## Deliverables

In `modules/rtl_buddy/build.py` (continuing from spec 03):

- `WriteFilelistMod` — `(test, model, work_dir:Path)`, `keyed_join` over `test` + `model` (joined by key) with `work_dir` as a `persistent_input` → reimplements `VlogFilelist.write_output(unroll=True, flatten=False, strip=False, deduplicate=True, test_filelist=test.get_testbench().get_filelist())` using `model.value` (the `ModelConfig` from `load-model` upstream on its own keyed edge, with `.filelist: list[str]` and `.path: str` per spec [01c](01c-model-schema.md)) for `-F` include resolution. Writes the filelist file to `Path(work_dir) / f"run.{test_tag}.f"`, joining the per-tag name onto the validated base directory `work_dir` supplied by `work-dir` (the same artefact-location provider `ensure-logs-dir` consumes; **load-bearing** persistent input, so a missing edge fails edge-validation rather than silently writing to the ambient CWD). Emits two named outputs on success:
  - `("test", test)` (forwards the test edge)
  - `("filelist", KeyedValue(test.key, <Path>))` (consumed in lockstep by `build-compile-cmd` in spec [07a](07a-build-compile-cmd.md)).
  **Failure handling**: **one `except` per failure class**, each its own event — write errors `filelist_dir_not_found` (`FileNotFoundError`), `filelist_is_directory` (`IsADirectoryError`), `filelist_permission_denied` (`PermissionError`), `filelist_write_error` (`OSError`, last); resolve errors `filelist_resolve_error` (`KeyError`/`AttributeError` from a missing testbench filelist or a `-F` include that fails to resolve during recursion). Each logs its event with the **exception-specific** fields plus the attempted `path` (**not** `result`/`desc`) and emits `("fail", TestResult.prep(test.key, test.get_name(), <per-case desc>))`; the per-exception `log.error` drives the exit.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_filelist.py:137-159` — `VlogFilelist.write_output`; called from `VlogSim._write_filelist` at `tools/vlog_sim.py:88-93`. Two divergences in this plan: per-tag `run.{test_tag}.f` replaces the hard-coded `"run.f"` (`vlog_sim.py:157`), and the `.f` **contents** are rooted on `work_dir` (relpath base) rather than the reference's implicit-CWD base (`vlog_filelist.py:111` `os.path.relpath(line_path)`, `:150` `os.path.relpath(".", output_dir)`) — paired with `run-process`'s `cwd=work_dir` (spec [03](03-run-process.md)).

**Manifest** — append to the `- file: rtl_buddy/build.py` block in `modules/config.yaml` (opened by [`06a`](06a-run-preproc.md); append, don't re-create):

```yaml
  - { name: write-filelist, class_name: WriteFilelistMod }
```

## Tests

In `modules/tests/test_prep.py`. Fixtures: a committed `models.yaml` + testbench filelist fixture; `tmp_path` passed as the `work_dir` port (so `run.{test_tag}.f` lands under it); a `test` edge fixture (`{key, value}`) carrying the testbench and a separate `model` edge fixture (`{key, value}`) carrying the resolved `ModelConfig` (same key as `test`); `logging_handler` for the fail paths.

- `test` + `model` with a real model + testbench filelist, `work_dir=tmp_path` → writes `tmp_path/"run.{test_tag}.f"`, yields `("test", test)` then `("filelist", KeyedValue(key, <Path under work_dir>))`; a round-trip parse of the `.f` matches the expected entries and `+incdir+` consolidation is applied.
- Location follows `work_dir`, **not** the process CWD: with `monkeypatch.chdir(other)` and `work_dir=tmp_path`, the `.f` is still written under `tmp_path` (boundary: rooting on the provided base dir, mirrors `ensure-logs-dir`).
- **Contents** follow `work_dir`, not the process CWD: with `monkeypatch.chdir(other)` and `work_dir=tmp_path`, a source at `tmp_path/"src/a.sv"` is written into the `.f` as `src/a.sv` (relpath base `tmp_path`), **not** the `../…/src/a.sv` that a process-CWD base (`other`) would produce (boundary: entry paths root on `work_dir`, so the sim consuming the `.f` with `cwd=work_dir` resolves them).
- `test` whose `value.get_name()` has shell-unsafe chars (e.g. `a/b:c`) → the filelist filename is sanitised to `run.a_b_c.f` under `work_dir` (boundary: `test_tag` regex matches `build-compile-cmd`).
- `model.value` whose `.filelist`/`.path` reference a `-F` include that does not exist, or a missing testbench filelist → `KeyError`/`AttributeError` during resolution → `log.error("filelist_resolve_error", err=…)`, emits `("fail", TestResult.prep(key, test_name, …))`, no abort. (No "model is None" test — the `keyed_join` on `model` makes that unrepresentable.)
- `work_dir` pointing into a read-only directory → `PermissionError` on write → `log.error("filelist_permission_denied", path=…)`, emits `("fail", …)` (boundary: a **write** error logs its own event, distinct from `filelist_resolve_error`).
- `work_dir` whose parent directory is missing → `FileNotFoundError` on write → `log.error("filelist_dir_not_found", …)`, emits `("fail", …)` (boundary: each write/resolve class logs its own event).

## Acceptance criteria

- Tests pass.
- All three output ports exercised: on success `test` forwards the test edge and `filelist` emits `{key, value}`; on a resolve/write error the `fail` path routes a per-test FAIL `result` and logs at ERROR.
- The filelist contents reproduce the byte-for-byte output of rtl_buddy's `VlogFilelist` on the same inputs (modulo ordering if dedup is non-stable).
- The `modules/config.yaml` manifest entry `{ name: write-filelist, class_name: WriteFilelistMod }` validates and the harness resolves `write-filelist` → `WriteFilelistMod`.

## Constraints

- Write the per-tag filename `run.{test_tag}.f` (`test_tag = re.sub(r"[^A-Za-z0-9_.-]", "_", test.get_name())`, the same regex `build-compile-cmd` uses) — **never** the bare `run.f`. This per-tag naming is the interim concurrency mitigation, and needs no serialising lock.
- Root the filename on the provided `work_dir`: `Path(work_dir) / f"run.{test_tag}.f"` — `work_dir` is the validated base directory from `work-dir` (the same provider `ensure-logs-dir` consumes), supplied as a **load-bearing** persistent input. Do **not** compose a CWD-relative `Path(f"run.{test_tag}.f")` — location is decided by the provider, so a relocation (`--work-dir`, regression's per-suite root) is a one-node change.
- Root the `.f` **contents** on `work_dir` too, not just the filename: use `work_dir` (= `path.parent`) as the relpath base for every written entry (`os.path.relpath(entry, work_dir)`) and for the test-filelist prefix (`os.path.relpath(work_dir, path.parent)`), replacing the reference's implicit-CWD base (`vlog_filelist.py:111`) and its `"."`-as-CWD prefix (`:150`). The sim consumes the `.f` with `cwd=work_dir` (spec [03](03-run-process.md)), so a CWD-relative `.f` in a relocated `work_dir` would mis-resolve every source path. Under `work_dir == CWD` the output is byte-identical to the reference.
- Use the `keyed_join` contract over `test` + `model` (joined by key), with `work_dir` as a `persistent_input`. The `model` join means the node is gated until `load-model` produces the resolved `ModelConfig` — there is no "model not yet loaded" runtime case.
- On success emit `("test", test)` then `("filelist", {key, value: <Path>})` in lockstep via the generator.
- **One `except` per failure class** from the resolve/write — write errors `filelist_dir_not_found` (`FileNotFoundError`), `filelist_is_directory` (`IsADirectoryError`), `filelist_permission_denied` (`PermissionError`), `filelist_write_error` (`OSError`, **last** — the others subclass it); resolve errors `filelist_resolve_error` (`KeyError`/`AttributeError` from a missing testbench filelist or an unresolvable `-F` include). Each logs its event with the **exception-specific** fields plus the attempted `path` (**not** `result`/`desc`) and emits `("fail", TestResult.prep(test.key, test.get_name(), <per-case desc>))` on the `fail` port (→ `results-summary`); the per-exception `log.error` drives the exit. Per-test FAIL, not abort. Do **not** collapse them into one `except Exception`/one event.

## Notes

`write-filelist` is one of the few modules reimplementing nontrivial rtl_buddy logic. **The module *is* the native reimplementation of `VlogFilelist` — do not import or construct rtl_buddy's `VlogFilelist`** (that would break the layering: the reimplemented modules under `modules/rtl_buddy/` are deliberately distinct from the upstream `rtl_buddy/src/...` tree the specs cite only as compatibility sources). Port the *behaviour* of `VlogFilelist.write_output`/`_extract`/`_process` into module-private code (a `_write_filelist` helper plus whatever private helpers you factor out) — the option-parsing regex, `-F` recursion with unroll, `+incdir+`/`+libext+` handling, dedup, and the existence checks. `rtl_buddy/src/rtl_buddy/tools/vlog_filelist.py:137-159` (`write_output`, with `_extract`/`_process`) is the authoritative algorithm to mirror, invoked by rtl_buddy with the option set this module fixes — `unroll=True, flatten=False, strip=False, deduplicate=True, test_filelist=test.get_testbench().get_filelist()` (matching `VlogSim._write_filelist`, `tools/vlog_sim.py:88-93`). The model comes from the joined `model.value` edge (the `ModelConfig` `load-model` produced); the port reads its `get_model_path()`/`get_filelist()` to resolve `-F` includes relative to the output `.f`'s directory. Read the reference for the algorithm, but the code lives here, native.

Filelist filename: rtl_buddy writes a single `run.f` in CWD per compile, so concurrent compiles would collide. `write-filelist` therefore writes a **per-tag** path `run.{test_tag}.f`, where `test_tag = re.sub(r"[^A-Za-z0-9_.-]", "_", test.get_name())` (the same regex `build-compile-cmd` uses — spec [07a](07a-build-compile-cmd.md)), rooted on the `work_dir` provider (`Path(work_dir) / f"run.{test_tag}.f"`), and emits that `Path` as the `value` of its `filelist` edge. `build-compile-cmd` reads `filelist.value` straight into `-f`. The per-tag naming is the interim concurrency mitigation; rooting both the filename **and the contents** on `work_dir` brings `run.f` under the same artefact-location provider model as `logs/` (`work-dir` → consumers), and `run-process`'s `cwd=work_dir` (spec [03](03-run-process.md)) makes the `work_dir`-relative contents resolve at the simulator. With that, **CWD-location** is fully decided by the provider for `run.f`, `logs/`, `obj_dir_<tag>/`, the `test.*` symlinks (spec [08e](08e-link-latest.md)), `HierInstanceSeed.txt` (spec [08d](08d-write-randseed.md)), and tool-internal scratch (which the child writes under its `cwd=work_dir`). The remaining residual is **concurrency collision**, not location: the non-verilator configured `simv` is a fixed name (no per-tag prefix) that concurrent tests still share — its isolation waits on the upstream per-invocation-subdir change ([07 item 17](../07-ambiguities-and-assumptions.md)). See [05 — Interim CWD-collision posture](../05-branching-and-results.md#interim-cwd-collision-posture--per-tag-artefact-naming).
