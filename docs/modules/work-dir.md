# `work-dir`

**Class:** `WorkDirMod` (`modules/rtl_buddy/setup.py`)

[Back to index](index.md)

Emits the resolved current working directory.

## Inputs

None — source node.

## Outputs

`default` — `Path.cwd().resolve()`.

## Graph node

`work-dir`, contract `default`. Fanned as a persistent input to [ensure-logs-dir](ensure-logs-dir.md), [write-filelist](write-filelist.md), [build-compile-cmd](build-compile-cmd.md), [run-process](run-process.md), [write-randseed](write-randseed.md), and [link-latest](link-latest.md).
