# `loader_utils.py`

Source: [src/rtl_comrade/loader_utils.py](../../src/rtl_comrade/loader_utils.py)

## Role

Shared low-level loader helpers used by both the plugin loader and the logging loader:

- `load_config_file(Config, path, parent)` — load one YAML file into a serde-backed type with shared error handling. Opens `parent / path`, defaulting `parent` to `Path()`, keeping YAML paths relative to the config file that contains them.
- `import_plugin_file(file, name, namespace)` — dynamically import one plugin Python file and return its module object, registering it in `sys.modules` and putting its directory on `sys.path` for sibling imports.

## See Also

- [README.md](README.md)
- [loader_plugin.md](loader_plugin.md) — uses both helpers
- [loader_logger.md](loader_logger.md) — uses `import_plugin_file`
- [config.md](config.md)

## Key Behaviors

- `load_config_file` catches and fatal-logs YAML/serde/filesystem errors so malformed config stops the harness before execution.
- `import_plugin_file` leaves the plugin/file logging context bound on return so callers can attach their own member-selection diagnostics.
- fatal-level logging is used deliberately for missing files, invalid specs, and import errors so bad graphs are stopped before execution begins.
- non-`rtl_comrade` exceptions during YAML reads, filesystem access, or dynamic imports are logged with `exc_info=e` so traceback context is preserved.

## `sys.modules` key construction

The key under which a plugin file is registered in `sys.modules` (`plugin_name`) depends on whether the file has a caller-supplied name:

- **No name** (`name is None`): the key is the file path with the suffix stripped and `/` replaced by `.` (e.g. `/home/user/project/modules/stuff.py` → `home.user.project.modules.stuff`). The full path makes collisions between different files impossible regardless of namespace.
- **Name set**: the key is `{namespace}.{name}`. When `namespace` is non-empty this scopes the key to the plugin set (e.g. `modules.stuff`, `contracts.stuff`). When `namespace` is the empty string (the default) the key is `.{name}` — a leading-dot string that no user-supplied manifest name can produce, keeping it structurally disjoint from any namespaced key.

## Cross-file imports

Before importing a plugin file, `import_plugin_file` inserts the appropriate directory into `sys.path` so that plugin files can import siblings via Python's normal import machinery. For a package directory (one containing `__init__.py`) the parent is inserted so that `from pkg.sibling import X` resolves; for a plain directory the directory itself is inserted.

## Caveats

- a module already present in `sys.modules` under its canonical name or `plugin_name` is reused rather than re-executed; re-executing would produce a second distinct class object and break `isinstance` checks. The canonical name is only computed for package directories — plain-directory file stems (e.g. `io`, `re`) collide with stdlib.
- because `structure.py` later uses `inspect.getsource(...)`, this loader intentionally inserts imported modules into `sys.modules`.
