# `__main__.py`

Source: [src/rtl_comrade/__main__.py](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade/__main__.py)

## Role

This is the current process entrypoint for the harness. It is intentionally minimal and mainly supports basic testing.

## See Also

- [README.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/README.md)
- [graph.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/graph.md)
- [logging.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/logging.md)

## What It Does

- initializes logging through `initialise_logging(...)`
- chooses a graph path from `argv[1]` or falls back to `graph.yaml`
- builds a `Graph` with `Graph.from_file(...)`
- runs the graph with `asyncio.run(...)`
- converts logged failures into a process exit code

## Place In The System

`__main__.py` sits at the outermost edge of the harness. It does not contain graph logic itself; it just bootstraps the rest of the runtime.

## Current Limitations

- argument handling is hardcoded
- logging level selection is hardcoded
- there is no proper subcommand structure
- `graph.yaml` is the default even though the repository does not currently ship that file

## Likely Future Direction

The intended long-term direction is a proper `typer`-based CLI rather than additional ad hoc argument parsing here.
