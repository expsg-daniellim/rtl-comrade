# Spec 06: Per-test prep modules

**Depends on:** spec 01 (schema).
**References:** [03 — Per-test preparation section](../03-module-catalog.md).

## Goal

Implement the per-test preprocessing hook and filelist generator that sit between sweep
expansion and compile.

## Deliverables

In `modules/rtl_test/build.py` (continuing from spec 03):

- `RunPreprocMod` — `(ctx, root_cfg)` → if `test.preproc_path` set, `exec`s the script
  with `{logger, test_cfg, root_cfg}` (mutating `test`); emits `ctx`. Reuses the
  `exec_hook` helper from spec 05.
- `WriteFilelistMod` — `(ctx)` → reimplements `VlogFilelist.write_output(unroll=True,
  flatten=False, strip=False, deduplicate=True, test_filelist=test.tb.get_filelist())`;
  writes the filelist file; emits two named outputs:
  - `("ctx", ctx)` (passthrough)
  - `("filelist", {"key": ctx["key"], "filelist": <Path>})` (consumed in lockstep by
    `build-compile-cmd` in spec 07).

Manifest entries per [06](../06-graph-yaml.md).

Tests in `modules/tests/test_prep.py`:
- `run-preproc` no-op when no script.
- `run-preproc` mutates `test.pa`/`test.pd`/`test.timeout` when script sets them.
- `write-filelist` produces a syntactically valid `.f` file from a real `models.yaml` +
  testbench filelist; round-trip parse matches expected entries; `+incdir+` consolidation
  works.

## Acceptance criteria

- Tests pass.
- The filelist module reproduces the byte-for-byte output of rtl_buddy's `VlogFilelist`
  on the same inputs (modulo ordering if dedup is non-stable).

## Notes

`write-filelist` is one of the few modules reimplementing nontrivial rtl_buddy logic
(`VlogFilelist`). Port it carefully — the option-parsing regex, `-F` recursion with
unroll, `+incdir+`/`+libext+` handling, dedup, and the existence checks are all
behaviour worth replicating. See `rtl_buddy/src/rtl_buddy/tools/vlog_filelist.py` for
the reference.

Filename caveat from [07 settled 13 / KIV 17]: rtl_buddy writes a single `run.f` in CWD
per compile; concurrent compiles collide. The upstream rtl_buddy change (per-invocation
subdirs) will resolve this. Until then, `write-filelist` writes `run.f` literally.
