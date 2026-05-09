# `loader.py`

Source: [src/rtl_comrade/loader.py](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade/loader.py)

## Role

This file handles two related harness jobs:

- loading YAML-backed config files
- discovering and importing plugin classes from configured paths

## See Also

- [README.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/README.md)
- [graph.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/graph.md)
- [config.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/config.md)
- [structure.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/structure.md)

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

## Caveats

- without a manifest, all classes in a module are exposed, which can accidentally include helper or imported classes
- because `structure.py` later uses `inspect.getsource(...)`, this loader intentionally inserts imported modules into `sys.modules`
- many failures here log at fatal level by design, so import and parse errors block execution instead of letting the harness attempt to limp into runtime
