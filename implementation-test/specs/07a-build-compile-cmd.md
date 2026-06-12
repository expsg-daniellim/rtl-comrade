# Spec 07a: build-compile-cmd (`BuildCompileCmdMod`)

**Depends on:** spec 06 (write-filelist), spec [01a](01a-builder-schema.md)
(`BuildCompileCmdMod` consumes `RtlBuilderConfig` methods), spec
[01b](01b-suite-schema.md) (`BuildCompileCmdMod` reads
`ctx["test"].get_name()`/`get_plusdefines()`).
**References:** [03 — Reusable subprocess core section](../03-module-catalog.md). Parent
index: [07 — Compile-cycle modules](07-compile-cycle-modules.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)`
signature, the allowed output forms (plain return / named-port tuple / generator), the
`finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py`
are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry
below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit
`a69d962`). This module appends to `modules/rtl_buddy/build.py`, which is created by spec
[`06a`](06a-run-preproc.md) — append, do not overwrite. The file is shared with run-process
(`03`), the prep modules (`06a`–`06b`, index [06](06-prep-modules.md)), and the compile-cycle
modules (`07a`–`07b`, index [07](07-compile-cycle-modules.md)); coordinate shared imports and
helpers with those specs.

## Goal

Assemble the per-test compile argv (with log paths placed in `command`), fold `simv` into
`ctx`, and emit the command for `run-process`.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry —
the catalog is the design view, this is the build view; update both when behaviour changes.
Both outputs are emitted in lockstep via a generator.

```
contract:          default
persistent_inputs: [builder_cfg, builder_mode, logs_dir]
inputs:            ctx, filelist, builder_cfg, builder_mode:str = "debug", logs_dir:str = "logs"
outputs:           ctx     → ctx   (with simv folded in)
                   command → {key, argv, stdout_path, stderr_path}
```

```python
class BuildCompileCmdMod:
    def run(self, ctx, filelist, builder_cfg, builder_mode:str = "debug", logs_dir:str = "logs"):
        test_tag = re.sub(r"[^A-Za-z0-9_.-]", "_", ctx["test"].get_name())
        exe = builder_cfg.get_exe()
        is_verilator = os.path.basename(exe).startswith("verilator")
        build_dir = f"obj_dir_{test_tag}"
        simv = f"{build_dir}/simv" if is_verilator else builder_cfg.get_simv()
        argv = [exe, *builder_cfg.get_compile_time_opts(builder_mode)]
        if is_verilator:
            argv += ["--Mdir", build_dir]
        argv += [*plusdefines, "-f", str(filelist["filelist"])]
        ctx = { **ctx, "simv": simv }
        yield ("ctx", ctx)
        yield ("command", { "key": ctx["key"], "argv": argv,
                            "stdout_path": f"{logs_dir}/{test_tag}.compile.log",
                            "stderr_path": f"{logs_dir}/{test_tag}.compile.err" })
```

## Algorithm

1. Derive tags and the verilator switch: `test_tag = re.sub(r"[^A-Za-z0-9_.-]", "_",
   ctx["test"].get_name())`, `exe = builder_cfg.get_exe()`, `is_verilator =
   os.path.basename(exe).startswith("verilator")`, `build_dir = f"obj_dir_{test_tag}"`, and
   `simv = f"{build_dir}/simv" if is_verilator else builder_cfg.get_simv()` (the caller-side
   verilator quirk, spec 01a).
2. Build the plusdefines list from `ctx["test"].get_plusdefines()` (spec 01b → `dict | None`):
   when not `None`, format each entry `f"+define+{k}={v}"`, or `f"+define+{k}"` when `v is
   None`.
3. Assemble the argv: `[exe, *builder_cfg.get_compile_time_opts(builder_mode)]`, then append
   `["--Mdir", build_dir]` when `is_verilator`, then `[*plusdefines, "-f",
   str(filelist["filelist"])]`. Do not `mkdir(logs_dir)` — `ensure-logs-dir` already created it.
4. Fold `simv` into ctx (`ctx = {**ctx, "simv": simv}`; `build_dir` is not carried — unused
   downstream) and emit in lockstep: `("ctx", ctx)` then `("command", {"key": ctx["key"],
   "argv": argv, "stdout_path": f"{logs_dir}/{test_tag}.compile.log", "stderr_path":
   f"{logs_dir}/{test_tag}.compile.err"})`.
5. **Failure — bad builder mode.** No catch here:
   `builder_cfg.get_compile_time_opts(builder_mode)` itself `log.critical`s (immediate exit) if
   `builder_mode` is unknown or its `compile_time` is `None` (spec 01a) — system-wide
   misconfiguration, not per-test.

## Deliverables

In `modules/rtl_buddy/build.py`:

- `BuildCompileCmdMod` — `(ctx, filelist, builder_cfg, builder_mode:str="debug", logs_dir:str="logs")` →
  assembles the argv as
  `[builder_cfg.get_exe()] + builder_cfg.get_compile_time_opts(builder_mode) + (["--Mdir", build_dir] if is_verilator else []) + plusdefines + ["-f", filelist["filelist"]]`,
  where `is_verilator = os.path.basename(builder_cfg.get_exe()).startswith("verilator")`
  (the caller-side verilator switch documented in spec [01a — Verilator
  quirk](01a-builder-schema.md)). Computes `test_tag = re.sub(r"[^A-Za-z0-9_.-]", "_",
  ctx["test"].get_name())`, `build_dir = f"obj_dir_{test_tag}"`, and `simv =
  f"{build_dir}/simv" if is_verilator else builder_cfg.get_simv()` (mirrors
  `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:61-80`). Folds `simv` into `ctx`
  (`ctx["simv"] = simv`); does not fold `build_dir` (not needed downstream). Does not
  `mkdir(logs_dir)` — `ensure-logs-dir` has already bootstrapped the directory via the
  env_ready chain. `plusdefines` is built from `ctx["test"].get_plusdefines()` (spec
  [01b](01b-suite-schema.md) — returns `dict | None`; when not `None`, format each entry
  as `f"+define+{k}={v}"` or `f"+define+{k}"` for `v is None`, mirroring
  `vlog_sim.py:107-117`). Compile log paths are composed as
  `f"{logs_dir}/{test_tag}.compile.log"` and `.err`.
  Emits:
  - `("ctx", ctx_with_simv)` — ctx now carries `simv`
  - `("command", {"key", "argv", "stdout_path", "stderr_path"})` — log paths under `logs_dir`.
  **Failure handling**: `builder_cfg.get_compile_time_opts(builder_mode)` calls
  `log.critical` (immediate `SystemExit(1)`) if `builder_mode` is not in
  `builder_cfg.opts` or the mode's `compile_time` is `None` — see spec
  [01a](01a-builder-schema.md). No catching; system-wide misconfiguration.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:141-159` — `VlogSim.compile` argv assembly; helpers `_get_build_tag`/`_get_build_dir`/`_get_simv_path` at `vlog_sim.py:61-80`, `_get_plusdefines` at `:107-117`.

**Manifest** — append to the `- file: rtl_buddy/build.py` block in `modules/config.yaml`
(opened by [`06a`](06a-run-preproc.md); append, don't re-create):

```yaml
  - { name: build-compile-cmd, class_name: BuildCompileCmdMod }
```

## Tests

In `modules/tests/test_compile_cycle.py`. Fixtures: `builder_cfg` doubles (one verilator
`exe`, one non-verilator) exposing `get_exe`/`get_simv`/`get_compile_time_opts`; a `ctx`
fixture (with `test.get_name`/`get_plusdefines`) and a `filelist` dict; `logging_handler`
for the bad-mode path.

- Non-verilator builder, `get_plusdefines()` is `None` → yields `("ctx", ctx_with_simv)` with
  `ctx["simv"] == builder_cfg.get_simv()`, then `("command", {argv, stdout_path, stderr_path})`
  where `argv == [exe, *compile_opts, "-f", str(filelist["filelist"])]` (matches `VlogSim.compile`).
- Verilator builder (`os.path.basename(exe).startswith("verilator")`) → `argv` contains
  `["--Mdir", "obj_dir_{tag}"]` and `ctx["simv"] == "obj_dir_{tag}/simv"` (boundary: verilator
  switch derives `simv`/`build_dir` differently).
- `get_plusdefines()` returns `{"FOO": 1, "BAR": None}` → `argv` contains `"+define+FOO=1"`
  and `"+define+BAR"` (boundary: `None`-valued define formats without `=`).
- `logs_dir="custom"` → `command["stdout_path"] == "custom/{tag}.compile.log"` and
  `stderr_path == "custom/{tag}.compile.err"`; default `"logs"` yields `logs/{tag}.compile.*`
  (rtl_buddy parity).
- `ctx["test"].get_name()` has shell-unsafe chars → `test_tag` is sanitised in `build_dir`,
  verilator `simv`, and both log paths (boundary: `test_tag` regex).
- `builder_mode` unknown to the builder → `get_compile_time_opts` `log.critical`s →
  `pytest.raises(SystemExit)` (not caught here — system-wide misconfiguration).

## Acceptance criteria

- Tests pass.
- Both output ports (`ctx`, `command`) are exercised in lockstep: `ctx["simv"]` is set per
  builder type and `command` carries the `logs_dir`-prefixed `stdout_path`/`stderr_path`.
- No port-routed failure path (the compile `rc` is interpreted downstream by
  `interpret-compile`).
- Wiring `build-compile-cmd` → `run-process` (instance #1) → `interpret-compile` end-to-end
  against a real builder surfaces a non-zero `rc` on a known bad source file (see
  [07 index](07-compile-cycle-modules.md#acceptance-criteria)).
- The `modules/config.yaml` manifest entry `{ name: build-compile-cmd, class_name: BuildCompileCmdMod }`
  validates and the harness resolves `build-compile-cmd` → `BuildCompileCmdMod`.

## Constraints

- Detect verilator on `os.path.basename(builder_cfg.get_exe()).startswith("verilator")` (the
  `exe`, not `name`); `simv = f"{build_dir}/simv"` for verilator else `builder_cfg.get_simv()`.
- Do **not** `mkdir(logs_dir)` — `ensure-logs-dir` already bootstrapped it.
- Fold `simv` into `ctx`; do **not** fold `build_dir` (unused downstream).
- Do **not** catch `get_compile_time_opts(builder_mode)` — it `log.critical`s on an unknown
  mode / `None` opts (spec [01a](01a-builder-schema.md)); this is system-wide misconfiguration,
  not per-test.
- Emit `("ctx", ...)` then `("command", ...)` in lockstep via the generator.
- `build_dir`/verilator `simv` are already per-tag; do **not** add a lock for the residual
  non-verilator `simv` (TODO #30) — that waits on [07 item 17](../07-ambiguities-and-assumptions.md).

## Notes

`simv` is set by `build-compile-cmd` and carried in `ctx` — `build-sim-cmd` reads it
directly. `build_dir` is not in `ctx` (not needed downstream).

**Concurrency note (TODO #30 / item 17).** `build_dir = f"obj_dir_{test_tag}"` and the
verilator `simv = f"{build_dir}/simv"` are already per-tag, so they don't collide across
concurrent tests. The `-f` filelist is per-tag because `write-filelist` writes
`run.{test_tag}.f` (spec [06b](06b-write-filelist.md)) and this module passes
`filelist["filelist"]` through unchanged — no edit needed here. **Residual:** for
non-verilator builders `simv = builder_cfg.get_simv()` is a *fixed configured* name with
no per-tag prefix, which the graph can't freely redirect; its isolation waits on the
upstream per-invocation-subdir change ([07 item 17](../07-ambiguities-and-assumptions.md)).
Do not add a lock for it — the `serial_acquire` shim was removed (TODO #30); see
[05 — Interim CWD-collision posture](../05-branching-and-results.md#interim-cwd-collision-posture--per-tag-artefact-naming).
