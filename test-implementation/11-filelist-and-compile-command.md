# Spec 11: FilelistGenerate + CompileCommandBuild

## What this covers

Implement `FilelistGenerate` and `CompileCommandBuild` in `modules/rtl_buddy_compat/compile.py`. These two are kept together because `FilelistArtefact` embeds the `PreprocessedRunPlan`, making `CompileCommandBuild` directly downstream of `FilelistGenerate` with a tight data dependency. Neither runs a subprocess — that is spec 12.

## Prerequisites

Spec 00 (artefacts) must be complete.

## Before you start

Read:
- `rtl_buddy/src/rtl_buddy/tools/vlog_filelist.py` — full file; port `_extract()` and `_process()` logic
- `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:L61-L93` — build dir, safe test name, filelist write call
- `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:L108-L119` — plusdefine construction
- `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:L143-L166` — compile command construction
- `rtl_buddy/src/rtl_buddy/config/rtl.py:L43-L60` — `get_compile_time_opts(mode)`

## File: `modules/rtl_buddy_compat/compile.py`

Create this file. Spec 12 (`CompileExecute`) will be added to it.

### `FilelistGenerate`

```
contract: default
inputs:  preprocessed: PreprocessedRunPlan
outputs: default → FilelistArtefact
```

Implementation steps:

1. Compute `safe_name`: replace any character not in `[a-zA-Z0-9_]` with `_` in `preprocessed.test.name`.
2. `build_dir = os.path.join(preprocessed.test.model_path_parent, safe_name)` — use whatever project-relative build dir convention matches `vlog_sim.py:L61-L71`. Create it if absent.
3. `output_path = os.path.join(build_dir, "run.f")`.
4. Extract model filelist: read the `models.yaml` in the model directory and get the filelist paths; call `_extract(lines, unroll=True, fpath=models_yaml_path)`.
5. Extract testbench filelist if `preprocessed.test.testbench_filelist` is set; call `_extract()` on those lines with `unroll=True`.
6. Merge entries; call `_process(entries, deduplicate=True)`.
7. Write `output_path` with header `"// rtl-buddy generated model filelist\n"` followed by processed lines.
8. Emit `FilelistArtefact(output_path=output_path, lines=processed_lines, run_plan=preprocessed)`.

Key behaviors from `vlog_filelist.py` to preserve:
- `-f` anywhere → `log.critical(...)` (fatal)
- `-F` with `unroll=True` → recurse
- `+libext+` entries consolidate into one
- Missing file/dir → `log.error(...)` (deferred failure, not immediate exception)

---

### `CompileCommandBuild`

```
contract: latest, trigger_ports: [filelist]
inputs:  root: RootContext, filelist: FilelistArtefact
outputs: default → CompileCommand
```

`root` is a state port. `filelist` triggers each invocation. The `PreprocessedRunPlan` is read from `filelist.run_plan`; no third input port is needed.

Implementation steps:

1. `run_plan = filelist.run_plan`.
2. Reconstruct builder config from `root.rtl_builder_cfg` dict to get the compiler executable and compile-time options.
3. `safe_name` and `build_dir` — same computation as `FilelistGenerate`.
4. Build `argv`:
   - `[compiler_exe]`
   - `+ get_compile_time_opts(root.rtl_builder_mode)` from builder config (`rtl.py:L43-L60`)
   - `+ ["--Mdir", build_dir]` if `os.path.basename(compiler_exe)` starts with `"verilator"`
   - `+ [f"+define+{k}" if v is None else f"+define+{k}={v}" for k, v in run_plan.test.plusdefines.items()]`
   - `+ ["-f", filelist.output_path]`
5. Emit `CompileCommand(argv=argv, cwd=root.project_root, test_name=run_plan.test.name, build_dir=build_dir, filelist_path=filelist.output_path, run_plan=run_plan)`.

Compatibility: `vlog_sim.py:L61-L71, L108-L119, L143-L166`.

## Register in `modules/rtl_buddy_compat/config.yaml`

Append to `files`:

```yaml
- file: compile.py
  plugins:
  - name: filelist_generate
    class_name: FilelistGenerate
  - name: compile_command_build
    class_name: CompileCommandBuild
```

## Tests

Write `modules/rtl_buddy_compat/tests/test_compile_command.py`.

**`CompileCommandBuild`** (pure logic — construct a minimal `FilelistArtefact` with a stub `run_plan`):
- Non-Verilator builder → no `--Mdir` in argv
- Builder named `"verilator"` → `--Mdir <build_dir>` present
- `plusdefines={"DEBUG": None}` → `"+define+DEBUG"` in argv
- `plusdefines={"WIDTH": "8"}` → `"+define+WIDTH=8"` in argv
- `"-f run.f"` is the last element
- `run_plan` forwarded to `CompileCommand.run_plan`

**`FilelistGenerate`** (requires `tmp_path` and a minimal project layout):
- Two source lines in a filelist → `run.f` written with header and both lines
- `-f` line → fatal
- `+libext+.sv+.v` consolidated into one `+libext+` entry
- Missing source file → `log.error` (not exception), `run.f` still written
- Emitted `FilelistArtefact.run_plan` is the input `preprocessed`

## Constraints

- `CompileCommandBuild` must read `run_plan` from `filelist.run_plan`; it must NOT have a third input port.
- `FilelistGenerate` must create the build directory if it doesn't exist.
