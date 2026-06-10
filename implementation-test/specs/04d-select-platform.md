# Spec 04d: select-platform (`SelectPlatformMod`)

**Depends on:** spec 01 (schema).
**References:** [03 — Setup section](../03-module-catalog.md). Parent index:
[04 — Setup modules](04-setup-modules.md).

## Goal

Run `uname`, match it against each configured platform, and emit the active `platform_cfg`.

## Deliverables

In `modules/rtl_test/setup.py`:

- `SelectPlatformMod` — runs `uname` (subprocess), matches against each platform's
  `unames`, picks one; critical-logs if no match; emits `platform_cfg`.
  **Failure handling**: post-loop check — no platform matched → `log.critical(f"cannot
  find cfg-platform for uname {uname}")` (mirrors
  `rtl_buddy/src/rtl_buddy/config/root.py:117-118`). `uname` subprocess failure is
  surprising at this layer; let `FileNotFoundError` propagate.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/config/root.py:107-118` — `uname` subprocess + platform-match loop in `RootConfig.__init__`.

Manifest entries in `modules/config.yaml` per [06 — Manifest additions](../06-graph-yaml.md).

## Tests

In `modules/tests/test_setup.py`:

- Platform select picks correctly under controlled `uname` (mock or skip-if).

## Acceptance criteria

- Tests pass.
- Selects the correct platform from a real rtl_buddy `root_config.yaml` fixture under a
  controlled `uname` (contributes to the setup-only end-to-end graph — see
  [04 index](04-setup-modules.md#acceptance-criteria)).
