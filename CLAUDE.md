# CLAUDE.md

## What this repo is

`rtl-comrade` is a graph runner that executes modular Python nodes under contract-driven scheduling. Three distinct layers:

- **harness** (`src/rtl_comrade/`) — graph loading, orchestration, ports, validation, failure semantics
- **contracts** (`contracts/`) — scheduling and input-consumption policy
- **modules** (`modules/`) — node-local computation

Keep that split intact. Do not move scheduling logic into modules. Do not let modules know about the graph.

## Running

Commands are defined in `rtl_comrade_config.yaml` (searched upward from cwd to git root):

```yaml
commands:
  add:
    path: "graphs/graph2.yaml"
```

Then invoke by subcommand name:

```bash
uv run rtl-comrade add
uv run rtl-comrade --level debug add
uv run rtl-comrade --config-file other_config.yaml add
```

Python `>=3.11`. Runtime deps: `pyserde[yaml]`, `structlog`, `typer`.

## Before changing anything

| What you're touching | Read first |
|---|---|
| CLI / startup | `docs/harness/app.md` |
| Harness | `docs/harness/README.md` |
| Modules | `docs/module-implementation.md`, `modules/io.py`, `modules/funcs.py` |
| Contracts | `docs/contract-implementation.md`, `docs/available_contracts.md`, `contracts/contracts.py` |

`AGENTS.md` is the routing and invariants document. This file is a distillation of it — when they conflict, trust `AGENTS.md`.

## Global invariants — do not violate

- **`EndSentinel`** is core to the runtime. Wrong behavior here deadlocks or prematurely stops graphs.
- **Graph validation is fail-fast.** Malformed graphs must be rejected before runtime.
- **Logging is part of the failure model:**
  - `DEBUG`/`INFO`/`WARNING` — normal
  - `ERROR` — deferred failure; best-effort completion, then failing exit
  - `CRITICAL` — immediate failure
- **`structure.py` output-port inference is intentionally conservative.** Dynamic output names are allowed but weaken validation.
- **Input ports are single-source.** Multiple upstream edges into the same input port = overloaded input error.

## Module authoring rules

- Must expose `run(...)`. Parameters define input ports in declaration order.
- Default argument values become default-valued input ports.
- `__init__` may accept `config` (raw config), `Config` class (auto-deserialized), and/or `id` (harness passes `<node-id>.module`).
- `run(...)` may be sync, async, a generator, or async generator.
- Return `None` → emits nothing. Return non-tuple non-`None` → emits on `"default"` port. Return/yield `(port_name, value)` → emits on named port (`port_name` must be a string).
- May optionally expose `finalise()` (sync or async) — called once after all `run(...)` invocations, before `EndSentinel` propagates. Takes no arguments; return value is discarded.

## Contract authoring rules

- Must expose `get_inputs()` — sync or async.
- Must return `dict[str, Payload]` or `EndSentinel`.
- `__init__` may accept `config`, `Config`, `id`, and/or `ports` (contract-facing port adapters). Useful contracts almost always need `ports`.

## Config shape (`graph2.yaml` is the canonical example)

```yaml
modules:   # plugin paths
contracts: # contract plugin paths
nodes:     # node definitions
edges:     # graph connections
```

## Contribution rules

- Changes stay local to the seam being edited.
- If harness behavior affecting plugin authoring changes → update `docs/harness/`.
- If config shape, port semantics, or plugin loading changes → update the sample graph and manifests in the same commit.
- Prefer executable examples when introducing runtime features.
- Run tests with `uv run pytest tests/`. The suite covers all harness modules (unit) and the full `Graph.from_file → Graph.run` path (integration). See `docs/testing.md` for the full testing procedure and `tests/conftest.py` for shared fixtures.
- Do not treat `README.md` as the authoritative architecture document.

## Testing

Run the test suite:

```bash
uv run pytest tests/
```

Layout:

```
tests/
  conftest.py            # shared fixtures: logging_handler, make_graph_config, tmp_plugin_dir
  unit/                  # one file per harness module
  integration/           # full Graph.from_file → Graph.run scenarios
```

Key conventions:
- Tests that exercise fatal/error log paths use the `logging_handler` fixture. Fatal calls (`log.critical`/`log.fatal`) raise `SystemExit(1)`; assert with `pytest.raises(SystemExit)`. Error calls set `handler.failure = True` without raising.
- Integration tests write temporary plugin `.py` files to `tmp_path` and construct `GraphConfig` objects directly; they do not touch `graph2.yaml`.
- `asyncio_mode = "auto"` is set in `pyproject.toml`; async tests need no extra decoration.

See `docs/testing.md` for the two-stage testing procedure and coverage commands for each section.

## Current state / known gaps

- Graph paths in `rtl_comrade_config.yaml` are resolved relative to the runner's working directory, not relative to the config file.
- Subcommands have no options; graph configs are not introspected for dynamic CLI parameters.
- No automated test suite.
