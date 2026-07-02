# `build-compile-cmd`

**Class:** `BuildCompileCmdMod` (`modules/rtl_buddy/build.py`)

[Back to index](index.md)

Assembles the compiler invocation: the builder executable, its compile-time options for the selected mode, the test's `+define+` plusdefines, and `-f <filelist>`. Detects Verilator (from the exe basename) to add `--Mdir` and derive the `simv` path under an `obj_dir_<test>` build directory.

## Inputs

| Port | Type | Default | Meaning |
|---|---|---|---|
| `test` | `TestConfig` | — | the test |
| `filelist` | `KeyedValue[Path]` | — | filelist from [write-filelist](write-filelist.md) |
| `builder_cfg` | `RtlBuilderConfig` | — | selected builder (exe + options) |
| `logs_dir` | `Path` | — | where compile logs go |
| `work_dir` | `Path` | — | build-directory base |
| `builder_mode` | `str` | `"debug"` | selects the compile-time option set (CLI `--builder-mode`) |

## Outputs

`test` — forwarded; `simv` — `KeyedValue(test.key, simv_path)`; `command` — a `Command` writing to `<test>.compile.log` / `.compile.err`, consumed by [run-process](run-process.md).

## Graph node

`cc-build`, contract `keyed_join` (`key_field: key`, `persistent_inputs: [builder_cfg, builder_mode, logs_dir, work_dir]`).
