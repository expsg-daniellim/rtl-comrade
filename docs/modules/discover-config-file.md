# `discover-config-file`

**Class:** `DiscoverConfigFileMod` (`modules/rtl_buddy/setup.py`)

[Back to index](index.md)

Walks up from the current directory looking for `filename`, returning the first match as a `Path`. This is the entry point that locates `root_config.yaml`.

## Inputs

None — source node.

## Config

```yaml
config:
  filename: root_config.yaml
  max_levels: 8
```

| Field | Type | Default | Purpose |
|---|---|---|---|
| `filename` | `str` | — | file to search for |
| `max_levels` | `int` | `8` | how many parent directories to ascend before giving up |

## Outputs

`default` — the resolved `Path` to the config file.

## Failure routing

`log.fatal` (`config_discovery_denied`) if a directory can't be read; `log.fatal` (`config_not_found`) if the file is not found within `max_levels` or the filesystem root is reached.

## Graph node

`discover-root`, contract `default`.
