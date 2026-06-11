# Spec 04d: select-platform (`SelectPlatformMod`)

**Depends on:** spec 01 (schema).
**References:** [03 — Setup section](../03-module-catalog.md). Parent index:
[04 — Setup modules](04-setup-modules.md).

## Goal

Run `uname`, match it against each configured platform, and emit the active `platform_cfg`.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry —
the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract: unit
inputs:   root_cfg
outputs:  default → platform_cfg
```

```python
class SelectPlatformMod:
    def run(self, root_cfg):
        uname = subprocess.run(["uname"], capture_output=True, text=True).stdout.strip()
        for platform_cfg in root_cfg.platforms:
            if uname in platform_cfg.unames:
                return ("default", platform_cfg)
        log.critical("no_platform_match", uname=uname)
```

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
