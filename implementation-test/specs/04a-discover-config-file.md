# Spec 04a: discover-config-file (`DiscoverConfigFileMod`)

**Depends on:** spec 01 (schema).
**References:** [03 — Setup section](../03-module-catalog.md). Parent index:
[04 — Setup modules](04-setup-modules.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)`
signature, the allowed output forms (plain return / named-port tuple / generator), the
`finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py`
are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry
below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit
`a69d962`). This module appends to `modules/rtl_test/setup.py`, shared with the setup chain
(`04a`–`04i`, index [04](04-setup-modules.md)), the selection/expansion chain (`05a`–`05f`,
index [05](05-selection-expansion-modules.md)), and git-status (`10b`); coordinate shared
imports and helpers with those specs.

## Goal

Implement the run-once tree-walk that locates a named config file by walking up from CWD —
the entry point of the setup chain.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry —
the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract: unit
config:   filename:str, max_levels:int = 8
inputs:   —  (zero-input; runs once)
outputs:  default → Path
```

```python
class DiscoverConfigFileMod:
    @serde
    class Config:
        filename:str
        max_levels:int = 8

    def __init__(self, config):
        self.filename = config.filename
        self.max_levels = config.max_levels

    def run(self):
        d = Path.cwd()
        for _ in range(self.max_levels):
            if (d / self.filename).is_file():
                return ("default", d / self.filename)
            if (d / ".git").exists() or d == d.parent:
                break
            d = d.parent
        log.critical("config_not_found", filename=self.filename)
```

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

**Manifest** — this module opens the `rtl_test/setup.py` block in `modules/config.yaml`
(later appended to by `04b`–`04i`, `05a`–`05f`, `10b`):

```yaml
- file: rtl_test/setup.py
  plugins:
  - { name: discover-config-file, class_name: DiscoverConfigFileMod }
```

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
