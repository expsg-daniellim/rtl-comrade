# Spec 07a: build-compile-cmd (`BuildCompileCmdMod`)

**Depends on:** spec 06 (write-filelist), spec [01a](01a-builder-schema.md) (`BuildCompileCmdMod` consumes `RtlBuilderConfig` methods), spec [01b](01b-suite-schema.md) (`BuildCompileCmdMod` reads `ctx["test"].get_name()`/`get_plusdefines()`).
**References:** [03 — Reusable subprocess core section](../03-module-catalog.md). Parent index: [idx-07 — Compile-cycle modules](../idx-07-compile-cycle.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)` signature, the allowed output forms (plain return / named-port tuple / generator), the `finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py` are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit `a69d962`). This module appends to `modules/rtl_buddy/build.py`, which is created by spec [`06a`](06a-run-preproc.md) — append, do not overwrite. The file is shared with run-process (`03`), the prep modules (`06a`–`06b`, index [idx-06](../idx-06-prep.md)), and the compile-cycle modules (`07a`–`07b`, index [idx-07](../idx-07-compile-cycle.md)); coordinate shared imports and helpers with those specs.

## Goal

Assemble the per-test compile argv (with log paths placed in `command`), fold `simv` into `ctx`, and emit the command for `run-process`.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry — the catalog is the design view, this is the build view; update both when behaviour changes. Both outputs are emitted in lockstep via a generator. The skeleton is **illustrative** — `plusdefines` is constructed per Algorithm step 2 (the Algorithm + Deliverables are authoritative for the list-building details elided here).

```
contract:          default
persistent_inputs: [builder_cfg, builder_mode, logs_dir, work_dir]
inputs:            ctx, filelist, builder_cfg, logs_dir:Path, work_dir:Path, builder_mode:str = "debug"
outputs:           ctx     → ctx   (with simv folded in)
                   command → {key, argv, stdout_path, stderr_path}
```

`logs_dir` is the **resolved artefact directory** (a `Path`) supplied by `ensure-logs-dir`, not the CLI subdir name — this module joins log filenames onto it. `work_dir` is the **validated base directory** (a `Path`) supplied by `check-suite-cwd` — the artefact-location provider that roots `obj_dir_<tag>/` (and, via it, the verilator `simv`). Both are load-bearing persistent inputs; this module never touches the ambient CWD.

```python
class BuildCompileCmdMod:
    def run(self, ctx, filelist, builder_cfg, logs_dir, work_dir, builder_mode:str = "debug"):
        test_tag = re.sub(r"[^A-Za-z0-9_.-]", "_", ctx["test"].get_name())
        exe = builder_cfg.get_exe()
        is_verilator = os.path.basename(exe).startswith("verilator")
        build_dir = str(Path(work_dir) / f"obj_dir_{test_tag}")   # rooted on the validated base dir, not ambient CWD
        simv = f"{build_dir}/simv" if is_verilator else builder_cfg.get_simv()
        argv = [exe, *builder_cfg.get_compile_time_opts(builder_mode)]
        if is_verilator:
            argv += ["--Mdir", build_dir]
        argv += [*plusdefines, "-f", str(filelist["filelist"])]  # plusdefines built per Algorithm step 2
        ctx = { **ctx, "simv": simv }
        yield ("ctx", ctx)
        yield ("command", { "key": ctx["key"], "argv": argv,
                            "stdout_path": str(logs_dir / f"{test_tag}.compile.log"),
                            "stderr_path": str(logs_dir / f"{test_tag}.compile.err") })
```

## Algorithm

1. Derive tags and the verilator switch: `test_tag = re.sub(r"[^A-Za-z0-9_.-]", "_", ctx["test"].get_name())`, `exe = builder_cfg.get_exe()`, `is_verilator = os.path.basename(exe).startswith("verilator")`, `build_dir = str(Path(work_dir) / f"obj_dir_{test_tag}")` (rooted on the validated base dir from `check-suite-cwd`, not the ambient CWD), and `simv = f"{build_dir}/simv" if is_verilator else builder_cfg.get_simv()` (the caller-side verilator quirk, spec 01a; the verilator `simv` inherits the `work_dir` rooting via `build_dir`).
2. Build the plusdefines list from `ctx["test"].get_plusdefines()` (spec 01b → `dict | None`): when not `None`, format each entry `f"+define+{k}={v}"`, or `f"+define+{k}"` when `v is None`.
3. Assemble the argv: `[exe, *builder_cfg.get_compile_time_opts(builder_mode)]`, then append `["--Mdir", build_dir]` when `is_verilator`, then `[*plusdefines, "-f", str(filelist["filelist"])]`. Do not `mkdir(logs_dir)` — `ensure-logs-dir` already created it.
4. Fold `simv` into ctx (`ctx = {**ctx, "simv": simv}`; `build_dir` is not carried — unused downstream) and emit in lockstep: `("ctx", ctx)` then `("command", {"key": ctx["key"], "argv": argv, "stdout_path": str(logs_dir / f"{test_tag}.compile.log"), "stderr_path": str(logs_dir / f"{test_tag}.compile.err")})`. `logs_dir` is the resolved `Path` from `ensure-logs-dir`; join filenames onto it (`logs_dir / name`) — do not assume a CWD-relative `"logs"`.
5. **Failure — bad builder mode.** No catch here: `builder_cfg.get_compile_time_opts(builder_mode)` itself `log.fatal`s (immediate exit) if `builder_mode` is unknown or its `compile_time` is `None` (spec 01a) — system-wide misconfiguration, not per-test.

## Deliverables

In `modules/rtl_buddy/build.py`:

- `BuildCompileCmdMod` — `(ctx, filelist, builder_cfg, logs_dir:Path, work_dir:Path, builder_mode:str="debug")` → assembles the argv as `[builder_cfg.get_exe()] + builder_cfg.get_compile_time_opts(builder_mode) + (["--Mdir", build_dir] if is_verilator else []) + plusdefines + ["-f", filelist["filelist"]]`, where `is_verilator = os.path.basename(builder_cfg.get_exe()).startswith("verilator")` (the caller-side verilator switch documented in spec [01a — Verilator quirk](01a-builder-schema.md)). Computes `test_tag = re.sub(r"[^A-Za-z0-9_.-]", "_", ctx["test"].get_name())`, `build_dir = str(Path(work_dir) / f"obj_dir_{test_tag}")` (rooted on the validated base directory `work_dir` from `check-suite-cwd` — the same artefact-location provider `ensure-logs-dir` consumes; **load-bearing** persistent input), and `simv = f"{build_dir}/simv" if is_verilator else builder_cfg.get_simv()` (mirrors `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:61-80`; the verilator `simv` inherits the `work_dir` rooting via `build_dir`). Folds `simv` into `ctx` (`ctx["simv"] = simv`); does not fold `build_dir` (not needed downstream). Does not `mkdir(logs_dir)` — `ensure-logs-dir` has already bootstrapped the directory. `plusdefines` is built from `ctx["test"].get_plusdefines()` (spec [01b](01b-suite-schema.md) — returns `dict | None`; when not `None`, format each entry as `f"+define+{k}={v}"` or `f"+define+{k}"` for `v is None`, mirroring `vlog_sim.py:107-117`). Compile log paths are composed by joining onto the resolved `logs_dir` `Path` supplied by `ensure-logs-dir`: `str(logs_dir / f"{test_tag}.compile.log")` and `.compile.err`. This module never references the ambient CWD — `logs_dir` already encodes the artefact location decided once by `check-suite-cwd`/`ensure-logs-dir`. Emits:
  - `("ctx", ctx_with_simv)` — ctx now carries `simv`
  - `("command", {"key", "argv", "stdout_path", "stderr_path"})` — log paths under `logs_dir`.
  **Failure handling**: `builder_cfg.get_compile_time_opts(builder_mode)` calls `log.fatal` (immediate `typer.Exit(1)`) if `builder_mode` is not in `builder_cfg.opts` or the mode's `compile_time` is `None` — see spec [01a](01a-builder-schema.md). No catching; system-wide misconfiguration.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:141-159` — `VlogSim.compile` argv assembly; helpers `_get_build_tag`/`_get_build_dir`/`_get_simv_path` at `vlog_sim.py:61-80`, `_get_plusdefines` at `:107-117`.

**Manifest** — append to the `- file: rtl_buddy/build.py` block in `modules/config.yaml` (opened by [`06a`](06a-run-preproc.md); append, don't re-create):

```yaml
  - { name: build-compile-cmd, class_name: BuildCompileCmdMod }
```

## Tests

In `modules/tests/test_compile_cycle.py`. Fixtures: `builder_cfg` doubles (one verilator `exe`, one non-verilator) exposing `get_exe`/`get_simv`/`get_compile_time_opts`; a `ctx` fixture (with `test.get_name`/`get_plusdefines`), a `filelist` dict, and `work_dir=tmp_path` passed as the base-dir port; `logging_handler` for the bad-mode path.

- Non-verilator builder, `get_plusdefines()` is `None` → yields `("ctx", ctx_with_simv)` with `ctx["simv"] == builder_cfg.get_simv()`, then `("command", {argv, stdout_path, stderr_path})` where `argv == [exe, *compile_opts, "-f", str(filelist["filelist"])]` (matches `VlogSim.compile`).
- Verilator builder (`os.path.basename(exe).startswith("verilator")`), `work_dir=tmp_path` → `argv` contains `["--Mdir", str(tmp_path / "obj_dir_{tag}")]` and `ctx["simv"] == f"{tmp_path / 'obj_dir_{tag}'}/simv"` (boundary: verilator switch derives `simv`/`build_dir` differently, both rooted on `work_dir`).
- `build_dir`/verilator `simv` root on `work_dir`, **not** the process CWD: with `monkeypatch.chdir(other)` and `work_dir=tmp_path`, `--Mdir` and `ctx["simv"]` still sit under `tmp_path` (boundary: rooting on the provided base dir, mirrors `ensure-logs-dir`).
- `get_plusdefines()` returns `{"FOO": 1, "BAR": None}` → `argv` contains `"+define+FOO=1"` and `"+define+BAR"` (boundary: `None`-valued define formats without `=`).
- `logs_dir=Path("/work/custom")` (resolved dir from `ensure-logs-dir`) → `command["stdout_path"] == "/work/custom/{tag}.compile.log"` and `stderr_path == "/work/custom/{tag}.compile.err"` (paths are joined onto the provided directory; the module does not assume a CWD-relative `"logs"`). `logs_dir` and `work_dir` are independent base dirs — log files follow `logs_dir`, `obj_dir_<tag>/` follows `work_dir`.
- `ctx["test"].get_name()` has shell-unsafe chars → `test_tag` is sanitised in `build_dir`, verilator `simv`, and both log paths (boundary: `test_tag` regex).
- `builder_mode` unknown to the builder → `get_compile_time_opts` `log.fatal`s → `pytest.raises(typer.Exit)` (not caught here — system-wide misconfiguration).

## Acceptance criteria

- Tests pass.
- Both output ports (`ctx`, `command`) are exercised in lockstep: `ctx["simv"]` is set per builder type and `command` carries the `logs_dir`-prefixed `stdout_path`/`stderr_path`.
- No port-routed failure path (the compile `rc` is interpreted downstream by `interpret-compile`).
- Wiring `build-compile-cmd` → `run-process` (instance #1) → `interpret-compile` end-to-end against a real builder surfaces a non-zero `rc` on a known bad source file.
- The `modules/config.yaml` manifest entry `{ name: build-compile-cmd, class_name: BuildCompileCmdMod }` validates and the harness resolves `build-compile-cmd` → `BuildCompileCmdMod`.

## Constraints

- Detect verilator on `os.path.basename(builder_cfg.get_exe()).startswith("verilator")` (the `exe`, not `name`); `simv = f"{build_dir}/simv"` for verilator else `builder_cfg.get_simv()`.
- Do **not** `mkdir(logs_dir)` — `ensure-logs-dir` already bootstrapped it.
- `logs_dir` is the resolved artefact `Path` from `ensure-logs-dir` — compose paths by joining onto it (`logs_dir / name`); do **not** assume a CWD-relative `"logs"` string or read the ambient CWD.
- Root `build_dir` on the provided `work_dir`: `build_dir = str(Path(work_dir) / f"obj_dir_{test_tag}")` — `work_dir` is the validated base directory from `check-suite-cwd` (the same provider `ensure-logs-dir` consumes), supplied as a **load-bearing** persistent input. Do **not** compose a CWD-relative `f"obj_dir_{test_tag}"`; the verilator `simv = f"{build_dir}/simv"` then inherits the rooting for free.
- Fold `simv` into `ctx`; do **not** fold `build_dir` (unused downstream).
- Do **not** catch `get_compile_time_opts(builder_mode)` — it `log.fatal`s on an unknown mode / `None` opts (spec [01a](01a-builder-schema.md)); this is system-wide misconfiguration, not per-test.
- Emit `("ctx", ...)` then `("command", ...)` in lockstep via the generator.
- `build_dir`/verilator `simv` are already per-tag **and** now rooted on `work_dir` (R14); do **not** add a lock for the residual non-verilator configured `simv` — that fixed, config-supplied name the graph can't redirect waits on [07 item 17](../07-ambiguities-and-assumptions.md).

## Notes

`simv` is set by `build-compile-cmd` and carried in `ctx` — `build-sim-cmd` reads it directly. `build_dir` is not in `ctx` (not needed downstream).

**Input-pairing assumption (TO DOCUMENT).** This node is a `default` contract with two per-test streaming inputs, `ctx` and `filelist`, that must correspond. They pair correctly only because their shared producer (`write-filelist`, spec [06b](06b-write-filelist.md)) emits `("ctx", …)` and `("filelist", …)` in lockstep for each test, and `default` pairs its inputs positionally (it is **not** `keyed_join` — `keyed_join` is reserved for the streams that subprocess timing decouples: `interpret-compile`, `write-randseed`). Inserting a node between producer and consumer, or reordering the producer's emissions, would silently mismatch `ctx`↔`filelist`. This positional-pairing guarantee of the `default` contract is load-bearing here and is not yet spelled out in `docs/contracts/default.md` — document it there (and the same pattern in `build-sim-cmd`, spec [08c](08c-build-sim-cmd.md), which pairs `ctx`+`seed`).

**Concurrency note (item 17 / R14).** `build_dir = str(Path(work_dir) / f"obj_dir_{test_tag}")` and the verilator `simv = f"{build_dir}/simv"` are per-tag **and** rooted on the `work_dir` provider (R14), so they don't collide across concurrent tests and relocate as a one-node change — the same artefact-location model `logs/` uses. The `-f` filelist is likewise per-tag and `work_dir`-rooted because `write-filelist` writes `Path(work_dir) / f"run.{test_tag}.f"` (spec [06b](06b-write-filelist.md)) and this module passes `filelist["filelist"]` through unchanged — no edit needed here. **Residual:** for non-verilator builders `simv = builder_cfg.get_simv()` is a *fixed configured* name with no per-tag prefix that the graph can't freely redirect; its isolation waits on the upstream per-invocation-subdir change ([07 item 17](../07-ambiguities-and-assumptions.md)). Do not add a lock for it; see [05 — Interim CWD-collision posture](../05-branching-and-results.md#interim-cwd-collision-posture--per-tag-artefact-naming).
