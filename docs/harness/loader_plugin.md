# `loader_plugin.py`

Source: [src/rtl_comrade/loader_plugin.py](../../src/rtl_comrade/loader_plugin.py)

## Role

The harness plugin-discovery layer: turning configured plugin paths into module and contract class mappings. `graph.py` relies on it to resolve and import plugin classes.

## See Also

- [README.md](README.md)
- [loader_utils.md](loader_utils.md) — provides `import_plugin_file` (the dynamic import) and `load_config_file`
- [graph.md](graph.md)
- [config_graph.md](config_graph.md) — calls `load_plugin_configs`
- [structure.md](structure.md)

## Main Responsibilities

- parse plugin-folder manifests (`config.yaml`)
- resolve configured paths into a deduplicated list of plugin files
- import plugin classes (delegating the dynamic import to `loader_utils.import_plugin_file`)
- expose exported plugin classes under graph-visible names

## Supported Plugin Layouts

- a single Python file path
- a directory with `config.yaml` (a manifest)
- a directory without `config.yaml`, in which case `.py` files are auto-discovered

## Manifest Semantics

A manifest can list plugin files explicitly, rename exported plugin names, and map multiple classes out of one file.

## Two-stage API

Plugin loading is split into resolution and loading so callers can inspect the file list before any Python is executed:

1. **Resolution** (`load_plugin_config(path, relative_path)`, `load_plugin_configs(paths, relative_path)`) — filesystem-only: discovers which Python files belong to a configured path and returns `list[PluginFileConfig]`. No Python is imported. The optional `relative_path` is prepended to the given path before any filesystem access, so callers can supply paths relative to a config file's directory. Duplicate file paths within a single `load_plugin_config` call are deduplicated by resolved path; duplicate paths across a `load_plugin_configs` call are also skipped.
2. **Loading** (`PluginFileConfig.load(namespace)`, `load_plugins(configs, namespace)`) — imports each plugin file and returns a `dict[str, type]` mapping exported name to class. The optional `namespace` scopes the `sys.modules` key (see [loader_utils.md](loader_utils.md)) for manifest-named files.

`GraphConfig.from_file_config` calls `load_plugin_configs` on the `Path` objects from `GraphFileConfig`, passing the graph file's parent directory as `relative_path`; actual class loading happens later in `Graph.from_config`. Call hierarchy: `load_plugins` → `config.load(namespace)`.

`graph.py` passes `'modules'` and `'contracts'` as the respective namespaces when loading the two plugin sets, keeping their `sys.modules` keys structurally disjoint even if both sets contain a manifest-named file with the same name.

## Caveats

- without a manifest, auto-discovery filters to classes defined in the plugin file itself (by checking `cls.__module__ == module.__name__`); imported classes are excluded to prevent duplicate exports when multiple plugin files share a helper.
- duplicate exported names are fatal: within one file (`duplicate_key`) and across files in a `load_plugins` call (`duplicate_definition`).
- invalid files, invalid manifests, and broken imports log at fatal level by design, stopping bad graphs before execution begins.
