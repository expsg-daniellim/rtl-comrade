# `write-filelist`

**Class:** `WriteFilelistMod` (`modules/rtl_buddy/build.py`)

[Back to index](index.md)

Builds the compile filelist for the test: extracts entries from the model's filelist and the testbench's filelist (unrolling `-F` includes, honouring `+incdir+`/`+libext+`/`-v`/`-y`/`-f` options), rewrites paths relative to the working directory, deduplicates, and writes `run.<test>.f`. Emits the path of the written filelist.

## Inputs

| Port | Type | Meaning |
|---|---|---|
| `test` | `TestConfig` | the test (supplies the testbench filelist) |
| `model` | `ModelConfig` | resolved model (supplies the model filelist) |
| `work_dir` | `Path` | run working directory (output location + relpath base) |

## Outputs

`test` — forwarded; `filelist` — the `Path` of the written file. A failed write emits nothing.

## Failure routing

A lower-case `-f` include is a hard `log.fatal` (`filelist_lower_f_not_allowed`); a malformed line, a missing include file, or a `+incdir+` target that isn't a directory is `log.error` (best-effort, run continues); directory-missing / is-a-directory / permission / resolve / write errors are caught and logged at `ERROR`.

## Filelist helpers

`filelist_extract(lines, unroll, fpath)` and `filelist_process(entries, work_dir, deduplicate)` are module-level functions (not nodes) mirroring upstream `rtl_buddy`'s filelist handling. `FILELIST_OPTION_RE` parses each line into an optional option prefix (`-v`/`-y`/`-f`/`-F`/`+incdir+`/`+libext+`) and a path; `-F` includes are recursively unrolled and `+libext+` values are coalesced into a single trailing entry.

## Graph node

`filelist`, contract `keyed_join` (`key_field: key`, `persistent_inputs: [work_dir]`, `unwrap: true`, `ignore: [test]`). The `model` and `filelist` edges ride the wire as `KeyedValue`s; the contract unwraps `model` on the way in and keys the emitted `filelist` path on the way out, so the module never handles the key.
