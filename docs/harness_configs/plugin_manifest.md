# Plugin Manifest (`config.yaml`)

A `config.yaml` file inside a plugin directory that maps plugin names to Python classes. Used by both module and contract plugin directories.

## Schema

```yaml
files:
- file: <str>          # filename relative to this manifest's directory
  plugins:
  - name: <str>        # plugin name used in graph YAML (module: or contract: fields)
    class_name: <str>  # Python class name inside the file
```

Multiple `plugins` entries per file are allowed. Multiple `files` entries are allowed.

## Examples

`modules/config.yaml`:

```yaml
files:
- file: io.py
  plugins:
  - name: fileread
    class_name: FileReadMod
  - name: stdout
    class_name: StdoutMod
- file: funcs.py
  plugins:
  - name: add
    class_name: AddMod
  - name: alu
    class_name: ALUMod
```

`contracts/config.yaml`:

```yaml
files:
- file: zip.py
  plugins:
  - name: zip
    class_name: ZipContract
- file: keyed_join.py
  plugins:
  - name: keyed_join
    class_name: KeyedJoinContract
  - name: required_inputs_by_key
    class_name: KeyedJoinContract
```

A single class can be registered under multiple names (`required_inputs_by_key` is an alias for `KeyedJoinContract`).

## Auto-discovery (no manifest)

If a plugin directory has no `config.yaml`, the loader auto-discovers all `.py` files and exports classes defined directly in each file (imported classes are excluded). Plugin names are derived from the class names. This is useful for quick prototyping but a manifest is preferred for explicit control.

## Cross-file imports

Before loading any file the loader inserts the plugin directory into `sys.path` so files can import siblings normally. For package directories (containing `__init__.py`) the parent is inserted instead so `from pkg.sibling import X` resolves correctly.
