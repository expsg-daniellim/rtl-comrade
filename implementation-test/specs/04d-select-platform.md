# Spec 04d: select-platform (`SelectPlatformMod`)

**Depends on:** spec 01 (schema).
**References:** [03 — Setup section](../03-module-catalog.md). Parent index:
[04 — Setup modules](04-setup-modules.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)`
signature, the allowed output forms (plain return / named-port tuple / generator), the
`finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py`
are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry
below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit
`a69d962`). This module appends to `modules/rtl_test/setup.py`, which is created by spec
[`04a`](04a-discover-config-file.md) — append, do not overwrite. The file is shared with the
setup chain (`04a`–`04i`, index [04](04-setup-modules.md)), the selection/expansion chain
(`05a`–`05f`, index [05](05-selection-expansion-modules.md)), and git-status (`10b`);
coordinate shared imports and helpers with those specs.

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

## Algorithm

1. Run `uname`: `uname = subprocess.run(["uname"], capture_output=True,
   text=True).stdout.strip()`.
2. Iterate `root_cfg.platforms` in declaration order; the first platform whose `unames` list
   contains `uname` is the match — emit `("default", platform_cfg)` and return.
3. **Failure — no platform matches.** Falling out of the loop means none matched:
   `log.critical(f"cannot find cfg-platform for uname {uname}")` (harness exits 1). A
   `FileNotFoundError` from the `uname` subprocess is surprising at this layer and is left to
   propagate uncaught.

## Deliverables

In `modules/rtl_test/setup.py`:

- `SelectPlatformMod` — runs `uname` (subprocess), matches against each platform's
  `unames`, picks one; critical-logs if no match; emits `platform_cfg`.
  **Failure handling**: post-loop check — no platform matched → `log.critical(f"cannot
  find cfg-platform for uname {uname}")` (mirrors
  `rtl_buddy/src/rtl_buddy/config/root.py:117-118`). `uname` subprocess failure is
  surprising at this layer; let `FileNotFoundError` propagate.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/config/root.py:107-118` — `uname` subprocess + platform-match loop in `RootConfig.__init__`.

**Manifest** — append to the `- file: rtl_test/setup.py` block in `modules/config.yaml`
(opened by [`04a`](04a-discover-config-file.md); append, don't re-create):

```yaml
  - { name: select-platform, class_name: SelectPlatformMod }
```

## Tests

In `modules/tests/test_setup.py`. Fixtures: `monkeypatch` on `subprocess.run` to return a
controlled `uname` (a mock-subprocess double); a `root_cfg` fixture carrying several
platforms; `logging_handler` for the `log.critical` path.

- `uname` matches the first platform's `unames` → emits `("default", <first platform_cfg>)`.
- `uname` matches only a later platform → emits `("default", <that platform_cfg>)` (iterates
  in declaration order).
- `uname` is present in two platforms' `unames` → emits the **first** in declaration order
  (boundary: first-match wins).
- `uname` matches no platform → no-match `log.critical` → `pytest.raises(SystemExit)`.
- `subprocess.run(["uname"])` raises `FileNotFoundError` (no `uname` binary) → propagates
  uncaught → `pytest.raises(FileNotFoundError)` (boundary: surprising tool-missing error).

## Acceptance criteria

- Tests pass.
- Output port `default` exercised: selects the correct `platform_cfg` from a real rtl_buddy
  `root_config.yaml` fixture under a controlled `uname` (contributes to the setup-only
  end-to-end graph — see [04 index](04-setup-modules.md#acceptance-criteria)).
- Failure idiom exercised: a `uname` matching no configured platform →
  `log.critical(f"cannot find cfg-platform for uname {uname}")` (harness exit 1).
- The `modules/config.yaml` manifest entry `{ name: select-platform, class_name: SelectPlatformMod }`
  validates and the harness resolves `select-platform` → `SelectPlatformMod`.

## Constraints

- `unit` contract; emit on the string-literal `default` port.
- Match in declaration order — the **first** platform whose `unames` list contains the `uname`
  output wins.
- No platform matches → `log.critical` (harness exit 1), never a port-routed result. A
  `FileNotFoundError` from the `uname` subprocess is surprising at this layer — let it propagate
  uncaught.
