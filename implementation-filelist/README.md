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

## Priority order

| # | Spec | Depends on | Notes |
|---|---|---|---|
| 01 | [filelist-entry](01-filelist-entry.md) | impl-test 01 | `FilelistEntry` datatype. No module. |
| 09 | [flag-gate](09-flag-gate.md) | — | Generic graph-control; payload-agnostic. |
| 10 | [dirname](10-dirname.md) | — | Generic; domain-agnostic. |
| 11 | [logger](11-logger.md) | — | Generic; payload-agnostic. |
| 12 | [constant](12-constant.md) | — | Generic; payload-agnostic. |
| 15 | [dirjoin](15-dirjoin.md) | — | Generic; domain-agnostic. |
| 02 | [filelist-extract](02-filelist-extract.md) | 01, impl-test 01b/01c | One instance per source; owns the manifest block for all seven pipeline modules. |
| 08 | [prioritised-merge](08-prioritised-merge.md) | 02 | `keyed_join` fan-in; sits between extract and normalise. |
| 13 | [filelist-path](13-filelist-path.md) | impl-test 01b, 04f | Per-test `.f` destination path; `test` graph only. |
| 03 | [filelist-normalise](03-filelist-normalise.md) | 02, 08 | Relativise + existence checks. |
| 04 | [filelist-flatten](04-filelist-flatten.md) | 03 | Optional transform; `basename`. |
| 05 | [filelist-strip](05-filelist-strip.md) | 03 | Optional transform; drop option token. |
| 06 | [filelist-dedup](06-filelist-dedup.md) | 03 | Drop duplicate entries. |
| 07 | [write-filelist](07-write-filelist.md) | 03, 06, impl-test 04f | Render + write `.f`; terminal node. |
| 14 | [test-update](14-test-update.md) | 02, 03, 06, 07, 08, 09, 10, 12, 13 | Wires the `test` graph onto the pipeline. No module. |
| 16 | [filelist-graph](16-filelist-graph.md) | 02–07, 09–11, 15, impl-test 04f/05e | `graphs/filelist.yaml`, manifest, command registration. No module. |

Specs 01, 09, 10, 11, 12, 15 have no internal dependencies and can run in parallel from the start. Spec 02 requires 01 (and impl-test 01b/01c). Specs 04, 05, 06 can run in parallel after 03. Specs 13 and 08 can run in parallel with each other and with 03 once their deps are met. Specs 14 and 16 are integration — all module specs must land first.

The framework this plan targets is documented under `docs/` (modules, contracts, harness, configs). The manifest registering all seven pipeline modules with `modules/config.yaml` lives in [00-overview](00-overview.md#the-pipeline-at-a-glance); individual specs reference it rather than duplicating it.
