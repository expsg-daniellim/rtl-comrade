# `loader_logger.py`

Source: [src/rtl_comrade/loader_logger.py](../../src/rtl_comrade/loader_logger.py)

## Role

Defines the `LoggingConfig` schema (a graph's `logging` block) and its `LoggingHandlerConfig` entries, and resolves that config into the per-run logging plugins. `LoggingConfig.load` is called from the `run` closure in [graph.md](graph.md) before any node executes.

## See Also

- [README.md](README.md)
- [loader_utils.md](loader_utils.md) — provides `import_plugin_file`
- [logging.md](logging.md) — the processor/handler model, `include_default`, and the harness `LoggingFatalHandler`
- [app.md](app.md) — `App.setup_logging`, the consumer that calls `LoggingPlugin.construct` to install these specs
- [config.md](config.md), [config_graph.md](config_graph.md) — carry the `logging` field typed as `LoggingConfig`
- [graph.md](graph.md) — the `run` closure that calls `LoggingConfig.load`

## Main Types and Functions

- `LoggingHandlerConfig` (serde schema): one custom-handler reference (`path`, `name`, `config`). Its `load()` method imports the handler's plugin file and selects the named object, classifying it (a `logging.Handler` subclass, a processor class, or a processor function/instance) and rejecting anything else. It does **not** construct it.
- `LoggingConfig` (serde schema): the container for a graph's `logging` block — a `handlers` list of `LoggingHandlerConfig` plus the top-level `include_default` bool (default `true`). Defined here and imported by [config.md](config.md) and [config_graph.md](config_graph.md) as the type of the `logging` field. Its `load(relative_path)` method classifies every entry into processor specs vs root-handler specs (preserving processor order), validates each processor's signature against structlog's `Processor` shape, and returns the `(processors, handlers)` pair. The consumer reads `include_default` off the config object separately. The entries are `LoggingPlugin` specs — imported and checked but **not constructed**.
- `LoggingPlugin`: a resolved-but-unconstructed entry — the selected `plugin`, its raw `config` dict, the `relative_path` for `{graph}` resolution, and the configured `name`. Its `construct()` method instantiates a class (deserialising its `Config`, relativising `{graph}` paths) or returns a function/instance unchanged; the consumer calls it at install time.

## Key Behaviors

- construction (instantiating a class, deserialising its `Config`, relativising `{graph}` paths) lives on `LoggingPlugin.construct` and runs only when the consumer (`App.setup_logging`) installs the specs, not during resolution — so `LoggingConfig.load` returns unconstructed specs, mirroring how the loader returns module/contract **classes** for `node.py` to construct.
- signature validation runs on the *unconstructed* object: a processor class is validated on its `__call__` with `self` dropped; a function or instance is validated directly.
- under `include_default: false`, the last processor is terminal and must return `str`; all others must return an `EventDict`. With no processors and no handlers, `no_renderers` is warned.
- fatal-level logging is used for invalid objects, signature mismatches, and unresolved annotations.
