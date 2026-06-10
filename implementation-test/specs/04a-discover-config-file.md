# Spec 04a: discover-config-file (`DiscoverConfigFileMod`)

**Depends on:** spec 01 (schema).
**References:** [03 — Setup section](../03-module-catalog.md). Parent index:
[04 — Setup modules](04-setup-modules.md).

## Goal

Implement the run-once tree-walk that locates a named config file by walking up from CWD —
the entry point of the setup chain.

## Deliverables

In `modules/rtl_test/setup.py`:

- `DiscoverConfigFileMod` — walks up the dir tree from CWD for a filename (config:
  `filename:str`, `max_levels:int = 8`); stops at git root or filesystem root; emits the
  resolved `Path`. Zero input ports; runs once via `unit`.
  **Failure handling**: post-loop check — if walked to the root without finding the file,
  call `log.critical(f"{filename} not found walking up from CWD")` (mirrors
  `rtl_buddy/src/rtl_buddy/config/root.py:35`). `PermissionError` from directory listing
  propagates uncaught (becomes harness CRITICAL via the bubbling-SystemExit catch). See
  [05 — Log idioms](../05-branching-and-results.md#log-idioms-per-failure-site).
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/config/root.py:16-36` — `_discover_root_cfg`.

Manifest entries in `modules/config.yaml` per [06 — Manifest additions](../06-graph-yaml.md).

## Tests

In `modules/tests/test_setup.py`:

- Discovery walks up to find a fixture `root_config.yaml`; stops at depth limit.

## Acceptance criteria

- Tests pass.
- Discovery resolves a fixture `root_config.yaml` from a nested CWD and stops at the
  `max_levels` depth limit (contributes to the setup-only end-to-end graph — see
  [04 index](04-setup-modules.md#acceptance-criteria)).

## Notes

`DiscoverConfigFileMod` is reusable for the harness's own config discovery — see
[07 implementation note](../07-ambiguities-and-assumptions.md).
