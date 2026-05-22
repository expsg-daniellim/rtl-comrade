# CLAUDE.md

## What this repo is

`rtl-comrade` is a graph runner that executes modular Python nodes under contract-driven scheduling. Three distinct layers:

- **harness** (`src/rtl_comrade/`) — graph loading, orchestration, ports, validation, failure semantics
- **contracts** (`contracts/`) — scheduling and input-consumption policy
- **modules** (`modules/`) — node-local computation

Keep that split intact. Do not move scheduling logic into modules. Do not let modules know about the graph.

## Always follow

`docs/code-style.md` applies to all code changes.

## Before changing anything

| What you're touching | Read first |
|---|---|
| CLI / startup | `docs/harness/app.md` |
| Harness internals | `docs/harness/README.md` |
| Modules | `docs/modules/implementation.md`, `modules/io.py`, `modules/funcs.py` |
| Module testing | `docs/modules/testing.md` |
| Contracts | `docs/contracts/implementation.md`, `docs/contracts/index.md`, `contracts/contracts.py` |
| Contract testing | `docs/contracts/testing.md` |
| Global invariants | `docs/invariants.md` |
| Config files | `docs/harness_configs/index.md` |
| Testing procedure | `docs/testing.md` |
| Contribution process | `docs/contributing.md` |
| Adding / restructuring docs | `docs/creating-documentation.md` |

If your task isn't covered by the table, run `find docs/ -name "*.md" | sort` to see all available docs.

## Running

See `docs/running.md` for the full invocation syntax, options, and config file format.

## Testing

```bash
uv run pytest tests/
```

See `docs/testing.md` for the full two-stage procedure and coverage requirements.
