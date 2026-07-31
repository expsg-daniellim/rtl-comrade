# Spec 16: Graph YAML, manifest, and command registration

**Depends on:** specs [02](02-filelist-extract.md)–[07](07-write-filelist.md), [09](09-flag-gate.md)–[11](11-logger.md) (the modules the `filelist` graph wires); [15](15-dirjoin.md) (`dirjoin`); [implementation-test spec 05e](../implementation-test/specs/05e-load-model.md) (`load-model`); [implementation-test spec 04f](../implementation-test/specs/04f-work-dir.md) (`work-dir`).
**References:** [00-overview](00-overview.md) — pipeline diagram, head, ordering; [09 — Wiring](09-flag-gate.md#wiring--the-filelist-graph) — the gate-chain edges (verbatim, except the `strip` → `strip_options` CLI rename below).

## Before you start

Read `docs/harness_configs/graph.md` (nodes, edges, CLI edge sources, `required`, multi-destination output fan-out, and the constraint that a reused `cli` name must carry an identical descriptor at every occurrence), `docs/harness_configs/plugin_manifest.md` (`config.yaml` shape), `docs/harness_configs/rtl_comrade_config.md` (registering subcommands), `docs/harness/validation.md` (cycle, overloaded-input, and persistent-port checks the acceptance criteria rely on), and `docs/harness/branch_labels.md` (how the three-gate chain's arms validate as mutually-exclusive sources on a single input port). This spec is the sole owner of `graphs/filelist.yaml` and the `filelist` entry in `rtl_comrade_config.yaml` — no sibling spec appends to those files.

## Goal

Assemble the `filelist` graph YAML, carry the manifest entries from this plan's module specs, and register the `filelist` subcommand in `rtl_comrade_config.yaml`.

## Deliverables

- **`graphs/filelist.yaml`** — per the pipeline diagram in [00-overview](00-overview.md#the-pipeline-at-a-glance): `work-dir` provides CWD; `config-path` (a `dirjoin` instance) resolves the CLI `model_config` filename against CWD, producing an absolute `Path` that fans to `load-model.model_path` and `model-dir.path`; `load-model` resolves the model; `model-dir` and `output-dir` (two [dirname](10-dirname.md) instances) produce the `base_dir` ports; `filelist-extract` turns the model's filelist into entries resolved from `model-dir`; `filelist-normalise` relativises entries against `output-dir`; three [flag-gate](09-flag-gate.md) instances (`gate-flatten`/`gate-strip`/`gate-dedup`) route entries through or past `filelist-flatten`/`filelist-strip`/`filelist-dedup` according to the `--flatten`/`--strip`/`--deduplicate` CLI options; `write-filelist` renders and writes the `.f`; and `log-filelist` (a [logger](11-logger.md) instance) reports the written path at `info`. CLI edges: `model_name` (positional, required) and `output_path` (positional, default `"run.f"`) supply `load-model` and the two dirname instances; `model_config` (option, default `"models.yaml"`) feeds `config-path.name`, which resolves it against CWD and fans the resulting `Path` to `load-model` and `model-dir`; `unroll` (option, bool, default `false`) feeds `extract.unroll`; and the three gate flags `flatten`/`strip_options`/`deduplicate` (options, bool, default `false`) each feed a gate's `flag` port with `required: true`. Every node fires once (all inputs are singletons). There is **no** `logging` block, **no** keying (`KeyedValue` envelopes do not appear — entries travel as a bare `list[entry]` throughout), **no** `prioritised-merge` (single source), **no** `constant` (CLI supplies `unroll`), and **no** `filelist-path` (CLI supplies `output_path`).
  ```yaml
  modules:
  - "../modules"
  contracts:
  - "../contracts"

  nodes:
  # --- head: CWD resolution, model loading, directory extraction ---
  - { id: work-dir,    module: work-dir, contract: default }    # zero-input CWD provider
  - { id: config-path, module: dirjoin,  contract: unit }       # resolves model_config against CWD
  - { id: load-model,  module: load-model, contract: default }  # model_name + model_path; test unwired (None default)
  - { id: model-dir,   module: dirname,    contract: unit }     # dirname(config-path) → extract.base_dir
  - { id: output-dir,  module: dirname,    contract: unit }     # dirname(output_path) → normalise.base_dir

  # --- pipeline ---
  - { id: extract, module: filelist-extract, contract: default }   # model filelist → resolved entries
  - id: normalise
    module: filelist-normalise
    contract:
      name: default
      config:
        persistent_inputs: [ base_dir ]

  # --- flag-gated transforms (spec 09 wiring, verbatim except the strip_options CLI rename) ---
  - id: gate-flatten
    module: flag-gate
    contract:
      name: default
      config:
        persistent_inputs: [ flag ]
  - { id: flatten, module: filelist-flatten, contract: default }
  - id: gate-strip
    module: flag-gate
    contract:
      name: default
      config:
        persistent_inputs: [ flag ]
  - { id: strip, module: filelist-strip, contract: default }
  - id: gate-dedup
    module: flag-gate
    contract:
      name: default
      config:
        persistent_inputs: [ flag ]
  - { id: dedup, module: filelist-dedup, contract: default }

  # --- write + report ---
  - { id: write, module: write-filelist, contract: default }   # entries + path from CLI; test unwired (None default)
  - id: log-filelist
    module:
      name: logger
      config:
        level: info
        event: filelist_written
        mapping: path
    contract: default

  edges:
  # ---- CLI edges ----
  # Positional arguments — declaration order sets CLI position.
  - src: { cli: model_name, option: false, type: str }
    dst: { node: load-model, port: model_name }
  - src: { cli: output_path, option: false, type: pathlib.Path, default: "run.f" }
    dst: { node: output-dir, port: path }
  - src: { cli: output_path, option: false, type: pathlib.Path, default: "run.f" }
    dst: { node: write, port: path }
  # Options.
  - src: { cli: model_config, type: str, default: "models.yaml" }
    dst: { node: config-path, port: name }
  - src: { cli: unroll, type: bool, default: false }
    dst: { node: extract, port: unroll, required: true }
  - src: { cli: flatten, type: bool, default: false }
    dst: { node: gate-flatten, port: flag, required: true }
  - src: { cli: strip_options, type: bool, default: false }
    dst: { node: gate-strip, port: flag, required: true }
  - src: { cli: deduplicate, type: bool, default: false }
    dst: { node: gate-dedup, port: flag, required: true }

  # ---- head: CWD → config-path → model loading → extract ----
  - src: { node: work-dir }
    dst: { node: config-path, port: dir }
  - src: { node: config-path }
    dst: { node: load-model, port: model_path }
  - src: { node: config-path }
    dst: { node: model-dir, port: path }
  - src: { node: load-model, port: model }
    dst: { node: extract, port: source }
  - src: { node: model-dir }
    dst: { node: extract, port: base_dir }
  - src: { node: output-dir }
    dst: { node: normalise, port: base_dir }

  # ---- pipeline: extract → normalise → gate chain → write → log ----
  - src: { node: extract, port: entries }
    dst: { node: normalise, port: entries }
  - src: { node: normalise, port: entries }
    dst: { node: gate-flatten, port: value }
  # gate-flatten → flatten → gate-strip
  - src: { node: gate-flatten, port: on }
    dst: { node: flatten, port: entries }
  - src: { node: flatten, port: entries }
    dst: { node: gate-strip, port: value }
  - src: { node: gate-flatten, port: off }
    dst: { node: gate-strip, port: value }
  # gate-strip → strip → gate-dedup
  - src: { node: gate-strip, port: on }
    dst: { node: strip, port: entries }
  - src: { node: strip, port: entries }
    dst: { node: gate-dedup, port: value }
  - src: { node: gate-strip, port: off }
    dst: { node: gate-dedup, port: value }
  # gate-dedup → dedup → write
  - src: { node: gate-dedup, port: on }
    dst: { node: dedup, port: entries }
  - src: { node: dedup, port: entries }
    dst: { node: write, port: entries }
  - src: { node: gate-dedup, port: off }
    dst: { node: write, port: entries }
  # write → log
  - src: { node: write, port: filelist }
    dst: { node: log-filelist, port: value }
  ```

  Seven CLI parameters, all read off `do_gen_model_filelist` (`rtl_buddy/src/rtl_buddy/rtl_buddy.py:441-447`):

  | cli name | src | kind | type | default | help | destinations |
  |---|---|---|---|---|---|---|
  | `model_name` | `:441` | positional | `str` | — (required) | `name of model` | `load-model.model_name` |
  | `output_path` | `:442` | positional | `pathlib.Path` | `run.f` | `Output filename` | `output-dir.path`, `write.path` |
  | `model_config` | `:443` | option | `str` | `models.yaml` | `model_config.yaml to use` | `config-path.name` |
  | `unroll` | `:444` | option | `bool` | `false` | `Recursively unroll -F in filelists` | `extract.unroll` |
  | `flatten` | `:445` | option | `bool` | `false` | `Remove path to a file, leaving just the filename` | `gate-flatten.flag` |
  | `strip_options` | `:446` | option | `bool` | `false` | `Remove option part of a line` | `gate-strip.flag` |
  | `deduplicate` | `:447` | option | `bool` | `false` | `Remove duplicates` | `gate-dedup.flag` |

  Notes on the CLI surface and wiring:
  - **Positional order.** `model_name` first, `output_path` second — set by declaration order of their first CLI edge in the `edges` list.
  - **Fan-out.** `output_path` fans to two destinations (`output-dir.path` and `write.path`) — two CLI edges with identical descriptors (`docs/harness_configs/graph.md`). `config-path`'s default output fans to two destinations (`load-model.model_path` and `model-dir.path`) — two node edges. `model_config` itself has a single CLI edge to `config-path.name`; the fan-out happens downstream, after CWD resolution.
  - **`config-path` (`dirjoin`).** Resolves the bare `model_config` filename against CWD: `work-dir` provides `Path.cwd().resolve()` on port `dir`, the CLI `model_config` string arrives on port `name`, and `dirjoin` returns `Path(dir) / name` — an absolute `Path` that `load-model` and `model-dir` both accept. This replaces the implicit CWD resolution `ModelConfigLoader` performs in rtl_buddy.
  - **`model_name` has no default** — it is required. Omitting `default` in the CLI descriptor makes the parameter mandatory.
  - **`required: true` on defaulted CLI-fed ports.** `unroll`, `flatten`, `strip_options`, and `deduplicate` all feed ports with Python defaults (`False`). Without `required: true`, `DefaultContract` treats the port as special (non-blocking), and the module's default can silently win a race against the CLI injection. `required: true` forces the first invocation to await the real value. The three gate flags additionally list `flag` in `persistent_inputs` — both, always, per [spec 09](09-flag-gate.md#the-flag-needs-required-true-and-persistent_inputs). `unroll` on `extract` needs only `required: true` (no `persistent_inputs`): the node fires once, so there is no second invocation to replay for.
  - **`strip_options`** is the CLI name, matching rtl_buddy's parameter name (`rtl_buddy.py:446`); the parameter reaches `write_output` as `strip=strip_options` (`:457`). The plan calls the node-port name `strip` (spec [05](05-filelist-strip.md)), which is the input port of `filelist-strip`, not the CLI parameter. [Spec 09](09-flag-gate.md#wiring--the-filelist-graph) wrote `cli: strip` in its wiring example; this spec carries the final CLI name.
  - **No short flags.** rtl_buddy declares `-c`/`-u`/`-f`/`-s`/`-d` short forms; the graph YAML schema has no `short_flag` field, so the CLI exposes long-form options only (`--model-config`, `--unroll`, `--flatten`, `--strip-options`, `--deduplicate`).

  Contract choices:
  - **`work-dir`** — `default`. Zero inputs; fires once on graph start, emitting `Path.cwd().resolve()`. Per [implementation-test spec 04f](../implementation-test/specs/04f-work-dir.md).
  - **`config-path`** — `unit`. Two inputs (`dir` from `work-dir`, `name` from CLI `model_config`); fires once.
  - **`load-model`** — `default`. Two inputs (`model_name` from CLI, `model_path` from `config-path`) and one unwired (`test`, default `None`); fires once. [00-overview § Head](00-overview.md#head): "runs the node under `default` — one module, two graphs, the difference entirely in wiring."
  - **`model-dir`, `output-dir`** — `unit`. One input, one invocation, per [spec 10](10-dirname.md).
  - **`extract`** — `default`. Three singleton inputs (`source`, `base_dir`, `unroll`). `unroll` is the only defaulted port; `required: true` on its edge prevents the default from racing.
  - **`normalise`** — `default` with `persistent_inputs: [base_dir]`, per [spec 03](03-filelist-normalise.md#contract--per-graph-module-is-envelope-agnostic). The singleton `base_dir` from `output-dir` is cached, though the node fires only once.
  - **`gate-flatten`, `gate-strip`, `gate-dedup`** — `default` with `persistent_inputs: [flag]`, per [spec 09](09-flag-gate.md#wiring--the-filelist-graph).
  - **`flatten`, `strip`, `dedup`** — `default`. One input (`entries`, no default), fed by the gate's `on` arm; the node fires once if the flag is true, never if false.
  - **`write`** — `default`. Two singleton inputs (`entries`, `path`); `test` unwired, default `None`. On success, emits `("filelist", path)` to `log-filelist`; on write error, logs and emits nothing, so `log-filelist` never fires and the node terminates on `EndSentinel`.
  - **`log-filelist`** — `default`. One input (`value`, no default); fires once if `write` succeeds, never otherwise. Terminal sink — no output ports.

- **`modules/config.yaml`** — the seven pipeline entries are listed in [00-overview](00-overview.md#the-pipeline-at-a-glance). This spec asserts that every node in `graphs/filelist.yaml` resolves against the manifest. Additional entries beyond the seven: `filelist-path` ([spec 13](13-filelist-path.md)) in the `rtl_buddy/build.py` block; `dirname`, `dirjoin`, `logger`, `constant` in the `funcs.py` block; `flag-gate` in the `rtl_buddy/control.py` block. The `rtl_buddy/setup.py` block drops `route-list-mode` ([spec 14](14-test-update.md)).

  Not every entry in the manifest is wired by this graph. `prioritised-merge`, `constant`, and `filelist-path` are registered for the `test` graph ([spec 14](14-test-update.md)) and for reuse by sibling graphs. This spec asserts that every node in `graphs/filelist.yaml` resolves against the manifest — the central registry-resolvability assertion.

- **`rtl_comrade_config.yaml`** — add:
  ```yaml
  commands:
    filelist:
      path: "graphs/filelist.yaml"
      help: "Generate a compile filelist from a model configuration."
  ```

## Tests

Graph-assembly checks in `tests/test_graph_assembly.py` (or similar) — the inputs are the committed YAML files, the expected outputs are load/validation outcomes. Fixtures: the harness `Graph.from_file` / `validation.py` API; a CLI runner for the `--help` cases.

- `Graph.from_file("graphs/filelist.yaml")` → loads without error; every node's module name resolves against `modules/config.yaml` (`work-dir`, `dirjoin`, `load-model`, `dirname` ×2, `filelist-extract`, `filelist-normalise`, `flag-gate` ×3, `filelist-flatten`, `filelist-strip`, `filelist-dedup`, `write-filelist`, `logger`). No contract beyond `default` and `unit` is referenced; those are built-in and need no manifest.
- `validation.py` on the loaded graph → reports **no** cycles and **no** overloaded inputs. Each gate's two arms (`on`/`off`) feed one downstream input port (`gate-strip.value`, `gate-dedup.value`, or `write.entries`); the harness validates them as mutually-exclusive sources via branch labels ([`docs/harness/branch_labels.md`](../docs/harness/branch_labels.md)) without `overloaded_srcs`. No `missing_required_inputs` or `unknown_persistent_ports`.
- Running the graph with a committed model fixture → `write` produces the `.f` file at `output_path`; `log-filelist` emits one `filelist_written` event at `info` carrying the path; exit 0.
- Running with `--flatten --strip-options --deduplicate` → each gate routes to `on`; the transforms apply (basename, option-drop, dedup); the `.f` reflects all three.
- Running with none of the three flags → each gate routes to `off`; no transform runs; the `.f` matches `filelist-extract → filelist-normalise → write-filelist` directly.
- A write error (unwritable `output_path`) → `write` logs the error event and emits nothing on `filelist`; `log-filelist` never fires; exit non-zero.
- `uv run rtl-comrade --help` → output lists `filelist` with the help string `"Generate a compile filelist from a model configuration."`.
- `uv run rtl-comrade filelist --help` → output lists every CLI parameter (`model_name` positional required, `output_path` positional default `"run.f"`, `model_config` option default `"models.yaml"`, `unroll`/`flatten`/`strip_options`/`deduplicate` options bool default `false`) with correct types and defaults.

## Acceptance criteria

- `uv run rtl-comrade --help` lists `filelist` with the help string.
- `uv run rtl-comrade filelist --help` lists every CLI parameter from the table above with correct types and defaults.
- Graph loads without validation errors — `Graph.from_file("graphs/filelist.yaml")` succeeds.
- `validation.py` reports no cycles, no overloaded inputs, no missing required inputs, no unknown persistent ports.
- Every module name in the graph resolves against `modules/config.yaml` (this spec is the central owner of the registry-resolvability assertion for the `filelist` graph, as [spec 11](../implementation-test/specs/11-graph-and-manifests.md) is for `test`).
- On a clean run, the only console output is the `filelist_written` log event from `log-filelist`.
- A write failure exits non-zero with no `filelist_written` event.

## Constraints

- Wire per the YAML above. The gate-chain edges are [spec 09](09-flag-gate.md#wiring--the-filelist-graph)'s, renamed from `cli: strip` to `cli: strip_options`.
- **No `logging` block.** The command has no tests to tabulate and no summary processors.
- **No keying.** Entries travel as a bare `list[entry]` throughout; no `KeyedValue` envelopes, no `keyed_join` contracts, no `unwrap`. [Spec 03](03-filelist-normalise.md) is envelope-agnostic — it works on bare lists here and uses `keyed_join` with `unwrap: true` in the test graph.
- **No `prioritised-merge`, `constant`, or `filelist-path`.** Single source (model only), CLI supplies `unroll` and `output_path` — the nodes the `test` graph needs for these roles are absent here. Their manifest entries are registered for other graphs, not consumed by this one.
- **`test` is unwired on `write-filelist`.** The writer's `test:TestConfig|None = None` default applies; write-error events log `key=None, test_name=None`. The `filelist` graph declares no summary processors, so those events render as plain ERROR log lines and a non-zero exit, not summary rows.
- **Each gate's arms rejoin before the next gate.** `gate-flatten`'s `on`/`off` rejoin at `gate-strip.value`; `gate-strip`'s at `gate-dedup.value`; `gate-dedup`'s at `write.entries`. The labels cancel at each rejoin, keeping the chain flat ([spec 09 § Rejoining the arms](09-flag-gate.md#rejoining-the-arms)).
- **`required: true` on every CLI-fed defaulted port.** Prevents the module's Python default from racing the CLI injection. The three gate flags additionally carry `persistent_inputs: [flag]` (spec 09's prescription); `extract.unroll` needs only `required: true` (the node fires once).
- The assembled graph must load with no cycles and no overloaded inputs (single-source-per-port, with the three mutually-exclusive gate-arm pairs validated by branch labels).

## Open items

None — the two `scratch.md` items (`model_path` type coercion and `model_config` CWD resolution) are resolved by the `work-dir` + `config-path` (`dirjoin`) wiring above. `dirjoin` is specified in [spec 15](15-dirjoin.md).
