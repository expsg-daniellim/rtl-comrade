# Spec 02: filelist-extract (`FilelistExtractMod`)

**Depends on:** [01c](../implementation-test/specs/01c-model-schema.md) (`ModelConfig`) and [01b](../implementation-test/specs/01b-suite-schema.md) (`TestConfig`, `TestbenchConfig`) — the source records this node reads its lines off; [spec 01 — FilelistEntry](01-filelist-entry.md) (the entry datatype it produces).
**References:** [00-overview](00-overview.md) — the pipeline rationale, node map, and ordering; [implementation-test spec 06b](../implementation-test/specs/06b-write-filelist.md) — the fused `WriteFilelistMod` this pipeline replaces.

## Before you start

Read `docs/module-implementation/implementation.md` (input-port inference, output forms, `finalise()`). This module natively reimplements rtl_buddy's `VlogFilelist._extract` — **do not import or construct rtl_buddy's `VlogFilelist`** (`modules/rtl_buddy/` is deliberately distinct from the upstream `rtl_buddy/src/...` tree, cited only as a compatibility source).

## Goal

Turn **one** filelist source (the record whose `filelist` field holds the lines — a `ModelConfig` from `models.yaml`, a `TestbenchConfig`/`TestConfig` from `tests.yaml`) into ordered `(path, option)` entries: parse each line's option prefix, resolve paths against the `base_dir` the graph supplies, recursively unroll `-F` includes, and coalesce `+libext+` tokens. **No** relativize, existence check, flatten, strip, or dedup — every one of those is a downstream node.

## Surface

```
contract:          default   (one instance per source; keyed by test in the test graph)
inputs:            source:ModelConfig|TestbenchConfig|TestConfig, base_dir:Path, unroll:bool = False
outputs:           entries → list[FilelistEntry]   (self-keyed in the test graph)
```

`entries` is the only output port. An unresolvable `-F` include is logged at ERROR and skipped — there is no `fail` port.

`source` is the config record the graph already carries on the `model` / `test` edges, not a pre-extracted `list[str]`: the node reads the lines off it with `get_filelist()`, reaching a `TestConfig`'s testbench through `get_testbench()` first. That is what lets the upstream chain feed this node directly — nothing in the graph produces a bare `list[str]`. Exactly one field is read off the record; the resolution directory is not derived from it.

`base_dir` is that directory, and it is the graph's to decide. A `filelist` is a field inline in a config file, not a file of its own, so a record-derived root would always be the holding file's directory — which is right for a `ModelConfig` and wrong for a testbench, where both the fused node (`build.py:123`) and rtl_buddy (`vlog_filelist.py:147-151`) root entries on the working directory instead. One rule cannot serve both sources, so each instance is wired its own. That also matches [04f](../implementation-test/specs/04f-work-dir.md): location is decided once and travels as data, so relocating it is a rewiring rather than module surgery. The per-graph roots are in [spec 14](14-test-update.md) and [00-overview](00-overview.md); `-F` includes are the one root this node still derives, from the include's own path (step 3 below).

Each graph instantiates one `filelist-extract` per source; the `prioritised-merge` node (spec [08](08-prioritised-merge.md), on `keyed_join`) merges the per-source `entries` streams into `filelist-normalise`.

`unroll` defaults to `False`, matching both places rtl_buddy declares a default — the `--unroll/-u` option (`rtl_buddy.py:444`) and `write_output` (`vlog_filelist.py:137`). `VlogSim` is the one caller that unrolls, passing `unroll=True` explicitly (`vlog_sim.py:93`), so the `test`/`randtest`/`regression` graphs wire that value on the edge rather than inheriting it.

```python
class FilelistExtractMod:
    def run(self, source:ModelConfig|TestbenchConfig|TestConfig, base_dir:Path, unroll:bool = False):
        config = source.get_testbench() if isinstance(source, TestConfig) else source
        lines = config.get_filelist()
        entries = []
        libexts = {}
        # ... algorithm steps 1-4 inlined here (see Algorithm below)
        yield ("entries", entries)
```

`base_dir` carries **no Python default**: every graph wires it, and a default would let a keyed contract fall back to it rather than await the real value ([spec 12](12-constant.md#what-the-consumer-must-declare)).

## Algorithm

Resolve `config` — `get_testbench()` first when `source` is a `TestConfig` — then read its `get_filelist()`, and port `VlogFilelist._extract` (`vlog_filelist.py:26-105`):

1. `prefix_parent = base_dir`. Iterate lines; `strip()`; skip blank and comment lines (`//`, `/*`, `*`).
2. Match each line with the option regex (`FILELIST_OPTION_RE`, `build.py:55`) into `(option, path)`: `+incdir+`/`+libext+` → token; `-v`/`-y`/`-F`/`-f` → flag + trailing space; else `None`. Malformed line → `log.error("filelist_malformed_line", line=line)` and skip (best-effort).
3. `line_path = os.path.expandvars(line_path)`, then branch:
   - `-f ` (lower-case) → `log.fatal("filelist_lower_f_not_allowed", line=line)` (hard stop).
   - `-F ` **and** `unroll` → `path_next = os.path.join(prefix_parent, line_path)`; open and recurse with `base_dir = os.path.dirname(path_next)`, extending `entries`. An include **is** a file, so it roots on its own directory — this is the one root the node derives, and it is unaffected by the wired top-level `base_dir`. Open failure → step 5.
   - `+libext+` → `libexts.update(dict.fromkeys(line_path.split('+')))` (accumulate, insertion-ordered).
   - else (source files, `-v`, `-y`, `+incdir+`, non-unrolled `-F`) → `entries.append(FilelistEntry(os.path.join(prefix_parent, line_path), option))`.
4. After the loop, if any `+libext+` accumulated, append one coalesced `FilelistEntry("+".join(libexts), "+libext+")`. `libexts` is a `dict` (used as an ordered set via `dict.fromkeys`), so the join is deterministic.
5. **Failure — unresolvable `-F` include.** rtl_buddy `log.error`s and continues (`vlog_filelist.py:91-92`); rtl_comrade's `filelist_extract` raises `KeyError` on the `OSError` (`build.py:84-85`) for the fused node to catch as `filelist_resolve_error`. Catch the include-open `OSError` here instead — `log.error("filelist_resolve_error", path=str(path_next), err=str(e))` — and skip that include, continuing the remaining lines. The event carries no `key`/`test_name`: this node holds a source record, not a test, so the error is a non-row ERROR and is **removed** from `FAIL_EVENTS`/`DESC_BUILDERS` in `graphs/log/summary.py`, joining `filelist_malformed_line` and `filelist_file_not_found`. It still trips the run's exit status via `handler.failure`.

Entries carry **non-relativized, non-flattened, non-deduped** paths, absolute whenever `base_dir` is — which every wiring makes it — because [normalise](03-filelist-normalise.md) rebases against a `base_dir` in a different directory and checks existence on what arrives. Every rewrite after that is a downstream node's function.

## Deliverables

In `modules/rtl_buddy/build.py`, replacing the extract portion of the fused `WriteFilelistMod`:

- `FilelistExtractMod` — `(source:ModelConfig | TestbenchConfig | TestConfig, base_dir:Path, unroll:bool = False)` → `("entries", list[FilelistEntry])`, the single output port. Reuse the existing `FILELIST_OPTION_RE` and `-F`/`+libext+` recursion from `filelist_extract`; lift them into this node rather than keeping the free function as a parallel path. The `model.get_filelist()` / `test.get_testbench().get_filelist()` calls the fused node made at its call site (`build.py:122-123`) move inside the module, one branch each, while the two `source_dir` values it computed there (`build.py:120-121`, `123`) move outward onto the `base_dir` edges — the graph keeps the per-source distinction the fused node hard-coded.
- **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_filelist.py:26-105` — `VlogFilelist._extract`.

**Manifest** — `{ name: filelist-extract, class_name: FilelistExtractMod }` in the `- file: rtl_buddy/build.py` block of `modules/config.yaml`. The full seven-entry listing is in [00-overview](00-overview.md#the-pipeline-at-a-glance).

**Summary registration** — in `graphs/log/summary.py`, drop `filelist_resolve_error` from `FAIL_EVENTS` and `DESC_BUILDERS`. It moves from the writer (which had a `test` to attribute it to) into this node (which does not), so it stops being a summary row; the four write-error events stay ([spec 07](07-write-filelist.md)).

## Tests

In `modules/tests/test_prep.py`:

- A `ModelConfig` whose `filelist` holds `-v`, source files, `+incdir+`, two `+libext+` lines → `entries` preserves order, prepends `base_dir`, appends exactly one coalesced `+libext+`. **No `relpath`, no `basename`, no dedup** applied — those boundaries move to specs 03–06.
- One record driven twice with two different `base_dir` values → entries rooted on each, showing the root comes from the port and nothing else.
- A record whose own `path` differs from `base_dir`, driven under `monkeypatch.chdir(other)` → entries are rooted on `base_dir`, neither on the record's directory nor on the process CWD.
- The same lines reached through each accepted record — a `ModelConfig`, a `TestbenchConfig`, and a `TestConfig` bound to that testbench — produce identical `entries` for the same `base_dir` (the `get_testbench()` hop is the only difference).
- `-F other.f`, `unroll=True`, committed `other.f` under `base_dir` → included entries spliced in order, rooted on `other.f`'s directory rather than on `base_dir` (an include is a file, not a field).
- `-F other.f`, `unroll=False` → single `-F` entry, not recursed.
- Missing `-F` include → `log.error("filelist_resolve_error", …)`, the remaining lines still extracted, no abort and no `fail` port.
- Lower-case `-f other.f` → `log.fatal("filelist_lower_f_not_allowed", …)`.
- Malformed line → `log.error("filelist_malformed_line", …)`, skipped.

## Acceptance criteria

- Tests pass.
- `entries` holds paths rooted on `base_dir`, with no relpath/flatten/dedup applied.
- On the same source and the root the reference used for it, `entries` matches rtl_buddy's `_extract` (order + `+libext+` coalescing) — for a testbench that root is the working directory, not `tests.yaml`'s.
- `filelist-extract` → `FilelistExtractMod` resolves in the manifest.

## Constraints

- **Resolution only.** No `os.path.relpath`, no `basename`, no existence check, no dedup — every rewrite is a downstream node (specs 03–06). Output is intentionally un-rewritten so any pipeline can consume it.
- **The record, not its lines.** `source` is a `ModelConfig`, `TestbenchConfig`, or `TestConfig`; the getter hop lives in this module. Exactly one field is read off it — the filelist — and nothing else about the source leaks in.
- **`base_dir` is wired, never derived from the source.** No `get_model_path()`, no `os.getcwd()`. A record-derived root would be the holding file's directory for every source, which is not what either reference does for a testbench. The `-F` recursion is the sole exception, and it roots on the include file's own path.
- One instance **per source** — do not accept a list and loop internally; the multi-source fan-in is `prioritised-merge` (spec [08](08-prioritised-merge.md)), not this node. That is what makes the model+testbench merge and the single-source `filelist` command the same node used differently.
- **`entries` is the only output port.** A resolve error is logged at ERROR and the include skipped — no `fail` port, no abort.
- Reimplement natively; never import rtl_buddy's `VlogFilelist`.
