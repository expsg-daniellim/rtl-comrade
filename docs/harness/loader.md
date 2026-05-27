# `loader.py`

Source: [src/rtl_comrade/loader.py](../../src/rtl_comrade/loader.py)

## Role

This file handles two related harness jobs:

- loading YAML-backed config files
- discovering and importing plugin classes from configured paths

## See Also

- [README.md](README.md)
- [graph.md](graph.md)
- [config.md](config.md)
- [structure.md](structure.md)

## Main Responsibilities

- load YAML files with shared error handling (`load_config_file(Config, path, parent)` opens `parent / path`, defaulting `parent` to `Path()`)
- parse plugin-folder manifests
- import plugin modules dynamically from file paths
- expose exported plugin classes under graph-visible names
- normalize file paths relative to a plugin folder manifest or a caller-supplied `relative_path`
- register imported modules in `sys.modules`

## Place In The System

This is the harness discovery layer. `graph.py` relies on it to turn configured plugin paths into module and contract class mappings.

It also participates in the harness fail-fast boundary: invalid files, invalid manifests, and broken imports are intended to stop bad graphs before execution starts.

## Key Behaviors

- plugin loading is split into resolution (`load_plugin_config`, `load_plugin_configs`) and import (`load_plugins`) so callers can inspect the file list before any Python is executed
- the optional `relative_path` argument to resolution functions prepends a base directory so callers can supply paths from a config file's directory without adjusting the raw path strings
- the optional `parent` argument to `load_config_file` opens `parent / path`, keeping YAML paths relative to the config file that contains them
- duplicate file paths within a single resolution call are deduplicated by resolved path; duplicate path strings across a `load_plugin_configs` call are skipped
- fatal-level logging is used deliberately for invalid files, manifests, and import errors so bad graphs are stopped before execution begins

## Supported Plugin Layouts

- a single Python file path
- a directory with `config.yaml`
- a directory without `config.yaml`, in which case `.py` files are auto-discovered

## Manifest Semantics

A manifest can:

- list plugin files explicitly
- rename exported plugin names
- map multiple classes out of one file

## Two-stage API

Plugin loading is split into resolution and loading:

1. **Resolution** (`load_plugin_config(path, relative_path)`, `load_plugin_configs(paths, relative_path)`) — filesystem-only: discovers which Python files belong to a configured path and returns `list[PluginFileConfig]`. No Python is imported. The optional `relative_path` argument is prepended to the given path before any filesystem access, so callers can supply paths relative to a config file's directory. Duplicate file paths within a single `load_plugin_config` call are deduplicated by resolved path. Duplicate paths across a `load_plugin_configs` call are also skipped.
2. **Loading** (`PluginFileConfig.load`, `load_plugins(configs)`) — imports each plugin file and returns a `dict[str, type]` mapping exported name to class.

`GraphConfig.from_file_config` calls `load_plugin_configs` on the `Path` objects from `GraphFileConfig`, passing the graph file's parent directory as `relative_path`; actual class loading happens later in `Graph.from_config`.

Call hierarchy: `load_plugins` → `config.load()`.

## Cross-file imports

Before importing a plugin file, `PluginFileConfig.load` inserts the appropriate directory into `sys.path` so that plugin files can import siblings via Python's normal import machinery. For a package directory (one containing `__init__.py`) the parent is inserted so that `from pkg.sibling import X` resolves; for a plain directory the directory itself is inserted.

## Caveats

- without a manifest, auto-discovery filters to classes defined in the plugin file itself (by checking `cls.__module__ == module.__name__`); imported classes are excluded to prevent duplicate exports when multiple plugin files share a helper
- a module already present in `sys.modules` under its canonical name is reused rather than re-executed; re-executing would produce a second distinct class object and break `isinstance` checks. The canonical name is only computed for package directories — plain-directory file stems (e.g. `io`, `re`) collide with stdlib
- because `structure.py` later uses `inspect.getsource(...)`, this loader intentionally inserts imported modules into `sys.modules`
- many failures here log at fatal level by design, so import and parse errors block execution instead of letting the harness attempt to limp into runtime
- when the loader catches non-`rtl_comrade` exceptions during YAML reads, filesystem access, or dynamic imports, it logs them with `exc_info=e` so traceback context is preserved
