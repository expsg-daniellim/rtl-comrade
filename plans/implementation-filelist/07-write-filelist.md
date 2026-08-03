# Spec 07: write-filelist (`WriteFilelistMod`)

**Depends on:** [spec 06](06-filelist-dedup.md) / [spec 03](03-filelist-normalise.md) (`entries` input — whichever transform is last in the wired chain), [04f](../implementation-test/specs/04f-work-dir.md) (`work_dir` provider).
**References:** [implementation-test spec 06b](../implementation-test/specs/06b-write-filelist.md) — the fused node this pipeline replaces; its per-tag naming, `work_dir` rooting, and write-error handling land here.

## Before you start

Read `docs/module-implementation/implementation.md`. This keeps the `WriteFilelistMod` name from 06b but is now **render + write** only — read/unroll and every path rewrite moved to specs [02](02-filelist-extract.md)–[06](06-filelist-dedup.md).

## Goal

Terminal node: render the final `(path, option)` entries into `.f` line strings with the `rtl-buddy` header, write them to a destination path, and log write failures. Render is folded in here (not a separate node) because stringifying an entry is trivial and invariant — no command varies it and nothing consumes the rendered lines before the write ([00-overview](00-overview.md#ordering-and-seams)).

## Surface

```
contract:          keyed_join   (test graph: joins entries + path by key; test read for log context)
inputs:            entries:list[FilelistEntry], path:Path, test:TestConfig|None = None
outputs:           filelist → Path (the written .f; the contract rewraps it as KeyedValue)
```

The contract is a per-graph choice — `keyed_join` with `unwrap: true` in the `test` graph (spec [14](14-test-update.md)), `default` in the `filelist` graph (spec [16](16-filelist-graph.md)). The module is envelope-agnostic: it takes and returns bare values in both cases.

**`test` is consumed, not forwarded.** The writer reads `test.key`/`test.get_name()` for its failure logs and emits nothing back: re-yielding the record it was handed is a passthrough the graph can do itself, so `cc-build` takes its `test` edge straight from `gate-pre` rather than from the writer. Sequencing survives the change — `cc-build` joins `test` and `filelist` by key, so a failed write withholds `filelist` and that key never assembles, exactly as before. This is the same removal `ResolveModelRefMod` made upstream ([docs/modules/resolve-model-ref.md](../docs/modules/resolve-model-ref.md): "The input `test` is not re-emitted; the graph wires it directly from upstream").

`path` is the **fully-resolved destination**, computed by the graph, not this node — keeping the writer reusable:
- `test`/`randtest`/`regression`: `Path(work_dir) / f"run.{test_tag}.f"` (`test_tag = re.sub(r"[^A-Za-z0-9_.-]", "_", test.get_name())`, the regex `build-compile-cmd` uses), per-tag so concurrent tests don't collide on a shared `run.f`.
- `filelist` command: the CLI `output_path` (default `run.f`).

The `filelist` command has no `test` at all, so it leaves the port unwired and the write-error events lose their `key`/`test_name` there — which costs nothing, because that graph declares no summary processors ([spec 16](16-filelist-graph.md)). Give `test` a `None` default so the writer loads in both graphs, and guard the log fields off it.

```python
class WriteFilelistMod:
    def run(self, entries:list[FilelistEntry], path:Path, test:TestConfig|None = None):
        key = test.key if test is not None else None
        test_name = test.get_name() if test is not None else None
        lines = [ f"+libext+{e.path}\n" if e.option == "+libext+" else (f"{e.option}{e.path}\n" if e.option else f"{e.path}\n")
                  for e in entries ]
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("// rtl-buddy generated model filelist\n")
                f.writelines(lines)
            yield ("filelist", path)
        except FileNotFoundError:
            log.error("filelist_dir_not_found", key=key, test_name=test_name, path=str(path))
        except IsADirectoryError:
            log.error("filelist_is_directory", key=key, test_name=test_name, path=str(path))
        except PermissionError as e:
            log.error("filelist_permission_denied", key=key, test_name=test_name, path=str(path), err=e.strerror)
        except OSError as e:
            log.error("filelist_write_error", key=key, test_name=test_name, path=str(path), err=e.strerror, errno=e.errno)
```

## Algorithm

1. **Render** each entry to a line: `+libext+` → `f"+libext+{e.path}\n"`; else `f"{e.option}{e.path}\n"` if `e.option` else `f"{e.path}\n"`. (Matches `_process`'s line-build, `vlog_filelist.py:123`, and its `+libext+` guard, `:116`.)
2. Open `path`; write the header `// rtl-buddy generated model filelist\n` then `writelines(lines)` (`vlog_filelist.py:155-158`).
3. On success emit `("filelist", path)` — the contract rewraps the path as `KeyedValue(test.key, path)`, and `build-compile-cmd` consumes it alongside the `test` edge it takes from `gate-pre`.
4. **Failure — write error, one `except` per class** (the write half of 06b's handler; the resolve half is extract's, spec [02](02-filelist-extract.md)): `FileNotFoundError`→`filelist_dir_not_found`, `IsADirectoryError`→`filelist_is_directory`, `PermissionError`→`filelist_permission_denied` (`err=e.strerror`), `OSError`→`filelist_write_error` (`err`/`errno`; **last** — the others subclass it). Each logs its event at ERROR with the attempted `path` plus the `key`/`test_name` a summary row is stamped from, and **emits nothing** — the handler's `failure` flag carries the verdict. Per-test FAIL, not abort. No `except Exception` catch-all.

No `KeyError`/`AttributeError` case — resolve errors are raised and routed in `filelist-extract`, never in the writer. No relpath/flatten/dedup — those are done by the time entries arrive.

## Deliverables

In `modules/rtl_buddy/build.py`, `WriteFilelistMod` reduced to render + write:

- `WriteFilelistMod` — `(entries:list[FilelistEntry], path:Path, test:TestConfig|None = None)`, `keyed_join` over `entries` + `path` (keyed by test, `unwrap: true`, no `ignore`), `test` read for log context only. Emits `("filelist", path)`; a write error logs and emits nothing. Drops the `model`/`work_dir`/`test_filelist` inputs and the inlined `filelist_extract`/`filelist_process` calls (moved to specs 02–06); folds in the line-render loop. Drops the `KeyError`/`AttributeError` handler with them — resolve errors are extract's now (spec [02](02-filelist-extract.md)) — and drops the `test` passthrough yield.
- **Graph rewiring** — in `graphs/test.yaml`, repoint `cc-build`'s `test` edge from `filelist` to `gate-pre`, the writer's own source for it.
- **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_filelist.py:116,123,155-158` — the render + header + write of `_process`/`write_output`; called from `VlogSim._write_filelist` (`tools/vlog_sim.py:88-93`).

Manifest `{ name: write-filelist, class_name: WriteFilelistMod }` (with the pipeline — [spec 02 Deliverables](02-filelist-extract.md#deliverables)). The four write-error events keep their `FAIL_EVENTS`/`DESC_BUILDERS` registrations in `graphs/log/summary.py` unchanged.

## Tests

In `modules/tests/test_prep.py`. The existing fused-node `WriteFilelistMod` tests are removed — the fused behaviour (extract, process, write) is replaced by the pipeline, and the new tests cover the render-and-write surface only.

- Entries (incl. a `+libext+`) + `path=tmp_path/"run.foo.f"` + `test` → writes header then rendered lines (`+libext+` rendered verbatim, options preserved); yields `("filelist", path)` and nothing else — in particular no `test`; round-trip read matches. The module is driven with bare values throughout, as the contract delivers them.
- End-to-end parity: `filelist-extract` ×2 → `filelist-normalise(base_dir=tmp_path)` → `filelist-dedup` → `write-filelist` reproduces the byte-for-byte `.f` the fused 06b `WriteFilelistMod` wrote on the same model+testbench inputs. Chaining the modules directly bypasses the contracts, so the test stands in for them at the `keyed_join` boundaries: hand the writer the bare entry list the contract would have unwrapped.
- `path` into a read-only dir → `PermissionError` → `filelist_permission_denied`, no results, `logging_handler.failure` set.
- `path` with missing parent → `FileNotFoundError` → `filelist_dir_not_found`, same.
- `path` that is a directory → `IsADirectoryError` → `filelist_is_directory`, same.
- `test` omitted (the `filelist` command) → `("filelist", path)` still fires on success, and a write error logs with `key`/`test_name` `None`.

## Acceptance criteria

- Tests pass.
- On success: header + rendered lines at `path` (verbatim — the writer neither computes the name nor rewrites paths); `filelist` is the only port that fires.
- Each write-error class logs its own event and emits nothing; no catch-all.
- The full pipeline reproduces 06b's byte-for-byte `.f` on the `test`-graph wiring.
- `write-filelist` → `WriteFilelistMod` resolves in the manifest.

## Constraints

- **Render + write only** — no path computation, no relpath/flatten/strip/dedup. `path` arrives resolved; entries arrive fully transformed.
- **One `except` per write-error class**, `OSError` last. Each logs its event with the attempted `path` and emits nothing. Per-test FAIL, not abort.
- **`filelist` is the only output port** — `test` is read for log context and never re-emitted; the graph carries it to `cc-build` itself.
- **The module never touches the key** beyond reading `test.key` off the `TestConfig` for the logs. `unwrap: true` goes on the `contract` plugin's `config`, the single slot it works from; with one output port there is nothing to `ignore`.
- Render `+libext+` verbatim (`+libext+{value}`), no prefix duplication.
- Reimplement natively; never import rtl_buddy's `VlogFilelist`.
