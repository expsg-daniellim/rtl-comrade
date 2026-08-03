# The `filelist` Graph

Graph file: `graphs/filelist.yaml` — registered as the `filelist` subcommand in `rtl_comrade_config.yaml`.

See also:

- [index.md](index.md) — graphs usage reference: CLI, output layout
- [docs/modules/index.md](../modules/index.md) — reference for the pipeline modules
- [docs/contracts/index.md](../contracts/index.md) — the scheduling policies the nodes are paired with
- [docs/harness_configs/graph.md](../harness_configs/graph.md) — the graph YAML format (nodes, edges, CLI edges, contract config)
- [docs/running.md](../running.md) — invocation, options, config discovery, exit codes

The `filelist` graph generates a compile filelist (`.f`) from a model configuration. It is a native reimplementation of upstream `rtl_buddy`'s `filelist` command (`do_gen_model_filelist`) as an `rtl-comrade` graph: it loads a model from `models.yaml`, extracts its filelist entries, runs them through a configurable transform pipeline (normalise, optionally flatten/strip/dedup), writes the `.f` file, and reports the written path. The same pipeline modules serve the `test` graph's per-test filelist generation — the difference is entirely in wiring: unkeyed here (one model, one invocation), keyed there (one filelist per test under `keyed_join`).

## Invocation

```bash
uv run rtl-comrade filelist MODEL_NAME [OUTPUT_PATH] [options]
```

`MODEL_NAME` is required; `OUTPUT_PATH` defaults to `run.f`. For global options (`--level`, `--config-file`) see [docs/running.md](../running.md). Within the graph the parameters feed:

| Parameter | Destination |
|---|---|
| `MODEL_NAME` | [load-model](../modules/load-model.md) |
| `OUTPUT_PATH` | `output-dir` (`dirname` instance), `write-filelist` |
| `--model-config` | `config-path` (`dirjoin` instance) |
| `--unroll` | `filelist-extract` |
| `--flatten` | `gate-flatten` (`flag-gate` instance) |
| `--strip-options` | `gate-strip` (`flag-gate` instance) |
| `--deduplicate` | `gate-dedup` (`flag-gate` instance) |

## Config files read

The `filelist` command reads only `models.yaml` (or a file specified by `--model-config`). It does not use `root_config.yaml` or `tests.yaml`.

| File | Node |
|---|---|
| `models.yaml` (or `--model-config`) | `config-path` (`dirjoin`, resolves against CWD) → [load-model](../modules/load-model.md) |

## Pipeline

For the full dataflow (per-edge payloads), see [`filelist-dataflow-diagram.md`](filelist-dataflow-diagram.md). The same flow in brief:

```
work-dir → config-path → load-model ─model─▶ extract ◀─base_dir─ model-dir ◀── config-path
                                                │
            output-dir ──base_dir─▶ normalise ◀─entries── extract
                                       │
  normalise ─▶ gate-flatten ──on──▶ flatten ──▶┐
               gate-flatten ──off─────────────▶ gate-strip ──on──▶ strip ──▶┐
                                                gate-strip ──off───────────▶ gate-dedup ──on──▶ dedup ──▶┐
                                                                             gate-dedup ──off───────────▶ write
                                                                                                    write → log-filelist
```

The flow reads in stages:

1. **Head** — `work-dir` provides CWD; `config-path` (`dirjoin`) resolves the `--model-config` filename against it; `load-model` reads the model configuration and returns the named model. `model-dir` and `output-dir` (two `dirname` instances) extract the base directories for resolution and normalisation.
2. **Extract** — `filelist-extract` turns the model record's filelist into `FilelistEntry` records resolved against `model-dir`, with `-F` unroll (when `--unroll` is set) and `+libext+` coalescing.
3. **Normalise** — `filelist-normalise` relativises each path against `output-dir` and emits existence warnings for missing files and non-directory `+incdir+` targets.
4. **Flag-gated transforms** — three `flag-gate` instances route entries through or past `filelist-flatten` (`--flatten`), `filelist-strip` (`--strip-options`), and `filelist-dedup` (`--deduplicate`). Each gate's `on`/`off` arms rejoin at the next gate's input port, keeping the chain flat. All three default to off.
5. **Write + report** — `write-filelist` renders entries to lines with a `// rtl-buddy generated model filelist` header and writes the `.f`; `log-filelist` (`logger` instance) reports the written path at `info`.

## Contracts

Every node fires once (all inputs are singletons) and runs under `default` or `unit`. There are no `keyed_join` contracts, no `KeyedValue` envelopes, and no `prioritised-merge` — entries travel as a bare `list[FilelistEntry]` throughout.

- **`work-dir`** — `default`. Zero inputs; fires once on graph start.
- **`config-path`** — `unit`. Two inputs (`dir` from `work-dir`, `name` from CLI); fires once.
- **`load-model`** — `default`. Two inputs (`model_name` from CLI, `model_path` from `config-path`); `test` unwired (default `None`).
- **`model-dir`, `output-dir`** — `unit`. One input each; fires once.
- **`extract`** — `default`. Three inputs (`source`, `base_dir`, `unroll`); `unroll` is `required: true` to prevent its `False` default from racing the CLI injection.
- **`normalise`** — `default` with `persistent_inputs: [base_dir]`. The singleton `base_dir` from `output-dir` is cached.
- **`gate-flatten`, `gate-strip`, `gate-dedup`** — `default` with `persistent_inputs: [flag]`. Each gate's `flag` edge is `required: true`; the pair gives "await once, replay thereafter".
- **`flatten`, `strip`, `dedup`** — `default`. One input (`entries`); the node fires once if its gate's flag is true, never if false.
- **`write`** — `default`. Two inputs (`entries`, `path`); `test` unwired (default `None`).
- **`log-filelist`** — `default`. One input; fires once if `write` succeeds, never otherwise. Terminal sink.

## Failure routing

The `filelist` graph declares no summary processors and no `logging` block — there is no test suite to tabulate. All failures render as plain log lines.

- **Extract failures.** An unresolvable `-F` include logs `filelist_resolve_error` at ERROR and skips the include. A malformed line logs `filelist_malformed_line` at ERROR and skips. Lower-case `-f` logs `filelist_lower_f_not_allowed` at FATAL (hard stop).
- **Normalise warnings.** Missing source files (`filelist_file_not_found`) and non-directory `+incdir+` targets (`filelist_incdir_not_a_dir`) log at ERROR, best-effort — the entry is still emitted.
- **Write errors.** `FileNotFoundError`, `IsADirectoryError`, `PermissionError`, and `OSError` each log their own event at ERROR and emit nothing on `filelist`, so `log-filelist` never fires. Write-error events carry `key=None` and `test_name=None` since there is no `TestConfig`.

Any `log.error` sets `handler.failure`, producing a non-zero exit. A `log.fatal` exits immediately. See [docs/running.md](../running.md).

## Outputs

On a clean run, the only console output is the `filelist_written` log event from `log-filelist`, reporting the path of the written `.f` file. The `.f` contains a `// rtl-buddy generated model filelist` header followed by the rendered entries — each line is a bare path (for source files), an option-prefixed path (for `-v`/`-y`/`+incdir+`/`-F` entries), or a coalesced `+libext+` value.

**Exit code** — any `log.error` exits non-zero; `log.fatal` exits immediately. See [docs/running.md](../running.md).
