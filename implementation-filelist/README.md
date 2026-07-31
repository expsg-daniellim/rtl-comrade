# Plan: filelist generation as an rtl-comrade node pipeline

This directory is an **implementation plan**, not code. It describes how to rebuild `rtl_buddy`'s compile-filelist generation (`rtl_buddy/src/rtl_buddy/tools/vlog_filelist.py`) as a pipeline of atomic, reusable `rtl-comrade` nodes scheduled by contracts — replacing implementation-test's fused `write-filelist` node ([spec 06b](../implementation-test/specs/06b-write-filelist.md)) so a per-command capability difference becomes which nodes are wired, not a boolean baked into code.

Read in order:

- [00-overview.md](00-overview.md) — goal, why the pipeline exists, the pipeline at a glance, the `filelist` command's head into `filelist-extract`, node map, and ordering/seams. Its Mermaid flowchart renders to `dataflow-diagram.svg`; re-run the repo-root [`regen-dataflow-diagram.sh`](../regen-dataflow-diagram.sh) `implementation-filelist` (uses `mmdc`, falling back to `npx @mermaid-js/mermaid-cli`) after editing the diagram.
- [01-filelist-entry.md](01-filelist-entry.md) — `FilelistEntry`: the entry datatype (`path`, `option`) that replaces the positional tuple; the correlation key rides on the `KeyedValue` envelope, not the entry.
- [02-filelist-extract.md](02-filelist-extract.md) — `FilelistExtractMod`: one source record's filelist (`ModelConfig`, `TestbenchConfig`, or `TestConfig`) → resolved `(path, option)` entries (`-F` unroll, `+libext+` coalesce); one instance per source.
- [08-prioritised-merge.md](08-prioritised-merge.md) — `PrioritisedMergeMod`: the ordered per-source fan-in (model before testbench) on `keyed_join`. *Numbered last, but sits between extract and normalise in the pipeline.*
- [03-filelist-normalise.md](03-filelist-normalise.md) — `FilelistNormaliseMod`: relativise each path against `base_dir` and emit existence warnings.
- [04-filelist-flatten.md](04-filelist-flatten.md) — `FilelistFlattenMod`: optional; `basename` each path.
- [05-filelist-strip.md](05-filelist-strip.md) — `FilelistStripMod`: optional; drop the option token.
- [06-filelist-dedup.md](06-filelist-dedup.md) — `FilelistDedupMod`: drop duplicate entries (always wired in `test`/`randtest`/`regression`).
- [07-write-filelist.md](07-write-filelist.md) — `WriteFilelistMod`: render entries → `.f`, write, and log write failures.
- [09-flag-gate.md](09-flag-gate.md) — `FlagGateMod`: route a value to one of two ports on a boolean, so a runtime flag can bypass an optional transform. Graph-control, not filelist-specific; registered under `control.py`, not with the seven.
- [10-dirname.md](10-dirname.md) — `DirnameMod`: the directory component of a path, supplying `filelist-normalise`'s `base_dir` from the CLI `output_path`. Generic, not filelist-specific; registered under `funcs.py`, not with the seven.
- [11-logger.md](11-logger.md) — `LoggerMod`: log one structured event per value received, projecting the event's fields off the value by config. A terminal sink with no outputs. Generic, not filelist-specific; registered under `funcs.py`, not with the seven.
- [12-constant.md](12-constant.md) — `ConstantMod`: emit one configured value, once, so a port whose value is fixed at graph-writing time is fed the same way a CLI-supplied one is. Generic, not filelist-specific; registered under `funcs.py`, not with the seven.
- [13-filelist-path.md](13-filelist-path.md) — `FilelistPathMod`: the per-test destination `work_dir / run.<tag>.f`, which [07](07-write-filelist.md) removed from the writer and no other node produces.
- [14-test-update.md](14-test-update.md) — wiring the `test` graph onto the pipeline: the node and edge changes to `graphs/test.yaml`, `route-list-mode` replaced by a [flag-gate](09-flag-gate.md) instance, the byte-for-byte parity argument, the one summary-processor removal, and the amendments specs [10](10-dirname.md) and [00](00-overview.md) need first. Defines no module.
- [15-dirjoin.md](15-dirjoin.md) — `DirjoinMod`: join a directory `Path` with a name string to produce a resolved `Path`. Generic, not filelist-specific; registered under `funcs.py`, not with the seven.
- [16-filelist-graph.md](16-filelist-graph.md) — the `filelist` command's graph YAML, manifest entries, and `rtl_comrade_config.yaml` registration. Assembles the pipeline diagram from [00-overview](00-overview.md) into `graphs/filelist.yaml` — unkeyed, single-source, three flag-gated transforms, one logger sink. Defines no module.

The framework this plan targets is documented under `docs/` (modules, contracts, harness, configs). The manifest registering all seven pipeline modules with `modules/config.yaml` lives in [spec 02 Deliverables](02-filelist-extract.md#deliverables); each node's spec points there.
