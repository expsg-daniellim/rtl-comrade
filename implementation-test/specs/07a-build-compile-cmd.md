# Spec 07a: build-compile-cmd (`BuildCompileCmdMod`)

**Depends on:** spec 06 (write-filelist), spec [01a](01a-builder-schema.md) (`BuildCompileCmdMod` consumes `RtlBuilderConfig` methods), spec [01b](01b-suite-schema.md) (`BuildCompileCmdMod` reads `test.get_name()`/`get_plusdefines()`).
**References:** [03 — Reusable subprocess core section](../03-module-catalog.md). Parent index: [idx-07 — Compile-cycle modules](../idx-07-compile-cycle.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)` signature, the allowed output forms (plain return / named-port tuple / generator), the `finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py` are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit `a69d962`). This module appends to `modules/rtl_buddy/build.py`, which is created by spec [`06a`](06a-run-preproc.md) — append, do not overwrite. The file is shared with run-process (`03`), the prep modules (`06a`–`06b`, index [idx-06](../idx-06-prep.md)), and the compile-cycle modules (`07a`–`07b`, index [idx-07](../idx-07-compile-cycle.md)); coordinate shared imports and helpers with those specs.

## Goal

Assemble the per-test compile argv (with log paths placed in `command`), emit `simv` as its own edge, and emit the command for `run-process`.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry — the catalog is the design view, this is the build view; update both when behaviour changes. The three outputs are emitted via a generator. The skeleton is **illustrative** — `plusdefines` is constructed per Algorithm step 2 (the Algorithm + Deliverables are authoritative for the list-building details elided here). `keyed_join` joins `test` + `filelist` by key (the `simv` edge is born here as its own `{key, value}` edge).

```
contract:          keyed_join
contract_config:   key_field: key
persistent_inputs: [builder_cfg, builder_mode, logs_dir, work_dir]
inputs:            test, filelist, builder_cfg, logs_dir:Path, work_dir:Path, builder_mode:str = "debug"
outputs:           test    → TestConfig (self-keyed)   (forwarded)
                   simv    → {key, value}   (the compiled simv path)
                   command → {key, argv, stdout_path, stderr_path}
```

`logs_dir` is the **resolved artefact directory** (a `Path`) — this module joins log filenames onto it; do not assume a CWD-relative `"logs"`. `work_dir` is the **validated base directory** (a `Path`) — this module roots `obj_dir_<tag>/` (and, via it, the verilator `simv`) onto it. Both are load-bearing persistent inputs; this module never touches the ambient CWD.

```python
class BuildCompileCmdMod:
    def run(self, test, filelist, builder_cfg, logs_dir, work_dir, builder_mode:str = "debug"):
        test_tag = re.sub(r"[^A-Za-z0-9_.-]", "_", test.get_name())
        exe = builder_cfg.get_exe()
        is_verilator = os.path.basename(exe).startswith("verilator")
        build_dir = str(Path(work_dir) / f"obj_dir_{test_tag}")   # rooted on the validated base dir, not ambient CWD
        simv = f"{build_dir}/simv" if is_verilator else builder_cfg.get_simv()
        argv = [exe, *builder_cfg.get_compile_time_opts(builder_mode)]
        if is_verilator:
            argv += ["--Mdir", build_dir]
        argv += [*plusdefines, "-f", str(filelist.value)]  # plusdefines built per Algorithm step 2
        yield ("test", test)                                       # forward the test edge unchanged
        yield ("simv", KeyedValue(test.key, simv))      # simv born as its own edge
        yield ("command", Command(test.key, argv=argv, stdout_path=str(logs_dir / f"{test_tag}.compile.log"), stderr_path=str(logs_dir / f"{test_tag}.compile.err")))
```

## Algorithm

1. Derive tags and the verilator switch: `test_tag = re.sub(r"[^A-Za-z0-9_.-]", "_", test.get_name())`, `exe = builder_cfg.get_exe()`, `is_verilator = os.path.basename(exe).startswith("verilator")`, `build_dir = str(Path(work_dir) / f"obj_dir_{test_tag}")` (rooted on the validated base dir `work_dir`, not the ambient CWD), and `simv = f"{build_dir}/simv" if is_verilator else builder_cfg.get_simv()` (the caller-side verilator quirk, spec 01a; the verilator `simv` inherits the `work_dir` rooting via `build_dir`).
2. Build the plusdefines list from `test.get_plusdefines()` (spec 01b → `dict | None`): when not `None`, format each entry `f"+define+{k}={v}"`, or `f"+define+{k}"` when `v is None`.
3. Assemble the argv: `[exe, *builder_cfg.get_compile_time_opts(builder_mode)]`, then append `["--Mdir", build_dir]` when `is_verilator`, then `[*plusdefines, "-f", str(filelist.value)]`. Do not `mkdir(logs_dir)` — the directory already exists.
4. Emit three edges via the generator: `("test", test)` (forward unchanged), `("simv", KeyedValue(test.key, simv))` (the compiled simv path — born here as its own edge; `build_dir` is not emitted, unused downstream), and `("command", Command(test.key, argv=argv, stdout_path=str(logs_dir / f"{test_tag}.compile.log"), stderr_path=str(logs_dir / f"{test_tag}.compile.err")))`. `logs_dir` is a resolved `Path`; join filenames onto it (`logs_dir / name`) — do not assume a CWD-relative `"logs"`.
5. **Failure — bad builder mode.** No catch here: `builder_cfg.get_compile_time_opts(builder_mode)` itself `log.fatal`s (immediate exit) if `builder_mode` is unknown or its `compile_time` is `None` (spec 01a) — system-wide misconfiguration, not per-test.

## Deliverables

In `modules/rtl_buddy/build.py`:

- `BuildCompileCmdMod` — `(test, filelist, builder_cfg, logs_dir:Path, work_dir:Path, builder_mode:str="debug")`, `keyed_join` over `test` + `filelist` (joined by key) with the config singletons as `persistent_inputs` → assembles the argv as `[builder_cfg.get_exe()] + builder_cfg.get_compile_time_opts(builder_mode) + (["--Mdir", build_dir] if is_verilator else []) + plusdefines + ["-f", filelist.value]`, where `is_verilator = os.path.basename(builder_cfg.get_exe()).startswith("verilator")` (the caller-side verilator switch documented in spec [01a — Verilator quirk](01a-builder-schema.md)). Computes `test_tag = re.sub(r"[^A-Za-z0-9_.-]", "_", test.get_name())`, `build_dir = str(Path(work_dir) / f"obj_dir_{test_tag}")` (rooted on the validated base directory `work_dir` — **load-bearing** persistent input), and `simv = f"{build_dir}/simv" if is_verilator else builder_cfg.get_simv()` (mirrors `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:61-80`; the verilator `simv` inherits the `work_dir` rooting via `build_dir`). Emits `simv` as **its own `{key, value}` edge**; does not emit `build_dir` (not needed downstream). Does not `mkdir(logs_dir)` — the directory already exists. `plusdefines` is built from `test.get_plusdefines()` (spec [01b](01b-suite-schema.md) — returns `dict | None`; when not `None`, format each entry as `f"+define+{k}={v}"` or `f"+define+{k}"` for `v is None`, mirroring `vlog_sim.py:107-117`). Compile log paths are composed by joining onto the resolved `logs_dir` `Path`: `str(logs_dir / f"{test_tag}.compile.log")` and `.compile.err`. This module never references the ambient CWD — `logs_dir` and `work_dir` already encode the artefact location. Emits:
  - `("test", test)` — forwards the test edge unchanged
  - `("simv", KeyedValue(key, simv))` — the compiled simv path, born here
  - `("command", Command(key, argv, stdout_path, stderr_path))` — log paths under `logs_dir`.
  **Failure handling**: `builder_cfg.get_compile_time_opts(builder_mode)` calls `log.fatal` (immediate `typer.Exit(1)`) if `builder_mode` is not in `builder_cfg.opts` or the mode's `compile_time` is `None` — see spec [01a](01a-builder-schema.md). No catching; system-wide misconfiguration.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:141-159` — `VlogSim.compile` argv assembly; helpers `_get_build_tag`/`_get_build_dir`/`_get_simv_path` at `vlog_sim.py:61-80`, `_get_plusdefines` at `:107-117`.

**Manifest** — append to the `- file: rtl_buddy/build.py` block in `modules/config.yaml` (opened by [`06a`](06a-run-preproc.md); append, don't re-create):

```yaml
  - { name: build-compile-cmd, class_name: BuildCompileCmdMod }
```

## Tests

In `modules/tests/test_compile_cycle.py`. Fixtures: `builder_cfg` doubles (one verilator `exe`, one non-verilator) exposing `get_exe`/`get_simv`/`get_compile_time_opts`; a `test` edge fixture (`{key, value}`, value exposing `get_name`/`get_plusdefines`), a `filelist` edge (`{key, value}`), and `work_dir=tmp_path` passed as the base-dir port; `logging_handler` for the bad-mode path. Drive `run(test, filelist, …)` directly — the `keyed_join` is the contract's concern.

- Non-verilator builder, `get_plusdefines()` is `None` → yields `("test", test)`, `("simv", KeyedValue(key, builder_cfg.get_simv()))`, then `("command", {argv, stdout_path, stderr_path})` where `argv == [exe, *compile_opts, "-f", str(filelist.value)]` (matches `VlogSim.compile`).
- Verilator builder (`os.path.basename(exe).startswith("verilator")`), `work_dir=tmp_path` → `argv` contains `["--Mdir", str(tmp_path / "obj_dir_{tag}")]` and the `simv` edge's `value == f"{tmp_path / 'obj_dir_{tag}'}/simv"` (boundary: verilator switch derives `simv`/`build_dir` differently, both rooted on `work_dir`).
- `build_dir`/verilator `simv` root on `work_dir`, **not** the process CWD: with `monkeypatch.chdir(other)` and `work_dir=tmp_path`, `--Mdir` and the `simv` edge value still sit under `tmp_path` (boundary: rooting on the provided base dir, mirrors `ensure-logs-dir`).
- `get_plusdefines()` returns `{"FOO": 1, "BAR": None}` → `argv` contains `"+define+FOO=1"` and `"+define+BAR"` (boundary: `None`-valued define formats without `=`).
- `logs_dir=Path("/work/custom")` (a resolved dir) → `command.stdout_path == "/work/custom/{tag}.compile.log"` and `stderr_path == "/work/custom/{tag}.compile.err"` (paths are joined onto the provided directory; the module does not assume a CWD-relative `"logs"`). `logs_dir` and `work_dir` are independent base dirs — log files follow `logs_dir`, `obj_dir_<tag>/` follows `work_dir`.
- `test.get_name()` has shell-unsafe chars → `test_tag` is sanitised in `build_dir`, verilator `simv`, and both log paths (boundary: `test_tag` regex).
- `builder_mode` unknown to the builder → `get_compile_time_opts` `log.fatal`s → `pytest.raises(typer.Exit)` (not caught here — system-wide misconfiguration).

## Acceptance criteria

- Tests pass.
- All three output ports (`test`, `simv`, `command`) are exercised: the `simv` edge `value` is set per builder type and `command` carries the `logs_dir`-prefixed `stdout_path`/`stderr_path`.
- No port-routed failure path (the compile `rc` is interpreted downstream by `interpret-compile`).
- Wiring `build-compile-cmd` → `run-process` (instance #1) → `interpret-compile` end-to-end against a real builder surfaces a non-zero `rc` on a known bad source file.
- The `modules/config.yaml` manifest entry `{ name: build-compile-cmd, class_name: BuildCompileCmdMod }` validates and the harness resolves `build-compile-cmd` → `BuildCompileCmdMod`.

## Constraints

- Detect verilator on `os.path.basename(builder_cfg.get_exe()).startswith("verilator")` (the `exe`, not `name`); `simv = f"{build_dir}/simv"` for verilator else `builder_cfg.get_simv()`.
- Do **not** `mkdir(logs_dir)` — the directory already exists.
- `logs_dir` is a resolved artefact `Path` — compose paths by joining onto it (`logs_dir / name`); do **not** assume a CWD-relative `"logs"` string or read the ambient CWD.
- Root `build_dir` on the provided `work_dir`: `build_dir = str(Path(work_dir) / f"obj_dir_{test_tag}")` — `work_dir` is the validated base directory, supplied as a **load-bearing** persistent input. Do **not** compose a CWD-relative `f"obj_dir_{test_tag}"`; the verilator `simv = f"{build_dir}/simv"` then inherits the rooting for free.
- Emit `simv` as its own `{key, value}` edge (`("simv", KeyedValue(test.key, simv))`); do **not** emit `build_dir` (unused downstream).
- Do **not** catch `get_compile_time_opts(builder_mode)` — it `log.fatal`s on an unknown mode / `None` opts (spec [01a](01a-builder-schema.md)); this is system-wide misconfiguration, not per-test.
- `keyed_join` over `test` + `filelist` (key_field `key`); the config singletons (`builder_cfg`/`builder_mode`/`logs_dir`/`work_dir`) are `persistent_inputs`. Emit `("test", ...)`, `("simv", ...)`, `("command", ...)` via the generator.
- `build_dir`/verilator `simv` are per-tag **and** rooted on `work_dir`; do **not** add a lock for the residual non-verilator configured `simv` — that fixed, config-supplied name the graph can't redirect waits on [07 item 17](../07-ambiguities-and-assumptions.md).

## Notes

`simv` is emitted by `build-compile-cmd` as its own `{key, value}` edge — `build-sim-cmd` joins it by key. `build_dir` is not emitted (not needed downstream).

**Concurrency note (item 17).** `build_dir = str(Path(work_dir) / f"obj_dir_{test_tag}")` and the verilator `simv = f"{build_dir}/simv"` are per-tag **and** rooted on the `work_dir` provider, so they don't collide across concurrent tests and relocate as a one-node change — the same artefact-location model `logs/` uses. The `-f` filelist is likewise per-tag and `work_dir`-rooted because `write-filelist` writes `Path(work_dir) / f"run.{test_tag}.f"` (spec [06b](06b-write-filelist.md)) and this module reads `filelist.value` straight into `-f`. **Residual:** for non-verilator builders `simv = builder_cfg.get_simv()` is a *fixed configured* name with no per-tag prefix that the graph can't freely redirect; its isolation waits on the upstream per-invocation-subdir change ([07 item 17](../07-ambiguities-and-assumptions.md)). Do not add a lock for it; see [05 — Interim CWD-collision posture](../05-branching-and-results.md#interim-cwd-collision-posture--per-tag-artefact-naming).
