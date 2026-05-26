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

- load YAML files with shared error handling
- parse plugin-folder manifests
- import plugin modules dynamically from file paths
- expose exported plugin classes under graph-visible names
- normalize file paths relative to a plugin folder manifest
- register imported modules in `sys.modules`

## Place In The System

This is the harness discovery layer. `graph.py` relies on it to turn configured plugin paths into module and contract class mappings.

It also participates in the harness fail-fast boundary: invalid files, invalid manifests, and broken imports are intended to stop bad graphs before execution starts.

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

1. **Resolution** (`resolve_path`, `resolve_paths`) — filesystem-only: discovers which Python files belong to a configured path and returns `list[PluginFileConfig]`. No Python is imported. Duplicate file paths within a single `resolve_path` call are deduplicated by resolved path. Duplicate path strings across a `resolve_paths` call are also skipped.
2. **Loading** (`PluginFileConfig.load`, `load_file_configs`) — imports each plugin file and returns a `dict[str, type]` mapping exported name to class.

`GraphConfig.from_file_config` calls `resolve_paths` on the raw path strings from `GraphFileConfig`; actual class loading happens later in `Graph.from_config`.

Call hierarchy: `load_file_configs` → `config.load()`. The legacy entry points `load_path` and `load_paths` are still available and compose `resolve_path` + `load_file_configs` internally.

## Cross-file imports

Before importing a plugin file, `PluginFileConfig.load` inserts the appropriate directory into `sys.path` so that plugin files can import siblings via Python's normal import machinery. For a package directory (one containing `__init__.py`) the parent is inserted so that `from pkg.sibling import X` resolves; for a plain directory the directory itself is inserted.

## Caveats

- without a manifest, auto-discovery filters to classes defined in the plugin file itself (by checking `cls.__module__ == module.__name__`); imported classes are excluded to prevent duplicate exports when multiple plugin files share a helper
- a module already present in `sys.modules` under its canonical name is reused rather than re-executed; re-executing would produce a second distinct class object and break `isinstance` checks. The canonical name is only computed for package directories — plain-directory file stems (e.g. `io`, `re`) collide with stdlib
- because `structure.py` later uses `inspect.getsource(...)`, this loader intentionally inserts imported modules into `sys.modules`
- many failures here log at fatal level by design, so import and parse errors block execution instead of letting the harness attempt to limp into runtime
- when the loader catches non-`rtl_comrade` exceptions during YAML reads, filesystem access, or dynamic imports, it logs them with `exc_info=e` so traceback context is preserved
