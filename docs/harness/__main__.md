# `__main__.py`

Source: [src/rtl_comrade/__main__.py](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade/__main__.py)

## Role

Process entrypoint. Creates an `App` instance and delegates the entire CLI lifecycle to it.

## See Also

- [app.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/app.md)
- [README.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/README.md)
- [graph.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/graph.md)
- [logging.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/logging.md)

## What It Does

Constructs an `App`, calls `app.run()`, and forwards the returned exit code to `SystemExit`. All argument parsing, logging setup, config discovery, and graph execution happen in `App`.

## Place In The System

`__main__.py` is the outermost edge of the harness. It owns nothing except the `main()` function registered as the `rtl-comrade` / `rtl_comrade` entry point in `pyproject.toml`.
