# Spec 14: the `test` graph on the filelist pipeline

**Depends on:** every module spec in this plan — [02](02-filelist-extract.md) (`filelist-extract`), [03](03-filelist-normalise.md) (`filelist-normalise`), [06](06-filelist-dedup.md) (`filelist-dedup`), [07](07-write-filelist.md) (`write-filelist`), [08](08-prioritised-merge.md) (`prioritised-merge`), [09](09-flag-gate.md) (`flag-gate`), [10](10-dirname.md) (`dirname`), [12](12-constant.md) (`constant`), [13](13-filelist-path.md) (`filelist-path`).
**References:** [00-overview](00-overview.md), [`docs/graphs/test.md`](../docs/graphs/test.md), [`docs/graphs/test-dataflow-diagram.md`](../docs/graphs/test-dataflow-diagram.md), [`docs/harness_configs/graph.md`](../docs/harness_configs/graph.md), [`docs/contracts/keyed_join.md`](../docs/contracts/keyed_join.md), [`docs/logger/summary-processor.md`](../docs/logger/summary-processor.md).

## Before you start

Read `docs/graphs/test.md` and `docs/harness_configs/graph.md`. This spec changes **`graphs/test.yaml`, `modules/config.yaml`, `graphs/log/summary.py`, and the `docs/` pages that describe them** — it defines no new module. Every module it wires is delivered by specs 02–13; land those first.

## Goal

Replace the `test` graph's fused `write-filelist` node with the pipeline, and replace `route-list-mode` with a [flag-gate](09-flag-gate.md) instance. **One-to-one parity**: the generated `run.<tag>.f` is byte-identical to what the fused node wrote, the CLI surface is unchanged, and no capability the graph did not already have is added. `filelist-flatten` and `filelist-strip` stay unwired — the `test` graph's flags are `flatten=False, strip=False, deduplicate=True` (`vlog_sim.py:93`), so `dedup` is wired unconditionally and the other two are absent, with no gate anywhere in the pipeline.

## What replaces what

| removed | replaced by |
|---|---|
| `filelist` (fused `write-filelist`, `build.py:115`) | `fl-model-ref`, `fl-model-root`, `fl-model`, `fl-tb`, `fl-merge`, `fl-norm`, `fl-dedup`, `fl-path`, `filelist` |
| `route-list` (`RouteListModeMod`) | `route-list` (`flag-gate` instance) |
| — | `unroll` ([constant](12-constant.md), one per graph) |
| `filelist_resolve_error` as a summary row | non-row ERROR ([spec 02](02-filelist-extract.md)) |

`RouteListModeMod` is **deleted** — from `modules/rtl_buddy/setup.py`, from `modules/config.yaml`, from `modules/tests/test_selection.py`, and its page `docs/modules/route-list-mode.md` is removed with the index entry pointing at it.

## Where each extract resolves against

[Spec 02](02-filelist-extract.md) takes `base_dir` as an input port, so both resolution directories come from the graph:

- **model** → `dirname(model_path)`, where `model_path` is `test.suite_dir / test.model_path`.
- **testbench** → `work_dir`.

Both reproduce the fused node exactly. It rooted model entries on `dirname(abspath(model.get_model_path()))`, and `load-model` stamps `ModelConfig.path` as `str(model_path)` off that same `suite_dir / model_path` join (`setup.py:230,243`), so the two are the same absolute directory; it rooted testbench entries on `dirname(str(work_dir / "tests.yaml"))`, which is `work_dir`.

### Why the model root is re-derived after `gate-pre`

`model-ref` already emits `model_path`, but it sits **upstream of `expand-sweep`**, which mints a new key per variant (`variant.key = f"{test.key}#{i}"`, `setup.py:291`). A root keyed `foo` can never join a source keyed `foo#0`, so `keyed_join` would hold the group forever — for swept tests only. Carrying the root through instead is not available either: `ExpandSweepMod` and `RunPreprocMod` yield only `test` and `model`, so a third payload means editing both (`gate-pre` would forward it — `EarlyStopGateMod` re-emits `**edges`).

So a second `resolve-model-ref` instance sits on the post-sweep `test` edge. It is a pure projection — two attribute reads and a path join wrapped in `KeyedValue`, no I/O, no state, no failure path (`setup.py:227-230`) — so re-running it costs one invocation per variant and yields the identical value: the sweep rewrites only `key` and `model` on a variant, leaving `suite_dir` and `model_path` untouched.

## `route-list` on `flag-gate`

`RouteListModeMod` is a boolean router over a payload it never inspects, which is [`flag-gate`](09-flag-gate.md) exactly. Wiring the generic node deletes the module rather than reimplementing it.

The arms change name on the wire — `on`/`off` instead of `list`/`run` — and the payload port is `value` instead of `suite_cfg`. Nothing downstream cares: `list-test-names` and `select-tests` each read `suite_cfg` and are wired by port name.

The node keeps `contract: unit`. [Spec 09](09-flag-gate.md#the-flag-needs-required-true-and-persistent_inputs) prescribes `default` + `persistent_inputs: [flag]` + `required: true` for the `filelist` command's gates, and none of that applies here: `UnitContract` awaits **every** port unconditionally (`contracts/unit.py:31-33`), so there is no default-versus-payload race to lose and nothing to replay across invocations. This is one suite, routed once — the contract the node already had.

## Nodes

Replacing the `route-list` line and the `filelist` node in `graphs/test.yaml`:

```yaml
# --- list mode vs run ---
- { id: route-list, module: flag-gate,      contract: unit }
- { id: list-names, module: list-test-names, contract: default }
```

```yaml
# --- per-test filelist pipeline ---
- id: unroll
  module: { name: constant, config: { value: true } }
  contract: default
- id: fl-model-ref
  module: resolve-model-ref
  contract: default
- id: fl-model-root
  module: dirname
  contract: { name: keyed_join, config: { key_field: key, unwrap: true } }
- id: fl-model
  module: filelist-extract
  contract: { name: keyed_join, config: { key_field: key, persistent_inputs: [ unroll ], unwrap: true } }
- id: fl-tb
  module: filelist-extract
  contract: { name: keyed_join, config: { key_field: key, persistent_inputs: [ unroll, base_dir ], unwrap: true } }
- id: fl-merge
  module:
    name: prioritised-merge
    config: { priorities: { model_entries: 0, tb_entries: 1 } }
  contract: { name: keyed_join, config: { key_field: key, unwrap: true } }
- id: fl-norm
  module: filelist-normalise
  contract: { name: keyed_join, config: { key_field: key, persistent_inputs: [ base_dir ], unwrap: true } }
- id: fl-dedup
  module: filelist-dedup
  contract: { name: keyed_join, config: { key_field: key, unwrap: true } }
- id: fl-path
  module: filelist-path
  contract: { name: keyed_join, config: { key_field: key, persistent_inputs: [ work_dir ], unwrap: true } }
- id: filelist
  module: write-filelist
  contract: { name: keyed_join, config: { key_field: key, unwrap: true } }
```

### Contract choices

- **`unroll`** — zero-input, so `default` and one invocation ([spec 12](12-constant.md#contract--default-and-why-it-runs-once)), matching `work-dir`/`prepend-path`/`git-status`.
- **`fl-model-ref`** — `default`, as the existing `model-ref` node is. It constructs its own `KeyedValue`s.
- **`fl-model-root`** — one keyed port carrying a `KeyedValue[Path]`, and [`dirname`](10-dirname.md) is generic and must not touch envelopes, so `keyed_join` + `unwrap` does the unwrap and rewrap. This is why it is not `unit` as spec 10 writes it: a contract is a per-node graph choice, and here the node runs once per test.
- **`fl-model`** — two keyed ports, `source` and `base_dir`, which must be matched by key; `unroll` persistent.
- **`fl-tb`** — one keyed port (`source`, the self-keyed `TestConfig`, delivered whole under `unwrap`); `base_dir` and `unroll` are persistent singletons. It still needs `keyed_join` rather than `default` because [spec 02](02-filelist-extract.md) keeps the module envelope-free — the contract is what rewraps `entries` under `test.key`.
- **`fl-merge`** — `keyed_join` is the whole point of the node ([spec 08](08-prioritised-merge.md)). No `contract_port_mappings`: `gate-pre` already runs a `**edges` module without one.
- **`fl-norm`** — `keyed_join` with `unwrap: true` and `persistent_inputs: [base_dir]`, per [spec 03](03-filelist-normalise.md#contract--per-graph-module-is-envelope-agnostic). The module takes and returns a bare `list[entry]`; the contract unwraps/rewraps the `KeyedValue` envelope, same as `fl-dedup`.
- **`fl-dedup`** — `keyed_join` + `unwrap`, because [spec 06](06-filelist-dedup.md)'s module takes and returns a bare list. Spec 03's "a single keyed port needs no join" argument does not carry over: what this node needs from `keyed_join` is the unwrap/rewrap, not the join.
- **`fl-path`** / **`filelist`** — as specified in [13](13-filelist-path.md) and [07](07-write-filelist.md). Each has exactly one output port, so neither needs `ignore`.

## Edges

Replacing the list-mode block, the `work-dir` edge into `filelist`, and the `gate-pre`/`filelist`/`cc-build` main-line edges:

```yaml
# ---- list mode vs run ----
- { src: { cli: list, type: bool, default: false }, dst: { node: route-list, port: flag } }
- { src: { node: parse-suite },           dst: { node: route-list, port: value } }
- { src: { node: route-list, port: on },  dst: { node: list-names, port: suite_cfg } }
- { src: { node: route-list, port: off }, dst: { node: select,     port: suite_cfg } }

# ---- per-test filelist pipeline ----
- { src: { node: unroll },   dst: { node: fl-model, port: unroll, required: true } }
- { src: { node: unroll },   dst: { node: fl-tb,    port: unroll, required: true } }
- { src: { node: work-dir }, dst: { node: fl-tb,    port: base_dir } }
- { src: { node: work-dir }, dst: { node: fl-norm,  port: base_dir } }
- { src: { node: work-dir }, dst: { node: fl-path,  port: work_dir } }

- { src: { node: gate-pre,      port: test },       dst: { node: fl-model-ref,  port: test } }
- { src: { node: fl-model-ref,  port: model_path }, dst: { node: fl-model-root, port: path } }
- { src: { node: fl-model-root },                   dst: { node: fl-model,      port: base_dir } }
- { src: { node: gate-pre,      port: model },      dst: { node: fl-model,      port: source } }
- { src: { node: gate-pre,      port: test },       dst: { node: fl-tb,         port: source } }

- { src: { node: fl-model, port: entries }, dst: { node: fl-merge, port: model_entries } }
- { src: { node: fl-tb,    port: entries }, dst: { node: fl-merge, port: tb_entries } }
- { src: { node: fl-merge, port: entries }, dst: { node: fl-norm,  port: entries } }
- { src: { node: fl-norm,  port: entries }, dst: { node: fl-dedup, port: entries } }
- { src: { node: fl-dedup, port: entries }, dst: { node: filelist, port: entries } }

- { src: { node: gate-pre, port: test },     dst: { node: fl-path,  port: test } }
- { src: { node: fl-path,  port: path },     dst: { node: filelist, port: path } }
- { src: { node: gate-pre, port: test },     dst: { node: filelist, port: test } }
- { src: { node: filelist, port: filelist }, dst: { node: cc-build, port: filelist } }
- { src: { node: gate-pre, port: test },     dst: { node: cc-build, port: test } }
```

The `--list` CLI descriptor is unchanged; only its destination port name moves from `list` to `flag`.

`gate-pre`'s `test` port now fans to five destinations, which the harness allows without restriction — the constraint is on input ports, not outputs (`docs/harness_configs/graph.md`).

`cc-build`'s `test` edge moves from `filelist` to `gate-pre`, as [spec 07](07-write-filelist.md) requires. Sequencing is preserved: `cc-build` joins `test` and `filelist` by key, so a failed write withholds `filelist` and that key never assembles.

### `required: true` on the two `unroll` edges

Both are mandatory, and omitting either is a silent wrong answer rather than an error. `filelist-extract` keeps `unroll:bool = False` ([spec 02](02-filelist-extract.md)), and `KeyedJoinContract` lets a persistent port with a module default fall back to it without blocking (`can_default`, `contracts/keyed_join.py:15`; the same rule as `DefaultContract`'s `is_special`). Without `required: true` the first keyed assembly can therefore fire before the constant is delivered, producing a filelist with `-F` includes unresolved and no diagnostic anywhere. `required: true` clears the fallback and forces the first assembly to await a real value; `persistent_inputs` then replays it for every later test. See [spec 12](12-constant.md#what-the-consumer-must-declare).

`base_dir` on `fl-tb` needs no `required:` — it has no Python default, so a persistent port without a delivered value blocks the first assembly by construction.

## Parity

The pipeline must reproduce the fused node byte-for-byte on the same inputs. The chain of equalities:

| stage | fused node | pipeline |
|---|---|---|
| model root | `dirname(abspath(model.get_model_path()))` (`build.py:125-126`) | `dirname(test.suite_dir / test.model_path)` — the same absolute directory, since `load-model` stamps `ModelConfig.path` from that join |
| tb root | `dirname(str(work_dir / "tests.yaml"))` = `work_dir` (`build.py:127`) | `work_dir` |
| unroll | hard-coded `True` at both call sites | `constant` → `unroll` on both extracts |
| order | model entries then testbench entries (`extend`) | `priorities: { model_entries: 0, tb_entries: 1 }` |
| rebase | `relpath(abs_path, work_dir)` (`build.py:105`) | `fl-norm` with `base_dir = work_dir` |
| flatten / strip | not applied | nodes absent from the graph |
| dedup | `deduplicate=True` (`build.py:128`) | `fl-dedup` wired unconditionally |
| destination | `work_dir / f"run.{test_tag}.f"` (`build.py:117-118`) | `fl-path` ([spec 13](13-filelist-path.md)) |
| output | header + rendered lines | `write-filelist` ([spec 07](07-write-filelist.md)) |

One deliberate difference in *ordering of equivalent operations*: the fused node deduplicated on the rendered line string, the pipeline on the `(path, option)` entry. [Spec 06](06-filelist-dedup.md) establishes these are equivalent because render is deterministic.

`tests/e2e/test_e2e.py` compares the assembled graph against snapshotted `rtl_buddy` output and is the gate for all of the above.

## Summary processor

One change in `graphs/log/summary.py`, and it is a removal: drop `filelist_resolve_error` from `FAIL_EVENTS` and from `DESC_BUILDERS`. It moves from the writer, which held a `TestConfig` to attribute it to, into `filelist-extract`, which holds only a source record ([spec 02](02-filelist-extract.md)), so it can no longer stamp the `key`/`test_name` a row is built from. It stays an ERROR and still trips the run's exit status through `handler.failure`; it simply renders no row.

**No event is added.** The pipeline's other diagnostics are all events the graph already produced and never registered — `filelist_malformed_line` and `filelist_incdir_not_a_dir` and `filelist_file_not_found` were non-row ERRORs in the fused node and remain so — and the four write-error events (`filelist_dir_not_found`, `filelist_is_directory`, `filelist_permission_denied`, `filelist_write_error`) keep their registrations unchanged, because [spec 07](07-write-filelist.md) keeps `test` on the writer for exactly that purpose. `prioritised-merge`'s `unranked_merge_port` is a `log.fatal` config error that aborts before any row exists, so it is not registered either.

The processors' `Config` defaults are the only place `FAIL_EVENTS` is consumed, so the removal needs no change in `graphs/test.yaml`'s `logging:` block.

## Deliverables

- **`graphs/test.yaml`** — the node and edge changes above; delete the `filelist` node's old definition, its `work-dir` edge, and the `filelist → cc-build` `test` edge.
- **`modules/config.yaml`** — remove `{ name: route-list-mode, class_name: RouteListModeMod }`; add `constant`, `dirname` and `logger` to the `funcs.py` block, `flag-gate` to the `rtl_buddy/control.py` block, and the seven pipeline entries ([00-overview](00-overview.md#the-pipeline-at-a-glance)) plus `filelist-path` ([13](13-filelist-path.md)) to the `rtl_buddy/build.py` block.
- **`modules/rtl_buddy/setup.py`** — delete `RouteListModeMod`.
- **`graphs/log/summary.py`** — drop `filelist_resolve_error` from `FAIL_EVENTS` and `DESC_BUILDERS`.
- **Docs.** Delete `docs/modules/route-list-mode.md`. Update `docs/modules/index.md` (the prep section, the pipeline sketch, and the deleted/added entries), `docs/graphs/test.md` (the `--list` destination row, the pipeline sketch, the `keyed_join` paragraph), `docs/graphs/test-dataflow-diagram.md`, and `docs/graphs/index.md:75` (the `run.<test>.f` producer link). Follow `docs/creating-documentation.md` and `docs/modules/doc-structure.md`. Per-module doc pages are each module spec's implementor's responsibility (`docs/contributing.md`), not this spec's.
- **No divergence entry.** Output is byte-identical; [spec 05](05-filelist-strip.md)'s `--strip` divergence belongs to a node this graph does not wire.

## Tests

The module-level tests belong to specs 02–13. This spec's own coverage is the graph:

- **`modules/tests/test_selection.py`** — remove the `RouteListModeMod` cases. Do not re-test `flag-gate` here; [spec 09](09-flag-gate.md) owns it.
- **`graphs/tests/test_summary.py`** — a `filelist_resolve_error` event produces **no** row, while the four write-error events still do.
- **`tests/e2e/test_e2e.py`** — the existing comparison against snapshotted `rtl_buddy` output is the parity gate; it should need no change, and needing one is the signal that parity broke.
- `--list` still prints the test names and nothing else, and the run branch is unaffected — the arm rename is invisible from outside.

## Acceptance criteria

- All four test stages pass (`docs/testing.md`), and coverage stays at its stated level.
- `uv run rtl-comrade test` produces a `run.<tag>.f` byte-identical to the pre-change graph's, for a plain test and for a swept test.
- `--list`, `--test-config`, `--logs-dir`, `--builder`, `--builder-mode`, `--early-stop`, `--rnd-new`, `--rnd-last` and the positional `TEST_NAME` behave exactly as before; no CLI parameter is added or removed.
- The graph loads with no `overloaded_srcs`, `missing_required_inputs`, `incomplete_keys`, or `unknown_persistent_ports` diagnostics.
- A write failure still renders one FAIL row per test; a resolve failure renders none but still exits non-zero.
- `route-list-mode` no longer resolves in the manifest, and no file references it.

## Constraints

- **Parity, not capability.** `filelist-flatten` and `filelist-strip` are not wired, no `flag-gate` appears in the filelist pipeline, and no CLI parameter is added — the flags are known at load time here, so they are expressed by which nodes exist.
- **`unroll` edges carry `required: true`** and both extract contracts list `unroll` in `persistent_inputs`. Neither alone is correct.
- **Both extract roots arrive on edges.** No module in the pipeline derives a resolution root from a record or reads the ambient CWD.
- **`route-list` keeps `contract: unit`.** Do not import spec 09's `default` + `required` + `persistent_inputs` wiring; it solves a problem `unit` does not have.
- **Delete `RouteListModeMod`**, do not reimplement it over `flag-gate`. A wrapper preserving the `list`/`run` port names would keep a module whose only content is a rename.
- The summary processor change is a **removal only** — do not add events, and do not re-register `filelist_resolve_error` under a new name.
