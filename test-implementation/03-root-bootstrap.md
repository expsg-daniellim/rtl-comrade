# Spec 03: RootBootstrap

## What this covers

Implement `RootBootstrap` in `modules/rtl_buddy_compat/bootstrap.py` (the file created by spec 02). This is the most I/O-intensive bootstrap module: it walks the directory tree looking for `root_config.yaml`, selects the platform builder, and emits a `RootContext` carrying serialized config as plain dicts so no live config objects cross the graph boundary.

## Prerequisites

Spec 00 (artefacts) and spec 02 (bootstrap.py file exists) must be complete.

## Before you start

Read:
- `rtl_buddy/src/rtl_buddy/config/root.py` — full file; `_discover_root_cfg()`, `RootConfig.__init__()`, platform/builder selection
- `rtl_buddy/src/rtl_buddy/config/rtl.py` — `RtlBuilderConfig` YAML schema (so you know what fields `rtl_builder_cfg` dict will have)
- `rtl_buddy/src/rtl_buddy/rtl_buddy.py:L171-L172` — mode defaults to `"debug"` for `test` command

## Addition to `modules/rtl_buddy_compat/bootstrap.py`

### `RootBootstrap`

```
contract: zip
inputs:  rtl_builder_mode: str | None, builder_override: str | None, run_depth: str
outputs: default → RootContext
```

All three inputs arrive from CLI edges.

Implementation steps:

1. **Discover** `root_config.yaml`: walk up from `os.getcwd()` until the file is found or the filesystem root is reached. Fatal (`log.critical` + `SystemExit`) if not found. Port `_discover_root_cfg()` from `root.py:L12-L31`.

2. **Load** the YAML. Expected top-level keys: `platform` (dict), `builder` (dict of builder-name → builder-config-dict). Fatal if malformed.

3. **Select platform**: `platform.uname().system.lower()`. Map `"linux"` → look up `"linux"` key, `"darwin"` → look up `"darwin"` key (or whatever keys the config defines). Fatal if no matching key. Source: `root.py:L46-L80`.

4. **Select builder**: if `builder_override` is set use that; otherwise use the platform's default builder name. Fatal if the chosen builder name is not in `config["builder"]`. Source: `root.py:L80-L113`.

5. **Set mode**: `rtl_builder_mode = rtl_builder_mode or "debug"`.

6. **Emit**: `RootContext(builder_name=..., rtl_builder_mode=..., run_depth=run_depth, project_root=root_config_path.parent, root_config_path=root_config_path, rtl_builder_cfg=config["builder"][builder_name], platform_name=platform_name)`.

`rtl_builder_cfg` is the raw dict for the selected builder — no live `RtlBuilderConfig` object crosses the boundary.

## Register in `modules/rtl_buddy_compat/config.yaml`

Add `RootBootstrap` to the existing `bootstrap.py` entry (created by spec 02):

```yaml
  - name: root_bootstrap
    class_name: RootBootstrap
```

## Tests

Add to `modules/rtl_buddy_compat/tests/test_bootstrap.py`.

Use `tmp_path` and write minimal `root_config.yaml` files. Look at `rtl_buddy/src/rtl_buddy/config/root.py` for the expected YAML schema.

- Valid config, matching platform → `RootContext` emitted with correct `builder_name`
- `builder_override` set → overrides the platform default
- `rtl_builder_mode=None` → `rtl_builder_mode="debug"` in context
- Missing `root_config.yaml` anywhere in tree → `SystemExit`
- Platform key not in config → `SystemExit`
- Builder name not in config → `SystemExit`
- `project_root` is the directory containing `root_config.yaml`

## Constraints

- Do not carry a live `RootConfig` or `RtlBuilderConfig` object. Everything must be serialized to primitives in `RootContext`.
- Do not import from the `rtl_buddy` package. Port the discovery and loading logic inline.
- The directory walk must stop at the filesystem root, not loop forever.
